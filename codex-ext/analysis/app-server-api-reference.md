# codex-app-server 接口参考

> 基于 codex-rust v0.155.1 源码分析

## 1. 协议概述

所有接口基于 **JSON-RPC 2.0** 协议，线格式如下：

```json
{"jsonrpc":"2.0","id":<RequestId>,"method":"<method_name>","params":{...}}
```

接口定义在 `app-server-protocol/src/protocol/common.rs` 中通过宏声明：
- `client_request_definitions!{...}` → `enum ClientRequest`（按 `method` 标记）
- `server_request_definitions!{...}` → `enum ServerRequest`
- `server_notification_definitions!{...}` → `enum ServerNotification`
- `client_notification_definitions!{...}` → `enum ClientNotification`

所有参数/响应类型结构体位于 `app-server-protocol/src/protocol/v2/` 目录下，按域分文件。

---

## 2. 客户端 → 服务器请求（ClientRequest，~120 个方法）

### 2.1 连接 / 初始化

| 方法 | 参数 | 响应 | 说明 |
|---|---|---|---|
| `initialize` | `InitializeParams` | `InitializeResponse` | 必须在连接上的任何其他方法之前调用 |

### 2.2 服务器自省

| 方法 | 说明 | 标记 |
|---|---|---|
| `server/diagnostics` | 服务器诊断信息 | 实验性 |
| `userVerification/status` | 用户验证状态 | 实验性 |
| `userVerification/enroll` | 用户验证注册 | 实验性 |
| `userVerification/delete` | 删除用户验证 | 实验性 |
| `userVerification/verify` | 验证用户 | 实验性 |
| `userVerification/cancel` | 取消验证 | 实验性 |
| `config/read` | 读取配置 | |
| `config/value/write` | 写入配置值 | |
| `config/batchWrite` | 批量写入配置 | |
| `configRequirements/read` | 读取配置要求 | |
| `externalAgentConfig/detect` | 检测外部代理配置 | |
| `externalAgentConfig/import` | 导入外部代理配置 | |
| `externalAgentConfig/recordHistory` | 记录历史 | |
| `externalAgentConfig/readHistories` | 读取历史 | |
| `experimentalFeature/list` | 列出实验性功能 | |
| `experimentalFeature/enablement/set` | 设置实验性功能启用状态 | |
| `modelProvider/capabilities/read` | 读取模型提供者能力 | |
| `windowsSandbox/readiness` | Windows 沙箱就绪状态 | |
| `windowsSandbox/setupStart` | 启动 Windows 沙箱设置 | |
| `mock/experimentalMethod` | 测试用模拟方法 | 仅测试 |

### 2.3 账户 / 认证

| 方法 | 说明 |
|---|---|
| `account/login/start` | 开始登录 |
| `account/login/cancel` | 取消登录 |
| `account/logout` | 登出 |
| `account/read` | 读取账户信息 |
| `account/bedrock/discover` | 发现 Bedrock |
| `account/bedrock/setup` | 设置 Bedrock |
| `account/rateLimits/read` | 读取速率限制 |
| `account/rateLimitResetCredit/consume` | 消耗速率限制重置额度 |
| `account/usage/read` | 读取使用量 |
| `account/workspaceMessages/read` | 读取工作区消息 |
| `account/sendAddCreditsNudgeEmail` | 发送添加积分提醒邮件 |
| `getAuthStatus` | **已弃用** — 获取认证状态 |
| `getConversationSummary` | **已弃用** — 获取对话摘要 |
| `gitDiffToRemote` | **已弃用** — Git diff 到远程 |

### 2.4 远程控制（全部实验性）

| 方法 | 说明 |
|---|---|
| `remoteControl/enable` | 启用远程控制 |
| `remoteControl/disable` | 禁用远程控制 |
| `remoteControl/status/read` | 读取远程控制状态 |
| `remoteControl/pairing/start` | 开始配对 |
| `remoteControl/pairing/status` | 配对状态 |
| `remoteControl/client/list` | 列出客户端 |
| `remoteControl/client/revoke` | 撤销客户端 |

### 2.5 环境（全部实验性）

| 方法 | 说明 |
|---|---|
| `environment/add` | 添加环境 |
| `environment/info` | 环境信息 |
| `environment/status` | 环境状态 |

### 2.6 文件系统

| 方法 | 说明 |
|---|---|
| `fs/readFile` | 读取文件 |
| `fs/writeFile` | 写入文件 |
| `fs/createDirectory` | 创建目录 |
| `fs/getMetadata` | 获取元数据 |
| `fs/readDirectory` | 读取目录 |
| `fs/remove` | 删除文件/目录 |
| `fs/copy` | 复制文件/目录 |
| `fs/watch` | 监视文件变化 |
| `fs/unwatch` | 取消监视 |

### 2.7 线程 / 项目（最大一组）

**线程管理：**

| 方法 | 说明 |
|---|---|
| `thread/start` | 启动新线程 |
| `thread/resume` | 恢复线程 |
| `thread/fork` | 分叉线程 |
| `thread/archive` | 归档线程 |
| `thread/delete` | 删除线程 |
| `thread/unsubscribe` | 取消订阅线程 |
| `thread/unarchive` | 取消归档 |
| `thread/rollback` | 回滚线程 |
| `thread/revert` | 还原线程 |
| `thread/compact/start` | 启动压缩 |

**线程属性：**

| 方法 | 说明 |
|---|---|
| `thread/name/set` | 设置线程名称 |
| `thread/metadata/update` | 更新元数据 |
| `thread/settings/update` | 更新设置 |
| `thread/memoryMode/set` | 设置内存模式 |
| `memory/status` | 内存状态 |
| `memory/reset` | 重置内存 |

**线程目标：**

| 方法 | 说明 |
|---|---|
| `thread/goal/set` | 设置目标 |
| `thread/goal/get` | 获取目标 |
| `thread/goal/clear` | 清除目标 |

**线程队列（实验性）：**

| 方法 | 说明 |
|---|---|
| `thread/queue/add` | 添加到队列 |
| `thread/queue/list` | 列出队列 |
| `thread/queue/update` | 更新队列项 |
| `thread/queue/delete` | 删除队列项 |
| `thread/queue/reorder` | 重新排序 |
| `thread/queue/start` | 启动队列 |

**线程附件：**

| 方法 | 说明 |
|---|---|
| `thread/attachment/add` | 添加附件 |
| `thread/attachment/list` | 列出附件 |
| `thread/attachment/remove` | 移除附件 |

**线程分区（注意：线名称为 `threadSection/*`）：**

| 方法 | 说明 |
|---|---|
| `thread/section/move` | 移动分区 |
| `thread/section/list` | 列出分区 |
| `thread/section/create` | 创建分区 |
| `thread/section/update` | 更新分区 |
| `thread/section/delete` | 删除分区 |

**线程交互：**

| 方法 | 说明 |
|---|---|
| `thread/shellCommand` | 执行 shell 命令 |
| `thread/approveGuardianDeniedAction` | 批准被 Guardian 拒绝的操作 |

**线程后台终端（实验性）：**

| 方法 | 说明 |
|---|---|
| `thread/backgroundTerminals/clean` | 清理后台终端 |
| `thread/backgroundTerminals/list` | 列出后台终端 |
| `thread/backgroundTerminals/terminate` | 终止后台终端 |

**线程引出（实验性）：**

| 方法 | 说明 |
|---|---|
| `thread/increment_elicitation` | 递增引出计数 |
| `thread/decrement_elicitation` | 递减引出计数 |

**线程注入：**

| 方法 | 说明 |
|---|---|
| `thread/inject_items` | 注入项目 |

**线程查询：**

| 方法 | 说明 |
|---|---|
| `thread/list` | 列出所有线程 |
| `thread/loaded/list` | 列出已加载线程 |
| `thread/read` | 读取线程详情 |
| `thread/turns/list` | 列出线程的 turn |
| `thread/items/list` | 列出线程项目 |
| `thread/timeline/list` | 列出时间线 |
| `thread/search` | 搜索线程 |
| `thread/searchOccurrences` | 搜索出现次数 |

**项目管理（实验性）：**

| 方法 | 说明 |
|---|---|
| `project/list` | 列出项目 |
| `project/read` | 读取项目 |
| `project/create` | 创建项目 |
| `project/import` | 导入项目 |
| `project/update` | 更新项目 |
| `project/move` | 移动项目 |
| `project/delete` | 删除项目 |

### 2.8 技能 / 钩子 / 插件 / 应用 / 市场

| 方法 | 说明 |
|---|---|
| `skills/list` | 列出技能 |
| `skills/extraRoots/set` | 设置额外技能根目录 |
| `skills/config/write` | 写入技能配置 |
| `hooks/list` | 列出钩子 |
| `model/list` | 列出模型 |
| `permissionProfile/list` | 列出权限配置 |
| `collaborationMode/list` | 列出协作模式 |
| `plugin/list` | 列出插件 |
| `plugin/search` | 搜索插件 |
| `plugin/installed` | 已安装插件 |
| `plugin/reconcile` | 调和插件 |
| `plugin/read` | 读取插件详情 |
| `plugin/install` | 安装插件 |
| `plugin/uninstall` | 卸载插件 |
| `plugin/skill/read` | 读取插件技能 |
| `plugin/share/save` | 保存插件分享 |
| `plugin/share/updateTargets` | 更新分享目标 |
| `plugin/share/list` | 列出分享 |
| `plugin/share/checkout` | 检出分享 |
| `plugin/share/delete` | 删除分享 |
| `marketplace/add` | 添加到市场 |
| `marketplace/remove` | 从市场移除 |
| `marketplace/upgrade` | 升级市场项 |
| `app/read` | 读取应用 |
| `app/list` | 列出应用 |
| `app/installed` | 已安装应用 |

### 2.9 Turn / 审查 / 实时

**Turn 管理：**

| 方法 | 说明 |
|---|---|
| `turn/start` | 启动 turn |
| `turn/steer` | 引导 turn |
| `turn/interrupt` | 中断 turn |
| `turn/settings/update` | 更新 turn 设置 |

**审查：**

| 方法 | 说明 |
|---|---|
| `review/start` | 启动审查 |

**实时（实验性）：**

| 方法 | 说明 |
|---|---|
| `thread/realtime/start` | 启动实时会话 |
| `thread/realtime/appendAudio` | 追加音频 |
| `thread/realtime/appendText` | 追加文本 |
| `thread/realtime/appendSpeech` | 追加语音 |
| `thread/realtime/stop` | 停止实时会话 |
| `thread/realtime/listVoices` | 列出可用语音 |

### 2.10 MCP

| 方法 | 说明 |
|---|---|
| `mcpServer/oauth/login` | MCP 服务器 OAuth 登录 |
| `config/mcpServer/reload` | 重新加载 MCP 服务器配置 |
| `mcpServerStatus/list` | 列出 MCP 服务器状态 |
| `mcpServer/resource/read` | 读取 MCP 服务器资源 |
| `mcpServer/tool/call` | 调用 MCP 服务器工具 |
| `mcpServer/event/stream/start` | 启动事件流（实验性） |
| `mcpServer/event/stream/stop` | 停止事件流（实验性） |

### 2.11 进程

| 方法 | 说明 |
|---|---|
| `command/exec` | 一次性命令执行 |
| `command/exec/write` | 写入命令 stdin |
| `command/exec/terminate` | 终止命令 |
| `command/exec/resize` | 调整命令终端大小 |
| `process/spawn` | 生成进程（实验性） |
| `process/writeStdin` | 写入进程 stdin（实验性） |
| `process/kill` | 杀死进程（实验性） |
| `process/resizePty` | 调整 PTY 大小（实验性） |

### 2.12 模糊搜索

| 方法 | 说明 |
|---|---|
| `fuzzyFileSearch` | 模糊文件搜索 |
| `fuzzyFileSearch/sessionStart` | 启动搜索会话（实验性） |
| `fuzzyFileSearch/sessionUpdate` | 更新搜索会话（实验性） |
| `fuzzyFileSearch/sessionStop` | 停止搜索会话（实验性） |

### 2.13 反馈

| 方法 | 说明 |
|---|---|
| `feedback/upload` | 上传反馈 |

---

## 3. 服务器 → 客户端请求（ServerRequest，10 个方法）

服务器可以*调用*客户端以获得批准/输入：

| 方法 | 说明 |
|---|---|
| `item/commandExecution/requestApproval` | 请求批准 shell 命令 |
| `item/fileChange/requestApproval` | 请求批准文件补丁 |
| `item/tool/requestUserInput` | 请求用户提供工具输入 |
| `mcpServer/elicitation/request` | MCP 引出请求（RMCP） |
| `item/permissions/requestApproval` | 请求额外权限 |
| `item/tool/call` | 在客户端上执行的动态工具调用 |
| `account/chatgptAuthTokens/refresh` | 刷新 ChatGPT 认证令牌 |
| `attestation/generate` | 生成平台证明 |
| `currentTime/read` | 从客户端时钟读取时间（实验性） |
| `item/applyPatchApproval` | **旧版**（v1）应用补丁批准 |
| `item/execCommandApproval` | **旧版**（v1）执行命令批准 |

---

## 4. 服务器 → 客户端通知（ServerNotification，~60 个事件）

### 4.1 生命周期

| 通知 | 说明 |
|---|---|
| `thread/started` | 线程已启动 |
| `thread/status/changed` | 线程状态变更 |
| `thread/archived` | 线程已归档 |
| `thread/deleted` | 线程已删除 |
| `thread/unarchived` | 线程已取消归档 |
| `thread/closed` | 线程已关闭 |
| `thread/reverted` | 线程已还原 |
| `thread/name/updated` | 线程名称更新 |
| `thread/project/updated` | 线程项目更新 |
| `thread/settings/updated` | 线程设置更新 |
| `thread/tokenUsage/updated` | 线程令牌使用量更新 |
| `thread/compacted` | 线程已压缩 |

### 4.2 Turn 与项目

| 通知 | 说明 |
|---|---|
| `turn/started` | Turn 已启动 |
| `turn/completed` | Turn 已完成 |
| `turn/diff/updated` | Turn diff 更新 |
| `turn/plan/updated` | Turn 计划更新 |
| `item/started` | 项目已启动 |
| `item/completed` | 项目已完成 |
| `item/agentMessage/delta` | 代理消息增量 |
| `item/plan/delta` | 项目计划增量 |
| `item/mcpToolCall/progress` | MCP 工具调用进度 |
| `item/commandExecution/outputDelta` | 命令执行输出增量 |
| `item/commandExecution/terminalInteraction` | 命令执行终端交互 |
| `item/fileChange/outputDelta` | 文件变更输出增量 |
| `item/fileChange/patchUpdated` | 文件变更补丁更新 |
| `item/autoApprovalReview/started` | 自动审批审查启动 |
| `item/autoApprovalReview/completed` | 自动审批审查完成 |
| `autoApprovalReview/strictReviewRequired` | 需要严格审查 |
| `item/reasoning/summaryTextDelta` | 推理摘要文本增量 |
| `item/reasoning/summaryPartAdded` | 推理摘要部分添加 |
| `item/reasoning/textDelta` | 推理文本增量 |

### 4.3 钩子

| 通知 | 说明 |
|---|---|
| `hook/started` | 钩子已启动 |
| `hook/completed` | 钩子已完成 |

### 4.4 实时（实验性）

| 通知 | 说明 |
|---|---|
| `thread/realtime/started` | 实时会话已启动 |
| `thread/realtime/itemAdded` | 实时项目添加 |
| `thread/realtime/item/started` | 实时项目启动 |
| `thread/realtime/item/transcript/delta` | 实时项目文本增量 |
| `thread/realtime/item/completed` | 实时项目完成 |
| `thread/realtime/transcript/delta` | 实时文本增量 |
| `thread/realtime/transcript/done` | 实时文本完成 |
| `thread/realtime/outputAudio/delta` | 实时输出音频增量 |
| `thread/realtime/sdp` | 实时 SDP |
| `thread/realtime/error` | 实时错误 |
| `thread/realtime/closed` | 实时会话关闭 |

### 4.5 进程

| 通知 | 说明 |
|---|---|
| `command/exec/outputDelta` | 命令执行输出增量 |
| `process/outputDelta` | 进程输出增量 |
| `process/exited` | 进程已退出 |

### 4.6 服务器请求

| 通知 | 说明 |
|---|---|
| `serverRequest/resolved` | 服务器请求已解决 |

### 4.7 MCP

| 通知 | 说明 |
|---|---|
| `mcpServer/oauthLogin/completed` | OAuth 登录完成 |
| `mcpServer/startupStatus/updated` | 启动状态更新 |
| `mcpServer/event/stream/notification` | 事件流通知 |

### 4.8 账户

| 通知 | 说明 |
|---|---|
| `account/updated` | 账户更新 |
| `account/rateLimits/updated` | 速率限制更新 |
| `account/login/completed` | 登录完成 |

### 4.9 应用 / 插件 / 远程

| 通知 | 说明 |
|---|---|
| `app/list/updated` | 应用列表更新 |
| `remoteControl/status/changed` | 远程控制状态变更 |
| `externalAgentConfig/import/progress` | 外部代理配置导入进度 |
| `externalAgentConfig/import/completed` | 外部代理配置导入完成 |

### 4.10 文件 / 技能

| 通知 | 说明 |
|---|---|
| `fs/changed` | 文件系统变更 |
| `skills/changed` | 技能变更 |
| `thread/attachment/updated` | 线程附件更新 |
| `thread/goal/updated` | 线程目标更新 |
| `thread/goal/cleared` | 线程目标清除 |
| `thread/queue/changed` | 线程队列变更 |
| `project/changed` | 项目变更 |

### 4.11 环境

| 通知 | 说明 |
|---|---|
| `thread/environment/connected` | 环境已连接 |
| `thread/environment/disconnected` | 环境已断开 |

### 4.12 模型 / 认证

| 通知 | 说明 |
|---|---|
| `model/rerouted` | 模型重新路由 |
| `model/verification` | 模型验证 |
| `modelProvider/authRecoveryStarted` | 认证恢复启动 |
| `modelProvider/authRecoveryCompleted` | 认证恢复完成 |
| `model/safetyBuffering/updated` | 安全缓冲更新 |
| `turn/moderationMetadata` | Turn 审核元数据 |

### 4.13 警告

| 通知 | 说明 |
|---|---|
| `error` | 错误 |
| `warning` | 警告 |
| `guardianWarning` | Guardian 警告 |
| `deprecationNotice` | 弃用通知 |
| `configWarning` | 配置警告 |
| `windows/worldWritableWarning` | Windows 全局可写警告 |
| `windowsSandbox/setupCompleted` | Windows 沙箱设置完成 |

### 4.14 模糊搜索

| 通知 | 说明 |
|---|---|
| `fuzzyFileSearch/sessionUpdated` | 搜索会话更新 |
| `fuzzyFileSearch/sessionCompleted` | 搜索会话完成 |

---

## 5. 客户端 → 服务器通知（ClientNotification）

仅**一个**变体：

| 通知 | 说明 |
|---|---|
| `Initialized` | 客户端在收到 initialize 响应后发送 |

---

## 6. 请求/响应类型源文件

所有参数/响应类型结构体位于 `app-server-protocol/src/protocol/v2/`：

```
account.rs    application.rs    apps.rs       attestation.rs    bedrock.rs
browser_use_config.rs  collaboration_mode.rs  command_exec.rs  computer_use_config.rs
config.rs     current_time.rs   diagnostics.rs  environment.rs
experimental_feature.rs  feedback.rs  fs.rs   hook.rs    item.rs   mcp.rs
memory.rs     model.rs          notification.rs  permissions.rs  plugin.rs
plugin_search.rs  process.rs  project.rs  realtime.rs  remote_control.rs
review.rs     shared.rs         thread.rs   thread_attachment.rs
thread_data.rs  thread_usage.rs  turn.rs    user_verification.rs
windows_sandbox.rs
```

每个结构体派生 `Serialize, Deserialize, Debug, Clone, PartialEq, JsonSchema, TS`，因此：
- JSON schema 固定文件写入 `app-server-protocol/schema/json/v2/*.json`（用于跨语言代码生成和一致性测试）
- TypeScript 声明输出到 `app-server-protocol/schema/typescript/`

v1 类型（`InitializeParams`、`InitializeResponse`、`ApplyPatchApproval*`、`ExecCommandApproval*`、`GetAuthStatus*`、`GetConversationSummary*` 等）位于 `protocol/v1.rs`。

---

## 7. 请求序列化作用域

每个 `ClientRequest` 声明一个**序列化作用域**，以便同一线程的冲突变更被序列化，而不相关的变更并发运行：

- `thread_id(p.thread_id)` — 按线程序列化
- `global("config")` / `global_shared_read("config")` — 配置的写者 vs 读者锁
- `global("account-auth")`、`global("remote-control")`、`global("environment")`、`global("mcp-registry")`、`global("projects")`、`global("windows-sandbox-setup")` 等
- `fs_watch_id`、`command_process_id`、`process_handle`、`fuzzy_session_id`、`mcp_oauth_server`、`optional_thread_id` 等
- `None` — 完全并发

通过 `RequestSerializationQueues` 实现（声明在 `request_serialization.rs` 中）。
