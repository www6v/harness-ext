# Codex CLI v0.155.1 — 项目分析报告

> **分析日期**: 2026-09-21
> **仓库**: [openai/codex](https://github.com/openai/codex)
> **许可证**: Apache-2.0
> **版本**: 0.155.1

---

## 目录

1. [项目概述](#1-项目概述)
2. [仓库顶层结构](#2-仓库顶层结构)
3. [Rust 工作空间架构 (codex-rs)](#3-rust-工作空间架构-codex-rs)
4. [核心 crate 详解](#4-核心-crate-详解)
5. [扩展系统 (ext/)](#5-扩展系统-ext)
6. [app-server 与 exec-server 架构](#6-app-server-与-exec-server-架构)
7. [协议层 (protocol)](#7-协议层-protocol)
8. [SDK 层](#8-sdk-层)
9. [TypeScript/Node.js 层](#9-typescriptnodejs-层)
10. [构建系统](#10-构建系统)
11. [测试策略](#11-测试策略)
12. [平台支持](#12-平台支持)
13. [关键外部依赖](#13-关键外部依赖)
14. [开发工作流](#14-开发工作流)
15. [架构总结](#15-架构总结)

---

## 1. 项目概述

**Codex CLI** 是 OpenAI 开发的一个本地运行的 AI 编程代理 (coding agent)。它可以直接在终端中使用，也可以集成到 IDE（VS Code、Cursor、Windsurf）中，还提供桌面应用和 Web 版本。

### 主要产品形态

| 形态 | 说明 |
|------|------|
| **Codex CLI** | 命令行接口，本项目的核心交付物 |
| **Codex TUI** | 终端用户界面 (Terminal UI)，基于 ratatui |
| **Codex IDE** | 集成到 VS Code / Cursor / Windsurf 等编辑器 |
| **Codex App** | 桌面应用 (`codex app`) |
| **Codex Web** | 云端版本 (chatgpt.com/codex) |

### 安装方式

- Shell 脚本安装: `curl -fsSL https://chatgpt.com/codex/install.sh | sh`
- npm: `npm install -g @openai/codex`
- Homebrew: `brew install --cask codex`
- 直接下载 GitHub Release 二进制文件

### 认证方式

- 通过 ChatGPT 账户登录（推荐，含 Plus/Pro/Business/Edu/Enterprise 计划）
- API Key 方式

---

## 2. 仓库顶层结构

```
codex-rust-v0.155.1/
├── codex-rs/          # Rust 工作空间（主代码库，150+ crates）
├── codex-cli/         # npm 包（@openai/codex），入口 bin/codex.js
├── sdk/               # 多语言 SDK（Python + TypeScript）
├── docs/              # 项目文档（安装、配置、沙箱、技能等）
├── scripts/           # 构建/格式化/发布脚本
├── third_party/       # 第三方依赖（voice、v8 等）
├── tools/             # 开发工具（argument-comment-lint 等）
├── patches/           # Bazel 补丁（LLVM、rules_rust、V8 等）
├── bazel/             # Bazel 构建配置和扩展
├── .github/           # CI/CD 工作流
├── package.json       # monorepo 根（pnpm workspace）
├── pnpm-workspace.yaml
├── MODULE.bazel       # Bazel 模块定义
├── justfile           # 任务运行器（just）
└── README.md
```

---

## 3. Rust 工作空间架构 (codex-rs)

### 3.1 规模概览

`codex-rs` 目录是一个包含 **150+ 个 crate** 的巨型 Rust 工作空间，由 `Cargo.toml` 中的 `[workspace.members]` 统一管理。工作空间使用 **Rust 2024 Edition**，版本由 workspace 级别统一控制。

### 3.2 Crate 分类

#### 入口/二进制 crates（4 个）

| Crate | 包名 | 说明 |
|-------|------|------|
| `cli/` | `codex-cli` | CLI 主入口，包含 `codex` 和 `logs_client` 两个二进制文件 |
| `tui/` | `codex-tui` | TUI 界面，包含 `codex-tui` 和 `md-events` 两个二进制文件 |
| `app-server/` | `codex-app-server` | 应用服务器，包含 `codex-app-server`、`exec-server`、`test-notify-capture` 三个二进制文件 |
| `code-mode-host/` | `codex-code-mode-host` | 独立的 code-mode 主机 |

#### 核心逻辑 crates（~10 个）

| Crate | 包名 | 说明 |
|-------|------|------|
| `core/` | `codex-core` | **最大的 crate**，核心代理逻辑、会话管理、上下文构建、MCP 集成等 |
| `protocol/` | `codex-protocol` | 核心协议定义：模型、权限、审批、工具调用、执行策略等 |
| `app-server-protocol/` | `codex-app-server-protocol` | app-server 的 JSON-RPC 协议（v1 + v2） |
| `exec-server/` | `codex-exec-server` | 执行服务器，管理沙箱进程执行 |
| `exec-server-protocol/` | `codex-exec-server-protocol` | exec-server 通信协议 |
| `config/` | `codex-config` | 配置管理（config.toml 解析） |
| `state/` | `codex-state` | 状态管理 |
| `sandboxing/` | `codex-sandboxing` | 沙箱抽象层 |
| `codex-api/` | `codex-api` | 与 OpenAI API 的交互定义 |
| `codex-client/` | `codex-client` | API 客户端实现 |

#### 服务器与通信 crates（~8 个）

| Crate | 包名 | 说明 |
|-------|------|------|
| `app-server/` | `codex-app-server` | 主应用服务器（WebSocket + HTTP） |
| `app-server-transport/` | `codex-app-server-transport` | 传输层抽象 |
| `app-server-daemon/` | `codex-app-server-daemon` | 守护进程管理 |
| `app-server-client/` | `codex-app-server-client` | app-server 客户端 |
| `backend-client/` | `codex-backend-client` | 后端 API 客户端 |
| `http-client/` | `codex-http-client` | HTTP 客户端封装 |
| `websocket-client/` | `codex-websocket-client` | WebSocket 客户端 |
| `rmcp-client/` | `codex-rmcp-client` | Rust MCP 客户端 |

#### 扩展系统 crates（`ext/`，~13 个）

| Crate | 包名 | 说明 |
|-------|------|------|
| `ext/agent/` | `codex-agent-extension` | Agent 扩展 |
| `ext/connectors/` | `codex-connectors-extension` | 连接器扩展 |
| `ext/extension-api/` | `codex-extension-api` | 扩展 API 定义 |
| `ext/goal/` | `codex-goal-extension` | 目标管理扩展 |
| `ext/git-attribution/` | `codex-git-attribution` | Git 归属扩展 |
| `ext/guardian-reviewer/` | `codex-guardian-reviewer` | Guardian 审查扩展 |
| `ext/guardian-v2/` | `codex-guardian-v2` | Guardian v2 扩展 |
| `ext/history-notes/` | `codex-history-notes-extension` | 历史记录扩展 |
| `ext/image-generation/` | `codex-image-generation-extension` | 图像生成扩展 |
| `ext/items/` | `codex-extension-items` | 扩展项目类型 |
| `ext/mcp/` | `codex-mcp-extension` | MCP 扩展 |
| `ext/memories/` | `codex-memories-extension` | 记忆扩展 |
| `ext/queue/` | `codex-queue-extension` | 队列扩展 |
| `ext/skills/` | `codex-skills-extension` | 技能扩展 |
| `ext/web-search/` | `codex-web-search-extension` | 网络搜索扩展 |

#### 功能模块 crates（~40+ 个）

| Crate | 说明 |
|-------|------|
| `agent-graph-store/` | Agent 图存储 |
| `agent-identity/` | Agent 身份管理 |
| `agent-roles/` | Agent 角色定义 |
| `analytics/` | 分析/遥测 |
| `apply-patch/` | 代码补丁应用 |
| `attachment-store/` | 附件存储 |
| `aws-auth/` | AWS 认证 |
| `code-mode/` | Code mode 逻辑 |
| `code-mode-protocol/` | Code mode 协议 |
| `code-mode-runtime/` | Code mode 运行时 |
| `cloud-config/` | 云端配置 |
| `cloud-tasks/` | 云端任务 |
| `collaboration-mode-templates/` | 协作模式模板 |
| `connectors/` | 连接器 |
| `context-fragments/` | 上下文片段 |
| `diagnostics/` | 诊断工具 |
| `exec/` | 执行抽象 |
| `execpolicy/` | 执行策略 |
| `features/` | 特性标志 |
| `feedback/` | 用户反馈 |
| `file-search/` | 文件搜索 |
| `file-system/` | 文件系统抽象 |
| `file-watcher/` | 文件监控 |
| `git-utils/` | Git 工具 |
| `guardian-context/` | Guardian 上下文 |
| `history/` | 历史管理 |
| `hooks/` | 钩子系统 |
| `keyring-store/` | 密钥存储 |
| `login/` | 登录管理 |
| `memories/read/` + `memories/write/` | 记忆读写 |
| `message-history/` | 消息历史 |
| `model-provider/` + `model-provider-info/` | 模型提供者 |
| `models-manager/` | 模型管理 |
| `network-proxy/` | 网络代理 |
| `ollama/` | Ollama 集成 |
| `lmstudio/` | LM Studio 集成 |
| `plugin/` | 插件系统 |
| `process-hardening/` | 进程加固 |
| `prompts/` | 提示词模板 |
| `realtime-webrtc/` | 实时 WebRTC |
| `rollout/` + `rollout-trace/` | 会话回滚和追踪 |
| `responses-api-proxy/` | Response API 代理 |
| `secrets/` | 密钥管理 |
| `shell-command/` | Shell 命令抽象 |
| `shell-escalation/` | Shell 权限提升 |
| `skills/` | 技能系统 |
| `thread-store/` | 线程存储 |
| `tools/` | 工具定义 |
| `uds/` | Unix Domain Socket |
| `user-verification/` | 用户验证 |
| `worktree/` | Git worktree 管理 |
| `workload-identity/` | 工作负载身份 |

#### 平台特定 crates（4 个）

| Crate | 说明 | 平台 |
|-------|------|------|
| `linux-sandbox/` | Linux 沙箱（bwrap + seccomp + landlock） | Linux |
| `bwrap/` | Bubblewrap 封装 | Linux |
| `mxc-sandbox/` | Microsoft MXC 沙箱集成 | Windows |
| `windows-sandbox-rs/` | Windows 沙箱服务 | Windows |
| `windows-sandbox-service/` | Windows 沙箱服务管理 | Windows |

#### 实用工具 crates（`utils/`，~20 个）

| Crate | 说明 |
|-------|------|
| `utils/absolute-path/` | 绝对路径类型 |
| `utils/approval-presets/` | 审批预设 |
| `utils/audio/` | 音频工具 |
| `utils/cache/` | 缓存抽象 |
| `utils/cargo-bin/` | Cargo 二进制路径解析 |
| `utils/cli/` | CLI 工具 |
| `utils/elapsed/` | 耗时显示 |
| `utils/fuzzy-match/` | 模糊匹配 |
| `utils/git-discovery/` | Git 仓库发现 |
| `utils/home-dir/` | 主目录 |
| `utils/image/` | 图像工具 |
| `utils/json-to-toml/` | JSON→TOML 转换 |
| `utils/oss/` | OSS 许可信息 |
| `utils/output-truncation/` | 输出截断 |
| `utils/path-utils/` + `utils/path-uri/` | 路径工具 |
| `utils/plugins/` | 插件工具 |
| `utils/pty/` | PTY 工具 |
| `utils/readiness/` | 就绪检查 |
| `utils/redacted-string/` | 敏感信息遮蔽 |
| `utils/rustls-provider/` | rustls 配置 |
| `utils/sandbox-summary/` | 沙箱摘要 |
| `utils/sleep-inhibitor/` | 休眠阻止 |
| `utils/stream-parser/` | 流解析 |
| `utils/string/` | 字符串工具 |
| `utils/template/` | 模板引擎 |

#### 其他 crates

| Crate | 说明 |
|-------|------|
| `ansi-escape/` | ANSI 转义序列处理 |
| `arg0/` | 进程名管理 |
| `async-utils/` | 异步工具 |
| `build-info/` | 构建信息 |
| `chatgpt/` | ChatGPT 集成 |
| `codex-backend-openapi-models/` | 后端 OpenAPI 模型 |
| `codex-experimental-api-macros/` | 实验性 API 宏 |
| `codex-home/` | Codex 主目录管理 |
| `codex-mcp/` | MCP 连接管理（核心 MCP 逻辑） |
| `core-api/` | 核心 API 抽象 |
| `core-plugins/` | 核心插件注册 |
| `external-agent-migration/` | 外部 agent 迁移 |
| `install-context/` | 安装上下文 |
| `mcp-skill-dependencies/` | MCP 技能依赖 |
| `otel/` + `otel-trace-websocket/` | OpenTelemetry 集成 |
| `response-debug-context/` | 响应调试上下文 |
| `stdio-to-uds/` | 标准IO 到 Unix Socket |
| `terminal-detection/` | 终端检测 |
| `test-binary-support/` | 测试二进制支持 |
| `thread-manager-sample/` | 线程管理器示例 |
| `v8-poc/` | V8 概念验证 |

---

## 4. 核心 crate 详解

### 4.1 `codex-core` — 代理核心

**位置**: `codex-rs/core/`
**规模**: 498 个 Rust 源文件（src/ 目录）
**定位**: 工作空间中最大的 crate，也是 AGENTS.md 中明确警告"避免再添加代码"的 crate。

#### 主要模块结构

| 模块 | 作用 |
|------|------|
| `agent/` | Agent 解析、注册、角色、控制（执行、驻留、服务层、生成、授权） |
| `config/` | 配置编辑、Bedrock、权限配置文件、OTel、认证密钥环 |
| `context/` | 上下文构建：指令、记忆、Guardian 策略、Hook 上下文、环境配置 |
| `client.rs` + `client_common.rs` | 模型客户端：HTTP SSE 流、请求/响应处理 |
| `codex_thread.rs` | Codex 线程生命周期管理 |
| `thread_manager.rs` | 线程管理器（创建/关闭/分叉） |
| `compact/` + `compact_*/` | 上下文压缩/令牌预算管理 |
| `mcp/` | MCP 工具集成（工具暴露、技能依赖、审批模板） |
| `exec/` | 命令执行（统一执行模型） |
| `guardian/` | Guardian 安全审查系统 |
| `sandboxing/` | 沙箱抽象 |
| `plugins/` | 插件加载与注册 |
| `skills/` | 技能管理 |
| `rollout/` | 会话持久化与恢复 |
| `session/` | 会话状态（turn context） |
| `hooks/` | 钩子系统（hook_mcp_executor、hook_runtime） |
| `connectors/` | 外部连接器集成 |
| `agents_md/` | AGENTS.md 文件解析与管理 |
| `web_search/` | 网络搜索集成 |
| `realtime_*/` | 实时对话与历史 |
| `shell/` + `shell_snapshot/` | Shell 环境管理 |
| `spawn/` | 进程生成 |
| `tools/` | 工具处理器 |
| `state_db_bridge/` | 状态数据库桥接 |

### 4.2 `codex-protocol` — 协议定义

**位置**: `codex-rs/protocol/`
**规模**: ~70 个源文件
**定位**: 定义 Codex 系统的所有核心数据结构。

#### 主要模块

| 模块 | 内容 |
|------|------|
| `models/` | 配置更新、工具调用执行、项目元数据 |
| `openai_models/` | Guardian 模型、推理努力 (reasoning effort) |
| `permissions/` | 权限目标、否认读取验证器、Windows glob |
| `protocol.rs` | 环境配置协议 |
| `account.rs` | 账户信息 |
| `approvals.rs` | 审批系统 |
| `auth.rs` | 认证 |
| `config_types.rs` | 配置类型 |
| `dynamic_tools.rs` | 动态工具定义 |
| `environment.rs` | 环境抽象 |
| `exec_output.rs` | 执行输出 |
| `items.rs` | 对话项定义 |
| `mcp.rs` / `mcp_policy.rs` | MCP 协议与策略 |
| `network_policy.rs` | 网络策略 |
| `realtime.rs` | 实时通信协议 |
| `request_user_input.rs` | 用户输入请求 |
| `shell_environment.rs` | Shell 环境 |
| `turn_input.rs` | Turn 输入 |
| `plan_tool.rs` | Plan 工具 |

### 4.3 `codex-app-server-protocol` — API 协议

**位置**: `codex-rs/app-server-protocol/`
**定位**: 定义 app-server 的 JSON-RPC API。

#### 版本策略
- **v1**: 已稳定，不再添加新功能
- **v2** (src/protocol/v2.rs + src/protocol/common.rs): 当前活跃开发版本

#### API 命名约定
- 请求: `*Params`
- 响应: `*Response`
- 通知: `*Notification`
- RPC 方法: `<resource>/<method>` (e.g., `thread/read`, `app/list`)
- 字段: wire 上使用 `camelCase`，config 相关使用 `snake_case`
- ID 类型: 纯 `String`
- 时间戳: 整数 Unix 秒 (`i64`)，命名 `*_at`

---

## 5. 扩展系统 (ext/)

扩展系统位于 `codex-rs/ext/`，提供可插拔的功能模块。

| 扩展 | 功能 |
|------|------|
| **agent** | Agent 扩展框架 |
| **connectors** | 外部服务连接器（如数据库、API） |
| **git-attribution** | Git 归属信息追踪 |
| **goal** | 目标管理系统 |
| **guardian-reviewer** / **guardian-v2** | 安全审查扩展 |
| **history-notes** | 对话历史备忘录 |
| **image-generation** | 图像生成（DALL-E 等） |
| **mcp** | Model Context Protocol 集成 |
| **memories** | 跨会话记忆系统 |
| **queue** | 任务队列扩展 |
| **skills** | 技能扩展框架 |
| **web-search** | 网络搜索集成 |
| **items** | 扩展项目类型定义 |
| **extension-api** | 扩展 API 抽象层 |

---

## 6. app-server 与 exec-server 架构

### 6.1 架构概述

Codex 采用 **前后端分离的进程架构**：

```
┌─────────────────────────────────────────────┐
│                  CLI / TUI                   │
│            (codex, codex-tui)                │
└─────────────────┬───────────────────────────┘
                  │ JSON-RPC (WebSocket/HTTP)
┌─────────────────▼───────────────────────────┐
│               app-server                     │
│         (codex-app-server)                   │
│  ┌───────────────────────────────────────┐  │
│  │          codex-core                    │  │
│  │  (agent logic, MCP, context, hooks)   │  │
│  └───────────────────────────────────────┘  │
└─────────────────┬───────────────────────────┘
                  │ exec-server-protocol
┌─────────────────▼───────────────────────────┐
│              exec-server                     │
│  (sandboxed command execution, file ops)     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Sandbox  │  │ Sandbox  │  │ Sandbox  │  │
│  │ (Linux)  │  │ (macOS)  │  │(Windows) │  │
│  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────┘
```

### 6.2 app-server

- 作为长期运行的守护进程
- 通过 JSON-RPC over WebSocket/HTTP 对外提供服务
- 内部集成 `codex-core` 代理逻辑
- 管理插件、扩展、MCP 连接
- 处理认证和会话生命周期

### 6.3 exec-server

- 接收来自 app-server 的命令执行请求
- 管理多种沙箱环境：
  - **Linux**: bubblewrap (bwrap) + seccomp + landlock
  - **macOS**: Seatbelt (`/usr/bin/sandbox-exec`)
  - **Windows**: AppContainer + MXC 沙箱
- 支持 `CODEX_SANDBOX_NETWORK_DISABLED` 环境变量控制沙箱网络
- 可在与 app-server 不同的操作系统上运行（远程执行）

### 6.4 通信流程

```
User Input → CLI/TUI → app-server (JSON-RPC) → core logic 
    → exec-server (tool calls) → sandboxed execution 
    → results → core logic → model API (OpenAI/Anthropic/...) 
    → response → TUI display
```

---

## 7. 协议层 (protocol)

### 7.1 `codex-protocol` (核心协议)

提供所有 crate 共享的基础数据类型：

- **审批系统**: `RequestPermission`, `PermissionTarget`
- **执行模型**: `ExecOutput`, `ShellEnvironment`
- **对话项**: `Item`, `ItemMetadata`, `ExecutedToolCalls`
- **MCP**: `McpPolicy`, `McpApprovalMeta`
- **网络策略**: `NetworkPolicy`, `NetworkDomainPermission`
- **配置**: `ConfigTypes`, `ModelProviderAuthInfo`
- **安全风险**: `SecurityRisk`
- **用户交互**: `RequestUserInput`, `TurnInput`

### 7.2 `codex-app-server-protocol` (API 协议)

定义 app-server 对外暴露的 JSON-RPC API：

- `thread/*`: 线程管理（创建、读取、列表、删除、恢复、分叉）
- `app/*`: 应用元数据（列表应用能力、版本信息）
- `turn/*`: 对话轮次管理
- `config/*`: 配置读写
- `model/*`: 模型信息和管理
- `plugin/*`: 插件管理
- `approval/*`: 审批操作

---

## 8. SDK 层

### 8.1 Python SDK

**位置**: `sdk/python/`
**包名**: `openai_codex`

```
sdk/python/
├── src/openai_codex/
│   ├── client.py           # 同步客户端
│   ├── async_client.py     # 异步客户端
│   ├── api.py              # 底层 API 调用
│   ├── models.py           # 数据模型
│   ├── types.py            # 类型定义
│   ├── errors.py           # 错误处理
│   ├── retry.py            # 重试逻辑
│   ├── _inputs.py          # 输入处理
│   ├── _run.py             # 运行管理
│   ├── _sandbox.py         # 沙箱配置
│   ├── _login.py           # 登录管理
│   ├── _goal.py            # 目标管理
│   ├── _approval_mode.py   # 审批模式
│   ├── _message_router.py  # 消息路由
│   └── generated/          # 从 app-server-protocol 自动生成
│       └── v2_all.py       # v2 API 生成代码
├── docs/                   # API 参考、FAQ
├── examples/               # 16 个示例（01-16）
├── tests/                  # 20+ 测试文件
└── notebooks/              # Jupyter notebook 教程
```

#### 核心功能
- 同步/异步双模式客户端
- 会话生命周期管理（创建、恢复、分叉、关闭）
- 流式事件处理
- 多模态输入（文本 + 图像）
- 审批和权限控制
- MCP 集成

### 8.2 TypeScript SDK

**位置**: `sdk/typescript/`

提供 TypeScript/JavaScript 版本的 SDK，与 Python SDK 对应的功能。

### 8.3 Python Runtime

**位置**: `sdk/python-runtime/`
**包名**: `codex_cli_bin`

轻量级运行时包，提供 CLI 二进制文件的 Python 封装。

---

## 9. TypeScript/Node.js 层

### 9.1 codex-cli npm 包

**位置**: `codex-cli/`
**包名**: `@openai/codex`

```
codex-cli/
├── bin/
│   └── codex.js          # npm 入口脚本（下载/启动 Rust 二进制）
├── scripts/
│   ├── build_npm_package.py
│   ├── init_firewall.sh
│   └── run_in_container.sh
└── package.json
```

这是一个 **轻量级 npm 包装器**，入口 `bin/codex.js` 负责：
1. 检测平台和架构
2. 下载对应的预编译 Rust 二进制文件
3. 启动 Codex CLI

### 9.2 前端 clients

- `codex-rs/responses-api-proxy/npm/` — 前端 Response API 代理（可能是 Electron/Web 前端使用）

---

## 10. 构建系统

### 10.1 双构建系统

Codex CLI 同时使用两个构建系统：

| 构建系统 | 用途 |
|----------|------|
| **Cargo** | 日常开发、本地构建、测试 |
| **Bazel** | CI/CD、正式发布、跨平台编译、端到端测试 |

### 10.2 Cargo 配置

- **Rust 版本**: 1.95.0 (stable)
- **Edition**: 2024
- **resolver**: "2"
- **优化配置**:
  - `dev`: debug = "limited" (快速编译 + 可回溯)
  - `release`: lto = "thin", debug = "line-tables-only", codegen-units = 4
  - `profiling`: 继承 release，debug = "full"
- **自定义 profile**: `dev-small` (最小二进制), `ci-test` (减少磁盘压力)

### 10.3 Bazel 配置

Bazel 配置非常精细，包括：

- **LLVM toolchain**: 通过 `@llvm` 模块提供的 hermetic 工具链
- **多平台 targets**:
  - `x86_64-unknown-linux-gnu` / `x86_64-unknown-linux-musl`
  - `aarch64-unknown-linux-gnu` / `aarch64-unknown-linux-musl`
  - `x86_64-apple-darwin` / `aarch64-apple-darwin`
  - `x86_64-pc-windows-msvc` / `x86_64-pc-windows-gnullvm`
  - `aarch64-pc-windows-msvc` / `aarch64-pc-windows-gnullvm`
- **自定义补丁管理**: 对 `rules_rs`、`rules_rust`、`v8`、`abseil-cpp`、`zstd-sys` 等应用了多个补丁
- **Windows 特殊处理**: MSVC + gnullvm 双 ABI 支持，Windows SDK 10.0.26100
- **macOS 特殊处理**: macOS SDK 26.5，多种框架链接
- **Nightly Rust**: 用于 argument-comment-lint 工具
- **外部工具链**: V8 (15.0.245.2)、OpenSSL、bzip2、xz、zlib 等均通过 Bazel 管理

### 10.4 justfile 任务

项目使用 `just` 作为任务运行器，主要命令：

| 命令 | 说明 |
|------|------|
| `just codex` | 运行 CLI |
| `just exec` | 运行 exec 模式 |
| `just test` | 运行测试 |
| `just fmt` | 格式化代码 |
| `just fix` | 运行 clippy --fix |
| `just bench` | 运行基准测试 |
| `just bazel-codex` | Bazel 构建并运行 |
| `just write-config-schema` | 生成 config schema JSON |
| `just write-app-server-schema` | 生成 app-server schema |
| `just argument-comment-lint` | 运行参数注释检查 |
| `just log` | 查看 SQLite 日志 |

---

## 11. 测试策略

### 11.1 测试框架

| 工具 | 用途 |
|------|------|
| **cargo-nextest** | 默认测试运行器（比 `cargo test` 更快） |
| **insta** | 快照测试（主要用于 TUI 输出验证） |
| **divan** | 基准测试 |
| **pretty_assertions** | 更好的测试 diff 输出 |
| **wiremock** | HTTP mock 服务 |
| **serial_test** | 串行测试 |
| **test-case** | 参数化测试 |
| **test-log** / **tracing-test** | 日志测试 |

### 11.2 测试层次

1. **单元测试**: 在各 crate 的 `*_tests.rs` 文件中
   - 测试模块使用 `#[path = "..._tests.rs"]` 方式组织
2. **集成测试** (核心): `core/suite/` 目录
   - 使用 `TestCodexBuilder` 构造测试实例
   - SSE 响应 mock (`mount_sse_once` / `mount_sse_sequence`)
   - `ResponseMock` 断言请求体
3. **集成测试** (app-server): 使用 `TestAppServer` + server mock
4. **快照测试** (TUI): `insta` 快照验证 UI 输出
5. **端到端测试**: Bazel 管理的 e2e 基准测试和集成测试
6. **远程测试**: 支持跨 OS 的 app-server + exec-server 组合测试

### 11.3 CI 测试

- `just test` (nextest) 用于本地开发
- `just bazel-test` 用于 Bazel 管理的测试
- `just test-github-scripts` 用于 GitHub Actions 脚本测试
- RUST_MIN_STACK = 8 MiB 避免栈溢出
- `NEXTEST_PROFILE=local` 使用本地配置

---

## 12. 平台支持

### 12.1 支持的操作系统

| 平台 | 架构 | 状态 |
|------|------|------|
| **macOS** | x86_64, aarch64 (Apple Silicon) | ✅ 完整支持 |
| **Linux** | x86_64 (glibc + musl), aarch64 (glibc + musl) | ✅ 完整支持 |
| **Windows** | x86_64 (MSVC + gnullvm), aarch64 | ✅ 完整支持 |
| **WSL2** | - | 推荐用于 Windows 开发 |

### 12.2 沙箱实现

| 平台 | 技术栈 |
|------|--------|
| **Linux** | Bubblewrap (bwrap), seccomp (syscall 过滤), landlock (文件系统限制) |
| **macOS** | Seatbelt (`/usr/bin/sandbox-exec`), 沙箱配置文件 |
| **Windows** | AppContainer (Windows Sandbox), MXC (Microsoft MXC 沙箱) |

### 12.3 内存分配器

- **musl Linux** (x86_64 + aarch64): `tikv-jemallocator 0.7.0`
- **其他平台**: 系统默认分配器

---

## 13. 关键外部依赖

### 13.1 Rust 生态核心依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| **tokio** | 1.x | 异步运行时（多线程、信号、进程、IO） |
| **serde** / **serde_json** | 1.x | 序列化/反序列化 |
| **ratatui** | 0.30.2 | TUI 框架 |
| **crossterm** | 0.29.0 | 跨平台终端控制 |
| **clap** | 4.x | CLI 参数解析 |
| **reqwest** | 0.12 | HTTP 客户端 |
| **axum** | 0.8 | HTTP 服务器 (app-server) |
| **sqlx** | 0.9.0 | SQLite 数据库（会话状态、历史） |
| **rmcp** | 3.2.0 | Rust MCP SDK |
| **tracing** | 0.1.44 | 结构化日志/追踪 |
| **opentelemetry** | 0.31.0 | OTel 遥测 |
| **tonic** / **prost** | 0.14.x | gRPC + Protobuf |
| **tungstenite** | 0.27.0 | WebSocket |
| **rustls** | 0.23 | TLS（aws_lc_rs 加密后端） |
| **sentry** | 0.46.0 | 错误追踪 |
| **tree-sitter** | 0.25.10 | 语法解析（Bash, PowerShell） |
| **gix** | 0.81.0 | Git 操作 |

### 13.2 AI/ML 相关

| 依赖 | 用途 |
|------|------|
| **tokenizers** (via tiktoken-rs) | Token 计数 |
| **tree-sitter-bash** / **tree-sitter-powershell** | Shell 脚本解析 |
| **syntect** | 语法高亮 |
| **image** | 图像处理（JPEG/PNG/GIF/WebP） |

### 13.3 平台特定

| 依赖 | 平台 | 用途 |
|------|------|------|
| **v8** (150.4.0) | 全平台 | JavaScript 引擎沙箱 |
| **tikv-jemallocator** | musl Linux | 内存分配器 |
| **landlock** / **seccompiler** | Linux | 沙箱安全 |
| **bwrap** (bubblewrap) | Linux | 容器隔离 |
| **MXC** | Windows | Microsoft 沙箱 |
| **AppContainer** | Windows | Windows 沙箱 |

### 13.4 第三方模型提供者

| 依赖 | 说明 |
|------|------|
| **ollama** | Ollama 本地模型集成 |
| **lmstudio** | LM Studio 本地模型集成 |
| **aws-auth** / **aws-sigv4** | AWS Bedrock 集成 |

---

## 14. 开发工作流

### 14.1 代码规范

项目有严格的 Rust 编码规范（定义在 `AGENTS.md`）：

- **Clippy lints**: 约 30 个 deny-level lint（unwrap_used、expect_used、redundant_clone 等）
- **format! 内联**: 强制 `uninlined_format_args`
- **方法引用**: 强制 `redundant_closure_for_method_calls`
- **if 折叠**: 强制 `collapsible_if`
- **参数注释约定**: opaque 字面量需加 `/*param_name*/` 注释
- **模块大小**: 目标 <500 行（不含测试），超过 800 行必须拆分
- **async trait**: 禁止 `#[async_trait]` 和 `#[allow(async_fn_in_trait)]`，要求显式 `Send` bound
- **测试断言**: 优先深度相等比较，使用 `pretty_assertions::assert_eq`
- **TUI 样式**: 使用 ratatui Stylize trait，禁止硬编码 `.white()`
- **API 设计**: 避免 bool/ambiguous Option 参数，使用 enum/新类型
- **变更大小**: 非机械性变更不超过 800 行，复杂逻辑不超过 500 行

### 14.2 格式化与 Lint

```
just fmt          # Rust + Bazel/Starlark + Python + Prettier
just fix -p <pkg> # Clippy --fix
just argument-comment-lint  # 自定义 Dylint 检查
just clippy -p <pkg>  # Clippy 检查
```

### 14.3 模式上下文管理规则

1. 不可重写历史 — 上下文必须增量构建
2. 避免频繁变更上下文导致缓存失效
3. 所有注入项必须有硬上限，不能无界
4. 单项不超过 10K tokens
5. 超过 1K tokens 的新项需标记 P0 人工审查
6. 注入片段必须在 `core/context` 中定义 struct 并实现 `ContextualUserFragment` trait

### 14.4 CI/CD

- **GitHub Actions**: CI 工作流在 `.github/workflows/` 中
- **多平台测试**: Linux, macOS, Windows 三方测试
- **argument-comment-lint**: CI 检查所有三个平台
- **schema 生成**: `write-config-schema` 和 `write-app-server-schema` 自动化

---

## 15. 架构总结

### 15.1 系统架构图

```
                          ┌──────────────────────────┐
                          │     User Interfaces       │
                          │  ┌──────┐  ┌──────────┐  │
                          │  │ CLI  │  │   TUI    │  │
                          │  └──┬───┘  └────┬─────┘  │
                          └─────┼───────────┼────────┘
                                │           │
                    JSON-RPC over WebSocket/HTTP
                                │           │
                          ┌─────▼───────────▼────────┐
                          │       app-server          │
                          │  ┌──────────────────────┐ │
                          │  │  Plugin / Extension   │ │
                          │  │       System          │ │
                          │  ├──────────────────────┤ │
                          │  │     codex-core        │ │
                          │  │  ┌────────────────┐  │ │
                          │  │  │ Agent & Thread  │  │ │
                          │  │  │    Manager       │  │ │
                          │  │  ├────────────────┤  │ │
                          │  │  │  Context Builder│  │ │
                          │  │  ├────────────────┤  │ │
                          │  │  │  MCP Integration│  │ │
                          │  │  ├────────────────┤  │ │
                          │  │  │  Hook System    │  │ │
                          │  │  ├────────────────┤  │ │
                          │  │  │  Skills Engine  │  │ │
                          │  │  └────────────────┘  │ │
                          │  └──────────────────────┘ │
                          └────────────┬──────────────┘
                                       │
                          exec-server-protocol
                                       │
                          ┌────────────▼──────────────┐
                          │       exec-server          │
                          │  ┌──────────────────────┐ │
                          │  │   Sandbox Manager     │ │
                          │  │  ┌────┐┌────┐┌─────┐ │ │
                          │  │  │bwrp││seat││MXC  │ │ │
                          │  │  │    ││belt││     │ │ │
                          │  │  └────┘└────┘└─────┘ │ │
                          │  └──────────────────────┘ │
                          └───────────────────────────┘
                                       │
                          ┌────────────▼──────────────┐
                          │    External Services       │
                          │  ┌────────┐ ┌───────────┐ │
                          │  │OpenAI  │ │ Anthropic │ │
                          │  │  API   │ │   /Other  │ │
                          │  └────────┘ └───────────┘ │
                          └───────────────────────────┘
```

### 15.2 关键设计决策

1. **多进程架构**: app-server 与 exec-server 分离，支持远程执行和跨 OS 沙箱
2. **双构建系统**: Cargo（开发）+ Bazel（发布），利用各自的优势
3. **Rust 2024 Edition**: 使用最新 Rust 特性
4. **150+ crate 工作空间**: 极细粒度的模块化，每个功能点都有独立的 crate
5. **扩展优先架构**: 通过 ext/ 系统实现功能可插拔性
6. **Guardian 安全系统**: 内置安全审查机制
7. **上下文硬约束**: 严格的 token 预算管理
8. **多模型支持**: OpenAI 原生 + Anthropic + Ollama + LM Studio + AWS Bedrock
9. **MCP 协议**: 通过 Model Context Protocol 集成外部工具
10. **多平台沙箱**: 每个平台使用最适合的沙箱技术

### 15.3 代码规模估算

| 层级 | 估算 |
|------|------|
| Rust 源文件总数 | 2,500+ |
| Rust crates | 150+ |
| 核心 crate 文件数 | 498+ |
| Python SDK 文件数 | 80+ |
| TypeScript SDK 文件数 | 50+ |
| 文档页数 | 15 |
| CI/CD 工作流 | 多个（.github/workflows/） |

---

> **注意**: 此分析基于 `codex-rust-v0.155.1` 版本快照。Codex CLI 是一个活跃开发的项目，架构和组件可能在新版本中有所变化。详细的最新信息请参考 [官方文档](https://developers.openai.com/codex) 和 [GitHub 仓库](https://github.com/openai/codex)。