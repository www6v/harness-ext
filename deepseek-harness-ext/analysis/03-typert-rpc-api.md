# Typert RPC 接口（Web/浏览器 API）

## 概述

DeepSeek Harness 的核心 API 基于自研的 **Typert RPC 协议**，通过 HTTP + WebSocket 对外暴露。这是 Web UI（浏览器前端）与 Host 后端通信的主要方式。

- **协议**: Typert — 类型化的、生成式的、命名空间作用域的远程过程调用
- **传输层**: HTTP/1.1（一元调用） + WebSocket（流式调用）
- **源码位置**: `packages/api/gateway/`、`packages/client/connection/`

## 网络架构

### HTTP 服务器

- **包**: `@deepseek-ai/dsh-host-webserver`（`packages/host/webserver/`）
- **实现**: 原生 `node:http.createServer()`
- **默认地址**: `http://127.0.0.1:3080`
- **特性**: 可选 gzip 压缩、路由注册、WebSocket 升级分发

### URL 路由总览

| 路径 | 类型 | 说明 |
|------|------|------|
| `/api` | HTTP 前缀路由 | 主 RPC 通道（一元调用） |
| `/api/remote.mux` | WebSocket 升级路由 | 多路复用流（流式调用 + 事件流） |
| `/api/session/uploadFileBinary` | HTTP POST | 二进制文件上传 |
| `/api/file` | HTTP GET/HEAD | 附件文件服务 |
| `/api/session.export` | HTTP GET/HEAD | 会话日志导出 |
| `/api/present.host` | HTTP GET | 桌面工作区信息 |
| `/api/present.open` | HTTP POST | 打开交付文件 |
| `/plugins` | HTTP 前缀路由 | 插件资源服务 |
| `/plugins/events` | SSE | HMR 模块图更新事件 |
| `/*` | 回退路由 | SPA 静态资源 |

## RPC 协议格式

### 一元调用（HTTP POST `/api`）

**请求**:
```json
{
  "type": "client-request",
  "rpcId": "uuid-string",
  "method": "namespace/methodName",
  "payload": { "args": { ... } }
}
```

**响应**:
```json
{
  "type": "server-response",
  "rpcId": "uuid-string",
  "result": {
    "ok": true,
    "value": { ... }
  }
}
```

**错误响应**:
```json
{
  "type": "server-response",
  "rpcId": "uuid-string",
  "result": {
    "ok": false,
    "error": {
      "code": "gateway/bad-request",
      "message": "...",
      "details": { ... }
    }
  }
}
```

### 流式调用（WebSocket `/api/remote.mux`）

**客户端 → 服务端**:
```json
{ "type": "open", "streamId": "uuid", "endpoint": "session/follow", "payload": { ... } }
{ "type": "cancel", "streamId": "uuid" }
```

**服务端 → 客户端**:
```json
{ "type": "item", "streamId": "uuid", "value": { ... } }
{ "type": "end", "streamId": "uuid" }
{ "type": "error", "streamId": "uuid", "error": { "code": "...", "message": "..." } }
```

## 命名空间 API 详情

### 1. `session` — 会话管理

**包**: `@deepseek-ai/dsh-api-session-controller`（`packages/api/session-controller/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `session/list` | 一元 | 列出所有可见会话 |
| `session/search` | 一元 | 搜索会话内容 |
| `session/create` | 一元 | 创建新会话 |
| `session/prompt` | 一元 | 向会话发送提示 |
| `session/cancel` | 一元 | 取消当前活跃操作 |
| `session/rename` | 一元 | 重命名会话 |
| `session/fork` | 一元 | 从已完成的轮次派生新会话 |
| `session/page` | 一元 | 读取会话历史分页 |
| `session/selectModel` | 一元 | 选择会话使用的模型 |
| `session/modelCatalog` | 一元 | 获取可用模型目录 |
| `session/attachment` | 一元 | 读取会话附件（图片等） |
| `session/updateQueue` | 一元 | 修改待处理的队列项 |
| `session/openWorkspacePath` | 一元 | 在桌面打开/显示工作区路径 |
| `session/canOpenWorkspacePath` | 一元 | 检查是否支持打开路径 |
| `session/follow` | **流式** | 实时跟踪会话事件流 |
| `session/assistantStream` | **流式** | 实时跟踪助手输出流 |
| `session/control` | **流式** | 实时控制帧流 |

### 2. `workspace` — 工作区管理

**包**: `@deepseek-ai/dsh-api-workspace-controller`（`packages/api/workspace-controller/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `workspace/create` | 一元 | 创建工作区 |
| `workspace/rename` | 一元 | 重命名工作区 |
| `workspace/delete` | 一元 | 删除工作区注册 |
| `workspace/insertBefore` | 一元 | 调整工作区排序 |
| `workspace/insertSessionBefore` | 一元 | 在工作区内调整会话排序 |
| `workspace/archiveSession` | 一元 | 归档（隐藏）会话 |
| `workspace/follow` | **流式** | 实时跟踪工作区变更 |

### 3. `directoryPicker` — 目录选择

**包**: `@deepseek-ai/dsh-api-workspace-controller`（`packages/api/workspace-controller/directory-picker.ts`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `directoryPicker/pick` | 一元 | 打开原生目录选择器 |
| `directoryPicker/list` | 一元 | 列出目录内容 |
| `directoryPicker/createDirectory` | 一元 | 创建新目录 |

### 4. `workspaceFiles` — 工作区文件

**包**: `@deepseek-ai/dsh-api-workspace-files`（`packages/api/workspace-files/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `workspaceFiles/read` | 一元 | 读取文件的文本分页 |
| `workspaceFiles/readBytes` | 一元 | 读取文件的字节窗口（base64） |
| `workspaceFiles/readAll` | 一元 | 读取完整文件内容 |
| `workspaceFiles/readRelated` | 一元 | 读取相对路径关联文件 |
| `workspaceFiles/stat` | 一元 | 获取文件元信息 |
| `workspaceFiles/list` | 一元 | 列出目录内容 |
| `workspaceFiles/changes` | **流式** | 实时文件变更观察 |

### 5. `settings` — 设置管理

**包**: `@deepseek-ai/dsh-api-settings-controller`（`packages/api/settings-controller/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `settings/describe` | 一元 | 描述所有设置命名空间 |
| `settings/canOpenAgentPresetDirectory` | 一元 | 检查能否打开预设目录 |
| `settings/update` | 一元 | 合并更新设置 |
| `settings/replace` | 一元 | 整体替换设置 |
| `settings/mutate` | 一元 | 路径级编辑操作 |
| `settings/openSettingsDocument` | 一元 | 在编辑器中打开设置文件 |
| `settings/openAgentPresetDirectory` | 一元 | 打开 Agent 预设目录 |

### 6. `credentials` — 凭据管理

**包**: `@deepseek-ai/dsh-api-settings-controller`（`packages/api/settings-controller/credentials.ts`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `credentials/describe` | 一元 | 描述凭据引用信息 |
| `credentials/set` | 一元 | 设置凭据值 |
| `credentials/unset` | 一元 | 清除凭据值 |

### 7. `llm` — LLM 运行时

**包**: `@deepseek-ai/dsh-llm`（`packages/llm/llm/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `llm/listProviders` | 一元 | 列出已注册的 LLM Provider |
| `llm/listConfigurableProviders` | 一元 | 列出可配置的 Provider 目录 |
| `llm/discoverModels` | 一元 | 探测 Provider 端点可用模型 |

### 8. `goals` — 目标管理

**包**: `@deepseek-ai/dsh-goal`（`packages/goal/goal/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `goals/get` | 一元 | 获取当前目标状态 |
| `goals/create` | 一元 | 创建新目标 |
| `goals/edit` | 一元 | 编辑目标 |
| `goals/pause` | 一元 | 暂停目标 |
| `goals/resume` | 一元 | 恢复目标 |
| `goals/complete` | 一元 | 标记目标完成 |
| `goals/clear` | 一元 | 清除目标 |

### 9. `commands` — 命令运行时

**包**: `@deepseek-ai/dsh-commands`（`packages/interaction/commands/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `commands/list` | 一元 | 列出有效的斜杠命令 |
| `commands/execute` | 一元 | 解析并执行斜杠命令 |

### 10. `agentPresets` — Agent 预设

**包**: `@deepseek-ai/dsh-agent-presets`（`packages/preset/agent-presets/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `agentPresets/list` | 一元 | 列出可用预设 |
| `agentPresets/read` | 一元 | 读取预设文档 |
| `agentPresets/copy` | 一元 | 复制预设 |
| `agentPresets/deletePreset` | 一元 | 删除预设 |
| `agentPresets/select` | 一元 | 选择预设 |

### 11. `subagents` — 子 Agent

**包**: `@deepseek-ai/dsh-subagent`（`packages/subagent/subagent/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `subagents/list` | 一元 | 列出子 Agent 目录 |
| `subagents/prompt` | 一元 | 向子 Agent 发送提示 |
| `subagents/interruptByParent` | 一元 | 通过父级中断子 Agent |

### 12. `fileUploads` — 文件上传

**包**: `@deepseek-ai/dsh-client-file-upload`（`packages/client/file-upload/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `fileUploads/upload` | 一元 | 上传编码文件（base64） |

另外通过 HTTP POST 提供二进制上传：
- **路径**: `POST /api/session/uploadFileBinary?sessionId=...&name=...`
- **Content-Type**: `application/octet-stream`
- **响应**: `{ receiptId, file: FileAttachmentRef }`

### 13. `skills` — 技能目录

**包**: `@deepseek-ai/dsh-api-session-controller`（`packages/api/session-controller/skill-catalog.ts`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `skills/list` | 一元 | 列出可用技能 |

### 14. `fileReferences` — 文件引用

**包**: `@deepseek-ai/dsh-api-session-controller`（`packages/api/session-controller/file-references.ts`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `fileReferences/resolve` | 一元 | 解析文件引用 |

### 15. `sessionFeedback` — 会话反馈

**包**: `@deepseek-ai/dsh-command-feedback`（`packages/feedback/command-feedback/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `sessionFeedback/record` | 一元 | 记录会话反馈 |

### 16. `messageFeedback` — 消息反馈

**包**: `@deepseek-ai/dsh-message-feedback`（`packages/feedback/message-feedback/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `messageFeedback/list` | 一元 | 列出消息反馈 |
| `messageFeedback/put` | 一元 | 创建/更新消息反馈 |
| `messageFeedback/delete` | 一元 | 删除消息反馈 |

### 17. `sessionReferenceResolver` — 会话引用

**包**: `@deepseek-ai/dsh-session-reference`（`packages/context/session-reference/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `sessionReferenceResolver/candidates` | 一元 | 导出会话引用候选 |

### 18. `agentTeams` — Agent 团队（实验性）

**包**: `@deepseek-ai/dsh-agent-team`（`packages/experimental/agent-team/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `agentTeams/view` | 一元 | 查看团队状态 |
| `agentTeams/createTask` | 一元 | 创建团队任务 |
| `agentTeams/updateTask` | 一元 | 更新团队任务 |

### 19. `dynamicCordisRunner` — 动态 Cordis 运行时

**包**: `@deepseek-ai/dsh-cordis-host-runner`（`packages/extensions/cordis-host-runner/`）

| 端点 | 模式 | 说明 |
|------|------|------|
| `dynamicCordisRunner/undefineFromPanel` | 一元 | 卸载插件 |
| `dynamicCordisRunner/runHostHalf` | 一元 | 运行宿主侧代码 |
| `dynamicCordisRunner/getClientCode` | 一元 | 获取客户端代码 |
| `dynamicCordisRunner/resolveRequestRun` | 一元 | 解析请求运行 |
| `dynamicCordisRunner/settleUserRun` | 一元 | 结算用户运行 |
| `dynamicCordisRunner/stopFromPanel` | 一元 | 停止插件 |
| `dynamicCordisRunner/inventory` | 一元 | 获取插件清单 |
| `dynamicCordisRunner/reportRenderFailure` | 一元 | 报告渲染失败 |
| `dynamicCordisRunner/reportClientGuardFailure` | 一元 | 报告客户端守卫失败 |
| `dynamicCordisRunner/invoke` | 一元 | 调用插件 |

## 事件流（$events）

通过 WebSocket `/api/remote.mux` 的 `$events` 逻辑端点，Host 向 Client 推送实时事件：

| 事件 | 类型 | 说明 |
|------|------|------|
| `api-session/activity` | emit | 会话活动更新 |
| `api-session/added` | emit | 会话已添加 |
| `api-session/removed` | emit | 会话已移除 |
| `api-session/status` | emit | 会话状态变更 |
| `api-session/error` | emit | 会话错误 |
| `agent-preset/selected` | emit | Agent 预设已选择 |
| `commands/change` | emit | 命令状态变更 |
| `credentials/reference-updated` | emit | 凭据引用更新 |
| `goal/activation-changed` | emit | 目标激活状态变更 |
| `llm/adapters-updated` | emit | LLM 适配器列表更新 |
| `settings/document-updated` | emit | 设置文档更新 |
| `cordis/request-run` | emit | Cordis 运行请求 |
| `cordis/dynamic-package` | emit | 动态 Cordis 包 |
| `cordis/dynamic-retract` | emit | 动态 Cordis 撤回 |
| `approval/request` | **waterfall** | 工具审批请求（Client 可响应） |
| `user-questions/request` | **waterfall** | 用户问题（Client 可响应） |

## 错误码

| 错误码 | 说明 |
|--------|------|
| `gateway/bad-request` | 请求参数无效 |
| `gateway/cancelled` | 调用被取消 |
| `gateway/internal` | 内部错误 |
| `gateway/ambiguous-endpoint` | 端点歧义 |
| `gateway/arguments-invalid` | 参数校验失败 |
| `gateway/context-*` | 上下文解析错误 |
| `gateway/invocation-unavailable` | 调用不可用 |
| `gateway/input-invalid` | 输入无效 |
