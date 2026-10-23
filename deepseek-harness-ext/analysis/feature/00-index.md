# DeepSeek Harness 功能分析报告

本目录包含对 `deepseek-harness` 代码库的核心功能分析。

## 报告索引

| 文件 | 主题 | 摘要 |
|------|------|------|
| [01-dynamic-workflow.md](./01-dynamic-workflow.md) | 动态工作流 (Dynamic Workflow) | 分析 deepseek-harness 是否支持动态工作流创建与执行 |
| [02-subagent.md](./02-subagent.md) | 子代理 (Subagent) | 分析 deepseek-harness 是否支持子代理生成与管理 |
| [03-file-input-output.md](./03-file-input-output.md) | 文件输入/输出 | 分析对话中是否能输入文件、输出文件 |
| [04-remote-upload-api.md](./04-remote-upload-api.md) | 远程上传接口 | 分析是否有接口能远程上传 skill 和文件 |
| [05-mcp.md](./05-mcp.md) | MCP (Model Context Protocol) | 分析 MCP 客户端桥接支持 (传输、工具同步、重连) |
| [06-credential-vaults.md](./06-credential-vaults.md) | Credential Vaults | 分析凭据管理系统 (CredentialProvider, AuthorizationService) |
| [07-agent-teams.md](./07-agent-teams.md) | Agent Teams (实验性) | 分析实验性的 Agent Teams 功能 — 持久化 roster, mailbox, task board |
| [08-skill-system.md](./08-skill-system.md) | Skill 系统 | 分析 Skill 的架构、注册、加载、调用方式及是否支持远程上传 |
| [09-sandbox.md](./09-sandbox.md) | Sandbox 系统 | 分析进程文件沙箱的架构、模式、多平台后端、升级机制及消费者集成 |
| [10-e2b-sandbox.md](./10-e2b-sandbox.md) | E2B 远程沙箱 | 分析 E2B 远程沙箱的机制和使用 — 接缝替换、SDK handle、原子写入、环境隔离、终止阶梯 |

## 功能总结

| 功能 | 支持状态 | 关键包 |
|------|----------|--------|
| Dynamic Workflow | **✅ 支持** | `packages/workflow/workflow/` |
| Subagent | **✅ 支持** | `packages/subagent/subagent/` |
| 文件输入 (对话上传) | **✅ 支持** | `packages/client/file-upload/`, `packages/attachment/` |
| 文件输出 (对话返回) | **✅ 支持** | `packages/client/ui-deliverables/`, `packages/attachment/` |
| 远程上传文件 | **✅ 支持** | `packages/client/file-upload/` (HTTP API) |
| 远程上传 Skill | **✅ Provider扩展** | `packages/skill/skill/` (Provider 模式), 详见 08-skill-system.md |
| Skill 系统 (完整分析) | **✅ 完整** | `packages/skill/skill/`, `packages/skill/skill-filesystem/`, `packages/skill/tool-skill/` |
| MCP 客户端 | **✅ 完整支持** | `packages/mcp/mcp-client/` |
| MCP 传输 (stdio/HTTP) | **✅ 支持** | `packages/mcp/mcp-client/src/transport.ts` |
| MCP 自动重连 | **✅ 支持** | `packages/mcp/mcp-client/src/connection.ts` |
| MCP Resources/Prompts | **❌ 不支持** | 延期实现 (见 README limitations) |
| Credential Vault (通用) | **✅ 支持** | `packages/credentials/credentials/`, `packages/credentials/credentials-local/` |
| Authorization Flows | **✅ 支持** | `packages/credentials/authorization/` |
| MCP ↔ Credentials 集成 | **⚠️ 间接** | MCP 使用 `!!js` + env vars, 非直接 CredentialRef |
| Sandbox 系统 | **✅ 完整** | `packages/sandbox/sandbox/`, `sandbox-local/`, `sandbox-policy/`, `sandbox-windows-acl/` |
| E2B 远程沙箱 | **⚠️ 实验性 POC** | `packages/e2b/e2b/`, `fs-e2b/`, `subprocess-e2b/` |
| Agent Teams | **⚠️ 实验性** | `packages/experimental/agent-team/` |

## 分析日期

2026-09-16
