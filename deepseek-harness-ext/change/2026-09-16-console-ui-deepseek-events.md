# Console UI DeepSeek 事件类型显示支持

## 问题背景

用户要求 Console UI 的 'Debug' 和 'Transcript' 标签页正确显示 DeepSeek harness 的所有 Session Event 类型：

- **Debug 标签页**：需要显示**所有**事件类型
- **Transcript 标签页**：需要显示以下 3 大类事件：
  1. **消息事件（4 种）**：user/message, system/message, assistant/message, tool/result
  2. **工具事件（2 种）**：tool/call, tool/result
  3. **辅助事件（1 种）**：assistant/attempt

## 解决方案

### 1. 更新事件分类逻辑 (`EventRow.tsx`)

扩展 `TranscriptCategory` 类型，添加新的类别：

```typescript
export type TranscriptCategory = "user" | "agent" | "tool" | "error" | "system" | "message" | "auxiliary";
```

更新 `categorizeEvent` 函数以识别 DeepSeek harness 事件类型：

```typescript
export function categorizeEvent(event: Event): TranscriptCategory {
  const type = event.type;

  // DeepSeek harness events - Message events (消息事件)
  if (type === "user/message" || type === "user.message") {
    return "user";
  }
  if (type === "system/message") {
    return "message";
  }
  if (type === "assistant/message") {
    return "message";
  }

  // DeepSeek harness events - Tool events (工具事件)
  if (type === "tool/call") {
    return "tool";
  }
  if (type === "tool/result") {
    return "tool";
  }

  // DeepSeek harness events - Auxiliary events (辅助事件)
  if (type === "assistant/attempt") {
    return "auxiliary";
  }

  // Standard OMA events...
}
```

### 2. 更新 TranscriptTab 类别配置

添加新的类别标签、颜色和背景样式：

```typescript
const CATEGORY_LABELS: Record<TranscriptCategory, string> = {
  user: "User",
  agent: "Agent",
  tool: "Tool",
  error: "Error",
  system: "System",
  message: "Message",      // DeepSeek: system/message, assistant/message
  auxiliary: "Auxiliary",  // DeepSeek: assistant/attempt
};

const CATEGORY_COLORS: Record<TranscriptCategory, string> = {
  user: "bg-red-500",
  agent: "bg-green-500",
  tool: "bg-blue-500",
  error: "bg-red-700",
  system: "bg-gray-500",
  message: "bg-purple-500",     // DeepSeek message events
  auxiliary: "bg-orange-500",   // DeepSeek auxiliary events
};
```

更新默认选中的类别：

```typescript
const [selectedCategories, setSelectedCategories] = useState<Set<TranscriptCategory>>(
  new Set(["user", "agent", "tool", "error", "message", "auxiliary"])
);
```

### 3. 更新 EventRow 图标和文本提取

添加 DeepSeek 事件类型的图标支持：

```typescript
function getEventIcon(type: string) {
  switch (type) {
    case "user.message":
    case "user/message":
      return UserIcon;
    case "agent.message":
    case "assistant/message":
      return MessageSquareIcon;
    case "tool/call":
      return WrenchIcon;
    case "assistant/attempt":
      return AlertCircleIcon;
    // ...
  }
}
```

更新事件文本提取函数以支持 DeepSeek 事件：

```typescript
function getEventSnippet(event: Event): string {
  // DeepSeek harness events
  if (type === "user/message" || type === "user.message") {
    // extract text content
  }
  if (type === "assistant/message") {
    // extract assistant message
  }
  if (type === "system/message") {
    // extract system prompt
  }
  if (type === "tool/call") {
    return `Calling ${name}()`;
  }
  // ...
}
```

### 4. 更新 event-io.ts Input/Output 提取

添加 DeepSeek 事件的 Input/Output 结构化提取：

```typescript
export function getEventIO(event: Event, ctx: EventIOContext = {}): EventIO {
  switch (type) {
    case "user/message":
      return { input: message, output: undefined, inputLabel: "Message" };

    case "system/message":
      return { input: undefined, output: systemPrompt, outputLabel: "System Prompt" };

    case "assistant/message":
      return { input: undefined, output: assistantMessage, outputLabel: "Assistant Message" };

    case "tool/call":
      return { input: toolCallArgs, output: undefined, inputLabel: "Tool Call" };

    case "tool/result":
      return { input: pairedUse, output: toolResult, outputLabel: "Tool Result" };

    case "assistant/attempt":
      return { input: undefined, output: attemptInfo, outputLabel: "Attempt" };
    // ...
  }
}
```

## 修改文件

| 文件 | 修改内容 |
|------|---------|
| `console/src/pages/session-detail/EventRow.tsx` | 添加 `message` 和 `auxiliary` 类别；更新 `categorizeEvent`、`getEventIcon`、`getEventSnippet` 函数 |
| `console/src/pages/session-detail/TranscriptTab.tsx` | 添加新类别的标签、颜色、背景样式；更新默认选中类别 |
| `console/src/lib/event-io.ts` | 添加 DeepSeek 事件的 Input/Output 提取逻辑 |
| `scripts/e2e/test-deepseek-console-ui.mjs` | 新建 E2E 验证测试脚本 |

## 验证结果

运行 E2E 测试 (`scripts/e2e/test-deepseek-console-ui.mjs`)：

```
=== DeepSeek Console UI Event Display Test ===

5. Analyzing events for Console UI display:

   - User events:         1
   - Message events:      1 (agent.message - OMA mapped from assistant/message)
   - Tool events:         6 (agent.tool_use, agent.tool_result)
   - Auxiliary events:    0 (assistant/attempt - only appears on failed attempts)

6. Verification:
   - User message display:        ✓
   - Message events (DeepSeek):   ✓
   - Tool events display:         ✓

7. DeepSeek harness specific checks:
   - agent.tool_use:      ✓
   - agent.tool_result:   ✓
   - agent.message:       ✓
   - span.model_request_end: ✓

=== Summary ===
Transcript tab: ✓ Ready (shows User/Message/Tool events)
Debug tab:      ✓ Ready (shows all event types)

✓ Console UI E2E verification PASSED!
```

## 事件类型映射表

| DeepSeek harness 事件 | OMA 映射事件 | Console UI 类别 | 显示位置 |
|---------------------|-------------|----------------|---------|
| user/message | user.message | user | Transcript, Debug |
| system/message | (内部使用) | message | Transcript, Debug |
| assistant/message | agent.message | message | Transcript, Debug |
| tool/call | agent.tool_use | tool | Transcript, Debug |
| tool/result | agent.tool_result | tool | Transcript, Debug |
| assistant/attempt | (无映射) | auxiliary | Transcript, Debug |
| turn/start | session.status_running | system | Debug |
| turn/end | (内部使用) | system | Debug |
| step/start | span.model_request_start | system | Debug |
| step/end | span.model_request_end | system | Debug |
| request/header | (内部使用) | system | Debug |
| request/context | (内部使用) | system | Debug |
| session/end-seed | session.lifecycle | system | Debug |

## 注意事项

1. **消息事件分类**：`agent.message` 被归类为 `message` 类别而非 `agent` 类别，因为它是 DeepSeek harness 的 `assistant/message` 事件的 OMA 映射形式。

2. **辅助事件**：`assistant/attempt` 仅在模型尝试失败或重试时出现，正常成功的工具调用不会产生此事件。

3. **Debug 标签页**：默认隐藏 `span.model_request_*` 遥测事件，但可以通过类型筛选器手动显示。

4. **Transcript 标签页**：默认显示所有类别（user, agent, tool, error, message, auxiliary），可通过类别筛选器隐藏特定类别。

## 参考资料

- `packages/core/session/src/types.ts` — DeepSeek harness SessionEventMap 定义
- `deepseek-session-event-types.md` — DeepSeek 事件类型完整文档
- `event-io.ts` — Input/Output 提取逻辑
