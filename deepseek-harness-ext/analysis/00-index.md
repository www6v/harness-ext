# DeepSeek Harness 对外 API 接口总览

## 文档索引

| 文档 | 说明 |
|------|------|
| [01-project-overview.md](./01-project-overview.md) | 项目概览与架构 |
| [02-cli-api.md](./02-cli-api.md) | CLI 命令行接口 |
| [03-typert-rpc-api.md](./03-typert-rpc-api.md) | Typert RPC 接口（Web/浏览器 API，**核心**） |
| [04-sdk-api.md](./04-sdk-api.md) | TypeScript SDK JSON-RPC 接口 |
| [05-acp-api.md](./05-acp-api.md) | ACP (Agent Client Protocol) 接口 |
| [06-webhook-api.md](./06-webhook-api.md) | Webhook HTTP 接口 |
| [07-python-sdk-api.md](./07-python-sdk-api.md) | Python SDK 接口 |

## 接口矩阵

| 接口类型 | 协议 | 端口/路径 | 认证 | 用途 |
|----------|------|-----------|------|------|
| **CLI** | 进程 argv | — | — | 命令行启动和管理 |
| **Typert RPC** | HTTP + WebSocket | `:3080/api` | 浏览器 Token | Web UI 核心 API |
| **SDK JSON-RPC** | stdio | — | 本地进程 | TypeScript 编程接口 |
| **ACP** | stdio | — | 本地进程 | IDE/CI 集成接口 |
| **Webhook** | HTTP POST | 可配置路径 | HMAC-SHA256 | 外部事件触发 |
| **Python SDK** | 子进程封装 | — | 本地进程 | Python 编程接口 |

## 统计

| 类别 | 数量 |
|------|------|
| Typert RPC 一元端点 | ~70+ |
| Typert RPC 流式端点 | ~5 |
| HTTP Fetch 路由 | ~7 |
| WebSocket 路由 | 1 |
| SDK 请求方法 | 3 |
| SDK 通知方法 | 4 |
| ACP 请求方法 | 9 |
| ACP 通知方法 | 2 |
| CLI 子命令 | 3 |
| 事件流事件类型 | ~17 |

## 接口选择指南

### 场景 → 推荐接口

| 场景 | 推荐接口 | 理由 |
|------|---------|------|
| 使用浏览器 UI | Typert RPC | Web UI 默认方式 |
| 简单脚本自动化 | SDK (TypeScript/Python) | 最简单的集成方式 |
| IDE 插件开发 | ACP | 完整会话管理 + MCP 支持 |
| CI/CD 集成 | ACP 或 SDK | 无头运行 |
| GitHub 事件触发 | Webhook | 被动接收事件 |
| 复杂自动化流程 | ACP | 会话恢复、配置变更 |
| 嵌入其他应用 | SDK | 子进程隔离、清晰 API |

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      外部接口层                              │
├──────────┬──────────┬──────────┬──────────┬────────────────┤
│  CLI     │  Web UI  │   SDK    │   ACP    │   Webhook      │
│  (argv)  │(Typert   │(JSON-RPC │(JSON-RPC │  (HTTP POST)   │
│          │ RPC)     │ stdio)   │ stdio)   │                │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴───────┬────────┘
     │          │          │          │              │
     ▼          ▼          ▼          ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                    DeepSeek Harness Host                     │
├─────────────────────────────────────────────────────────────┤
│  Cordis Plugin Framework (万物皆插件)                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Session │ │   LLM   │ │  Shell  │ │   FS    │ ...      │
│  │ Manager │ │ Runtime │ │Runtime  ││Runtime  │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────────────────┘
```
