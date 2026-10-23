# DeepSeek Harness 项目概览

## 项目简介

**DeepSeek Harness** (`dsh`) 是由 [DeepSeek AI](https://deepseek.com) 开发的开源 AI Agent 框架。项目基于 **"万物皆插件"（everything-is-a-plugin）** 架构，使用 [Cordis](https://github.com/cordiverse/cordis) 插件框架构建。

- **版本**: 0.1.5-rc.2（开发者预览版）
- **协议**: MIT
- **语言**: TypeScript / ESM
- **运行时**: Node.js ^22.19 || >=24
- **包管理**: pnpm 11.7.0（monorepo，267 个 npm 包）

## 项目结构

```
deepseek-harness/
├── apps/              # 4 个应用程序
│   ├── cli/           # CLI 命令行工具（dsh 命令）
│   ├── web/           # Web 前端（React SPA）
│   ├── desktop/       # Electron 桌面应用
│   └── desktop-host/  # Electron 宿主进程
├── packages/          # 核心包（50 个分组，267 个包）
├── native/            # 原生系统插件（Landlock、flock）
├── python/            # Python SDK
├── vendor/            # 供应商依赖（Cordis 框架）
├── website/           # VitePress 文档网站
├── docs/              # 架构文档
├── scripts/           # 构建/CI 脚本
├── benchmarks/        # 性能基准测试
└── snapshots/         # 会话重放测试固件
```

## 核心架构

### 插件体系

项目基于 Cordis 框架，所有功能通过插件组合：

- **Profile（配置档）**：命名的插件层组合
- **Bundle（捆绑包）**：可安装的插件层
- **Service（服务）**：注入到共享上下文的业务能力
- **Events（事件）**：类型化的发布/订阅通信

### 已发布的 Profile

| Profile | 用途 |
|---------|------|
| `web` | Web UI（默认） |
| `headless` | 无头模式（CLI 单次任务） |
| `sdk` | SDK JSON-RPC 运行时 |
| `sdk-minimal` | 最小 SDK 运行时 |
| `acp` | Agent Client Protocol 运行时 |
| `desktop` | Electron 桌面应用（内部使用） |

## 对外接口总览

项目对外暴露了 **6 大类 API 接口**：

| 接口类型 | 协议 | 详见文档 |
|----------|------|----------|
| CLI 命令行接口 | 进程参数 | [02-cli-api.md](./02-cli-api.md) |
| Web/Typert RPC 接口 | HTTP + WebSocket | [03-typert-rpc-api.md](./03-typert-rpc-api.md) |
| SDK JSON-RPC 接口 | stdio JSON-RPC | [04-sdk-api.md](./04-sdk-api.md) |
| ACP 接口 | stdio JSON-RPC | [05-acp-api.md](./05-acp-api.md) |
| Webhook 接口 | HTTP POST | [06-webhook-api.md](./06-webhook-api.md) |
| Python SDK 接口 | 子进程 SDK | [07-python-sdk-api.md](./07-python-sdk-api.md) |
