# DeepSeek Harness Session Follow Tool Events 修复

## 问题背景

在之前修复 Typert RPC payload 结构和 session/follow turn completion 后，meta-harness 能够从 deepseek-harness 接收事件，但存在以下问题：

1. **只有 `agent.thinking` 相关事件显示** - Console UI 只显示与思考相关的事件
2. **缺少 `agent.tool_use` 事件** - 工具调用没有被发出
3. **缺少 `agent.tool_result` 事件** - 工具执行结果没有被发出
4. **缺少 `agent.message` 事件** - 最终回复消息没有被发出

用户执行 `who am i` 测试时，只能看到：
```
- user.message
- session.lifecycle
- session.status_running
- span.model_request_end
- session.lifecycle
- session.status_idle
```

但没有看到任何 `agent.tool_use`、`agent.tool_result` 或 `agent.message` 事件。

## 根因分析

### 问题 1: `assistant/message` 内容类型处理不完整

DeepSeek harness 在 `assistant/message` 事件中发送多种类型的内容：
- `{"type": "reasoning"}` - 模型思考过程
- `{"type": "tool-call", "name": "pwsh", "arguments": "..."}` - 工具调用
- `{"type": "text"}` - 最终文本回复

原有代码只处理 `type: "text"` 的内容，忽略了 `tool-call` 类型：

```go
// 旧代码
for _, part := range d.Message.Content {
    if part.Type == "text" {
        sb.WriteString(part.Text)
    }
}
```

### 问题 2: `assistant/message` with tool-call 不应结束 turn

当 `assistant/message` 包含 `tool-call` 内容时，表示模型请求工具执行，turn 应该继续等待工具结果。原有代码在收到任何 `assistant/message` 时都标记 `done=true`，导致：
1. WebSocket 连接过早关闭
2. `tool/result` 事件无法被接收
3. 工具结果无法被发出

### 问题 3: 缺少 tool-call 内容类型识别

需要解析 `tool-call` 内容的 `id`、`name`、`arguments` 字段并发出 `agent.tool_use` 事件。

## 解决方案

### 修复 1: 处理 `assistant/message` 中的多种内容类型

修改 `emitSessionEvent` 函数，遍历 `message.content` 数组并根据类型处理：

```go
for _, part := range d.Message.Content {
    switch part.Type {
    case "text":
        textContent.WriteString(part.Text)
    case "tool-call":
        hasToolCall = true
        mapped, mapErr := agentToolUseEvent(part.Name, "")
        // emit agent.tool_use event
    case "reasoning":
        // skip internal thinking
    }
}
```

### 修复 2: 根据内容类型决定是否结束 turn

只有当 `assistant/message` 是纯文本回复（不含 tool-call）时才标记 turn 完成：

```go
// Only mark turn done if this is a final text response (no tool calls)
// Tool calls mean the model is requesting tool execution, not completing
if hasToolCall {
    return false, nil  // turn continues
}
return true, nil  // final response
```

### 修复 3: 捕获 usage 数据

`assistant/message` 可能包含 usage 字段（input/output tokens），需要捕获用于成本追踪：

```go
if d.Usage != nil && *usage == nil {
    *usage = &TurnUsage{
        InputTokens:  d.Usage.InputTokens,
        OutputTokens: d.Usage.OutputTokens,
    }
}
```

## 验证结果

运行 E2E 测试 (`scripts/e2e/test-deepseek-whoami.mjs`)：

```
=== DeepSeek 'Who Am I' Test ===

1. Creating DeepSeek agent...
   Agent: agent-xxx

2. Creating session...
   Session: sess-xxx

3. Sending 'who am i' prompt...
   Status: 202

4. Waiting for turn completion (timeout: 60s)...
   Turn completed!

5. Event summary:
   All events:
   - user.message              who am i
   - session.lifecycle         
   - session.status_running    
   - agent.tool_use            pwsh
   - agent.tool_result         
   - agent.message             Here's what I can tell about you...
   - span.model_request_end    
   - session.status_idle       

6. Checking for tool events:
   agent.tool_use: ✓
   agent.tool_result: ✓
   agent.message: ✓

✓ Test passed!
```

## 修改文件

- `internal/harness/deepseek_client.go`
  - `emitSessionEvent()` - 处理 `assistant/message` 中的多种内容类型
    - 解析 `tool-call` 内容并发出 `agent.tool_use` 事件
    - 累积 `text` 内容并发出 `agent.message` 事件
    - 跳过 `reasoning` 内部思考
    - 根据是否有 tool-call 决定是否结束 turn
    - 捕获 usage 数据用于成本追踪

## 事件流

修复后的完整事件流：

1. `user.message` - 用户发送 "who am i"
2. `session.status_running` - Session 开始处理
3. `agent.tool_use` (多次) - 模型调用工具获取上下文信息
4. `agent.tool_result` (多次) - 工具执行结果返回
5. `agent.message` - 模型综合工具结果给出最终回复
6. `span.model_request_end` - 带有 usage 数据
7. `session.status_idle` - Turn 完成

## 参考资料

- `internal/harness/hermes_client.go` - Hermes harness 实现参考
- `internal/harness/turn_telemetry.go` - `usageEvent` 函数定义
- 2026-09-15 session-follow-turn-completion.md - 之前的 turn completion 修复
