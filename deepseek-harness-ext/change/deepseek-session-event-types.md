# DeepSeek Harness Session Event 类型全览

本文档列出 DeepSeek Harness 支持的所有 Session Event 类型，基于 `packages/core/session/src/types.ts` 中的 `SessionEventMap` 定义。

---

## Session Event 类型列表

### 生命周期事件（Lifecycle Events）

| 事件类型 | 数据结构 | 说明 |
|---------|---------|------|
| `turn/start` | `{ turn: number }` | 打开一个新的 turn，在循环获取输入或执行 pre-step 之前 |
| `turn/end` | `{ turn: number; reason: TurnEndReason }` | 关闭 turn，包含结束原因（完成、取消、错误等） |
| `step/start` | `{ turn: number; step: number }` | 打开 step —— 一次模型调用加它请求的工具执行 |
| `step/end` | `{ turn: number; step: number }` | 关闭 step |
| `session/end-seed` | `{ inherited?: true }` | 标记构造函数种子的结束，用于 resume/fork/replay 场景 |

### 消息事件（Message Events）

这些事件产生 LLM 可见的消息，属于 `SurfaceEventType`：

| 事件类型 | 数据结构 | 说明 |
|---------|---------|------|
| `user/message` | `UserMessage` | 用户消息 —— 直接的人类提示、合成的上下文（文件变更通知、AGENTS.md 等）或目标 continuation |
| `system/message` | `{ turn, step, message: SystemMessage }` | 系统提示 —— 渲染后的系统指令在模型可见表面 |
| `assistant/message` | `{ turn, step, message: AssistantMessage, stream: AssistantStreamRecord[], usage?: TokenUsage, interrupted?: true }` | 助手消息 —— 包含完整的流式输出记录和 token 使用统计 |
| `tool/result` | `{ turn, step, message: ToolResultMessage, error?: { name, code }, meta?: JsonValue }` | 工具执行结果 —— 包含可选的错误信息和工具私有元数据 |

### 工具事件（Tool Events）

| 事件类型 | 数据结构 | 说明 |
|---------|---------|------|
| `tool/call` | `{ turn, step, callId: ToolCallId, name: string, arguments: string }` | 模型请求工具调用 —— 包含原始参数 JSON 字符串（未解析） |
| `tool/result` | `{ turn, step, message: ToolResultMessage, error?, meta? }` | 工具执行完成结果 |

### 请求元数据事件（Request Metadata Events）

| 事件类型 | 数据结构 | 说明 |
|---------|---------|------|
| `request/header` | `{ header: EpochHeader, reason: RequestHeaderReason, startsSeries?: true }` | 请求头快照 —— 包含调用配置、工具列表等 |
| `request/context` | `{ provider: string, model: string, contextWindow?: number, systemPromptUpdate?: SystemPromptUpdate }` | 路由元数据 —— 模型路由、上下文窗口、系统提示更新模式 |

### 辅助事件（Auxiliary Events）

| 事件类型 | 数据结构 | 说明 |
|---------|---------|------|
| `assistant/attempt` | `{ turn, step, stream: AssistantStreamRecord[] }` | 模型尝试记录 —— 未提交到表面的失败/重试/取消的尝试 |

---

## SessionEvent 通用结构

每个事件都有以下通用 envelope 结构：

```typescript
interface SessionEvent<T extends SessionEventType> {
  type: T                          // 事件类型
  seq: SessionSeq                  // 会话内单调递增的序列号
  time: number                     // Unix 时间戳（毫秒）
  data: SessionEventMap[T]         // 事件数据
  
  // 仅 SurfaceEventType 事件携带
  surfaceOp?: SurfaceOp            // 表面放置操作 ('append' 或 'replace')
  sourceEventSeqs?: SessionSeq[]   // 引用的源事件序列号（assistant/message 除外）
  
  // 可选标记
  ignorable?: true                 // 读者可安全忽略的纯信息性记录
}
```

---

## TurnEndReason 类型

`turn/end` 事件的原因类型：

```typescript
type TurnEndReason =
  | { kind: 'completed' }              // 正常完成
  | { kind: 'aborted'; reason: TurnEndCancelCause }  // 被取消
  | { kind: 'blocked' }                // 被阻止
  | { kind: 'error'; error: LlmFailure }  // LLM 错误
  | { kind: 'max-tokens' }             // 达到 token 上限
  | { kind: 'interrupted' }            // 崩溃后恢复时合成的中断标记
```

`TurnEndCancelCause` 包括：
- `{ kind: 'user' }` — 用户主动取消
- `{ kind: 'parent' }` — 父会话取消
- `{ kind: 'hook' }` — Hook 拒绝
- `{ kind: 'disposed' }` — 资源释放
- `{ kind: 'legacy' }` — 导入的历史记录

---

## RequestHeaderReason 类型

`request/header` 的原因类型：

```typescript
type RequestHeaderReason =
  | 'initial'    // 会话首个请求
  | 'resume'     // 恢复/进程重启后的首个请求
  | 'change'     // 后续请求使用不同的 header
  | 'series'     // 未变更 header 但开始新的消息系列
```

---

## SurfaceEventType 与 SurfaceOp

以下事件类型产生 LLM 可见的消息（`SurfaceEventType`）：

- `system/message`
- `user/message`
- `assistant/message`
- `tool/result`

这些事件携带 `surfaceOp` 字段，指定消息在表面的放置方式：

```typescript
type SurfaceOp =
  | 'append'                          // 追加到末尾（正常路径）
  | { op: 'replace'; startSeq, endSeq }  // 替换指定范围的表面节点
```

---

## meta-harness 当前支持的事件映射

根据 `internal/harness/deepseek_client.go` 中的 `emitSessionEvent` 和 `parseSessionEventFromRemote`：

| DeepSeek Event | OMA Event | 支持状态 |
|---------------|-----------|---------|
| `user/message` | `user.message` | ✅ 已支持 |
| `assistant/message` (text) | `agent.message` | ✅ 已支持 |
| `assistant/message` (tool-call) | `agent.tool_use` | ✅ 已支持 |
| `tool/call` | `agent.tool_use` | ✅ 已支持 |
| `tool/result` | `agent.tool_result` | ✅ 已支持 |
| `assistant/chunk` | `agent.message` (流式) | ✅ 已支持 |
| `turn/end` | (忽略，用 assistant/message 判断) | ⚠️ 部分支持 |
| `system/message` | - | ❌ 未支持 |
| `turn/start` | - | ❌ 未支持 |
| `step/start` | - | ❌ 未支持 |
| `step/end` | - | ❌ 未支持 |
| `request/header` | - | ❌ 未支持 |
| `request/context` | - | ❌ 未支持 |
| `session/end-seed` | - | ❌ 未支持 |
| `assistant/attempt` | - | ❌ 未支持 |

---

## 扩展建议

如需支持更多事件类型，可在 `emitSessionEvent` 中添加对应的 case：

```go
case "system/message":
    // 发出 system.message 事件用于记录系统提示变化
    
case "step/start":
    // 发出 step.start 事件用于 UI 显示执行进度
    
case "request/header":
    // 记录模型配置变更
```

---

## 参考资料

- `packages/core/session/src/types.ts` — SessionEventMap 定义
- `packages/session/session-format/src/types.ts` — 会话格式类型
- `internal/harness/deepseek_client.go` — meta-harness 实现
