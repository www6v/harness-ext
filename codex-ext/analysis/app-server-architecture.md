# codex-app-server 架构分析

> 基于 codex-rust v0.155.1 源码分析

## 1. 概述

`codex-app-server` 是 OpenAI Codex 桌面/VSCode 产品的**核心守护进程**。它是一个长期运行的 Rust 进程，位于 UI 客户端（VSCode 扩展、桌面应用、Web UI 等）和底层 Codex 核心（线程管理器、线程存储、模型提供者、MCP 工具服务器、沙箱、插件、登录、分析等）之间。

它暴露的是**双向 JSON-RPC 2.0 协议**（非 REST/HTTP）。同一套线格式用于四种传输模式：

| 传输方式 | URL 语法 | 用途 |
|---|---|---|
| `Stdio`（默认） | `stdio://` | 单个嵌入式客户端（CLI / 进程内） |
| `UnixSocket` | `unix://PATH` | 本地守护进程（生产守护进程模式） |
| `WebSocket` | `ws://IP:PORT` | 远程 / Web 客户端 |
| `Off` | `off` | 仅进程内嵌入（无监听器） |

第五种传输方式 **`RemoteControl`** 向 ChatGPT 后端（`chatgpt_base_url`）打开出站 WebSocket，让远程 ChatGPT 会话驱动本地守护进程。

> **注意：** 尽管依赖 `axum`，服务器**不暴露 REST 路由**。`axum` 仅用于其 WebSocket 升级机制（`ws://` 监听器）。

## 2. 工作区相关 Crate

所有 crate 位于 `codex-rs/` 目录下：

| Crate | 角色 |
|---|---|
| `app-server/` | 守护进程二进制 + 库。`src/main.rs` 解析 CLI 并调用 `run_main_with_transport_options`。 |
| `app-server-protocol/` | 定义 JSON-RPC **线协议**：`ClientRequest`、`ClientResponse`、`ServerRequest`、`ServerResponse`、`ServerNotification`、`ClientNotification`，以及所有参数/响应结构体。Schema 输出到 `schema/json/v1/` 和 `schema/json/v2/`。 |
| `app-server-transport/` | 传输层管道 — stdio、unix socket、WebSocket 接受器、远程控制、认证、守护进程关闭、连接 ID。 |
| `app-server-client/` | 客户端库，供其他 Rust 二进制（如 `tui`）与守护进程通信 — 处理 PID 跟踪、托管安装、更新循环、远程控制客户端。 |
| `app-server-daemon/` | 托管守护进程生命周期辅助（Windows 服务 / PID 跟踪）。 |
| `app-server-protocol-noop-macros/` | 非测试构建中使用的 `JsonSchema`/`TS` derive 宏的 no-op 替代。 |
| `app-server-test-client/` | 仅测试客户端，驱动服务器（loopback 响应服务器、引出脚本、插件分析测试）。 |

## 3. 入口点

### 二进制入口

**二进制文件：** `src/main.rs`（`codex-app-server`）
- 使用 `clap` 解析 `AppServerArgs`：`--listen URL`、`--session-source`、`--strict-config`、`--remote-control`、`--managed-daemon`，配置覆盖 `-c key=value`。
- 调用 `arg0_dispatch_or_else`，允许同一二进制通过 `arg0` 符号链接伪装成其他工具。
- 委托给 `src/lib.rs` 中的 `run_main_with_transport_options()`。

### 库入口

**库（`src/lib.rs`）：** `run_main_with_transport_options()` 是主启动函数：

1. 解析 CLI 配置覆盖，定位 `codex_home`
2. 加载 `ConfigManager`（用户 + 项目 + 托管配置层）和 `AuthManager`
3. 初始化 SQLite 状态数据库（带损坏恢复 / 备份重建）
4. 构建 `EnvironmentManager`、OpenTelemetry 提供者、跟踪层
5. 获取启动锁（`app_server_startup_lock_path`）用于 unix-socket 模式
6. 启动选定的传输接受器（`start_stdio_connection`、`start_control_socket_acceptor`、`start_websocket_acceptor`）
7. 启动 **Remote Control** 注册（`start_remote_control`）
8. 生成两个长生命周期任务：
   - **出站路由任务** — 将 `OutgoingEnvelope` 写入每连接写入器，跟踪每 `ConnectionId` 的 `OutboundConnectionState`
   - **处理器任务** — 拥有 `MessageProcessor` 并处理 `TransportEvent`：`ConnectionOpened`、`ConnectionClosed`、`IncomingMessage`。分发请求，关闭时排空连接
9. 监听 `SIGTERM`/`SIGHUP`/`Ctrl-C` → 进入优雅重启排空（拒绝新 turn，等待进行中的助手 turn 完成）

## 4. MessageProcessor — 中央请求分发器

文件：`src/message_processor.rs`

```
MessageProcessor
├── turn_admission: TurnAdmission                // 信号量，关闭期间限制 turn
├── user_verification: Service
├── outgoing: Arc<OutgoingMessageSender>
├── models_refresh_worker, turn_cost_worker
├── skills_watcher: Arc<SkillsWatcher>
└── 20+ 请求处理器（每个域一个）：
    ├── AccountRequestProcessor
    ├── AppsRequestProcessor
    ├── CatalogRequestProcessor
    ├── CommandExecRequestProcessor
    ├── ConfigRequestProcessor
    ├── EnvironmentRequestProcessor
    ├── FeedbackRequestProcessor
    ├── FsRequestProcessor
    ├── GitRequestProcessor
    ├── InitializeRequestProcessor
    ├── MarketplaceRequestProcessor
    ├── McpRequestProcessor
    ├── PluginRequestProcessor
    ├── ProcessExecRequestProcessor
    ├── ProjectRequestProcessor
    ├── RemoteControlRequestProcessor
    ├── SearchRequestProcessor
    ├── ThreadGoalRequestProcessor
    ├── ThreadQueueRequestProcessor
    ├── ThreadRequestProcessor
    ├── TurnRequestProcessor
    └── WindowsSandboxRequestProcessor
    (+ ExternalAgentConfigRequestProcessor)
```

### 请求处理流程

在 `src/lib.rs` 中，主事件循环匹配每个 `JSONRPCMessage::Request` 并转发给 `processor.process_request(...)`：

1. 构建跟踪 span
2. 反序列化 `JSONRPCRequest → ClientRequest`（通过 `protocol/common.rs` 中的标记枚举 `serde` 实现）
3. 特殊处理 `Initialize`（必须在连接上的任何其他方法之前发生）
4. 对于已初始化的连接，为受 turn 影响的方法获取 `TurnAdmission` 许可
5. 可选地在 `RequestSerializationQueue` 上排队（用于线程作用域序列化）
6. 通过 `handle_initialized_client_request()` 分发 — 一个巨大的 `match` 匹配 `ClientRequest` 变体（`message_processor.rs` 第 1074–1839 行）— 到适当的处理器
7. 通过 `OutgoingMessageSender::send_response_as` 发送响应，或通过 `send_error()` 发送错误

## 5. 传输与连接

`src/transport.rs`（服务器 crate 中）是对 `codex-app-server-transport` 的薄重新导出门面：

- **`AppServerTransport`** — 枚举（`Stdio`、`UnixSocket{socket_path}`、`WebSocket{bind_address}`、`Off`）
- **启动函数：** `start_stdio_connection`、`start_control_socket_acceptor`、`start_websocket_acceptor`、`start_remote_control`
- **`TransportEvent`** — `ConnectionOpened{id, origin, auth, writer, disconnect_sender}`、`ConnectionClosed{id}`、`IncomingMessage{connection_id, message}`、`DaemonShutdown`
- **`ConnectionOrigin`** — `Stdio`、`UnixSocket`、`WebSocket`、`RemoteControl`
- **`RemoteControlPolicy`** — `Allowed` 或 `DisabledByRequirements`
- **`RemoteControlStartupMode`** — `ResolvePersisted`、`EnabledEphemeral`、`DisabledEphemeral`
- WebSocket 认证通过 `AppServerWebsocketAuthSettings`/`WebsocketAuthCliMode`
- 启动锁：`app_server_startup_lock_path(&codex_home)` 确保只有一个守护进程拥有 socket

## 6. 生命周期、关闭与排空

- `ShutdownState` 跟踪 `requested`/`forced` 标志
- 第一次 `SIGTERM`/`SIGHUP`/`Ctrl-C`：`turn_admission.begin_drain()` 拒绝新 turn，等待进行中的 turn + 已接受的请求完成
- 第二次信号 → 强制完成
- 退出时：断开所有客户端连接（`OutboundControlEvent::DisconnectAll`），排空 `ConnectionCleanupTasks`，取消 `transport_shutdown_token`，加入接受器句柄
- 托管守护进程模式（`--managed-daemon`）额外写入 `daemon_recovery_file_path(&codex_home)` 加载线程的快照；下次启动时 `daemon_thread_recovery::start_recovery` 恢复它们

## 7. 进程内嵌入

服务器也可嵌入：`src/in_process.rs` 直接暴露 `MessageProcessor`，使进程内 Rust 调用者可以跳过线格式并调用 `process_client_request(ClientRequest, …)`（类型化，无 JSON）。进程内路径绕过 JSON 反序列化，但仍通过相同的处理器分发。

## 8. 其他二进制文件

同一 crate 的 `Cargo.toml` 定义了三个二进制文件：

- `codex-app-server` — 守护进程（`src/main.rs`）
- `codex-app-server-test-notify-capture` — 测试辅助，捕获出站服务器通知（`src/bin/notify_capture.rs`）
- `exec-server` — 独立执行服务器（`src/bin/exec_server.rs`）— 在完整守护进程之外使用 `EnvironmentManager`/执行机制

## 9. 测试

- `tests/common/` — 共享测试客户端工具（`app_test_support`）
- 每模块 `*_tests.rs` 文件，如 `transport_tests.rs`、`user_verification_*_tests.rs`、`config_manager_service_tests.rs`、`turn_cost_worker_tests.rs`
- `app-server-test-client` crate 提供集成测试脚本（如 `live_elicitation_hold.sh`、`request_user_input.rs`）
