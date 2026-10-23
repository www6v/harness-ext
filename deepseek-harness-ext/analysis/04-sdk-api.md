# SDK JSON-RPC 接口

## 概述

DeepSeek Harness SDK 提供了通过 **JSON-RPC 2.0 over stdio** 驱动 Agent 的编程接口。SDK 启动 `dsh --profile sdk` 作为子进程，通过标准输入/输出进行通信。

- **协议**: JSON-RPC 2.0（换行分隔）
- **传输**: stdio（stdin/stdout）
- **源码位置**: `packages/sdk/`
- **包名**:
  - `@deepseek-ai/dsh-sdk-protocol` — 协议类型定义
  - `@deepseek-ai/dsh-sdk-client` — TypeScript 客户端
  - `@deepseek-ai/dsh-sdk-jsonrpc-server` — 服务端插件

## 生命周期

```
客户端启动 dsh --profile sdk 子进程
  → initialize 握手
  → session/prompt 发送提示（可多次）
  ← session.event / session.status / subagent.* 通知
  → shutdown 关闭
```

## 请求方法（Client → Server）

### 1. `initialize` — 初始化握手

**参数**:
```typescript
interface InitializeParams {
  cwd: string                    // 工作目录
  provider: string               // LLM Provider（如 "deepseek-official"）
  model: string                  // 模型名称（如 "deepseek-v4-flash"）
  reasoningEffort?: string       // 推理强度（可选）
  maxTokens?: number             // 最大输出 token 数（可选）
}
```

**结果**:
```typescript
interface InitializeResult {
  serverInfo: {
    name: string    // "deepseek-harness-runtime"
    version: string // 版本号
  }
}
```

### 2. `session/prompt` — 发送提示

**参数**:
```typescript
interface SessionPromptParams {
  sessionId: string                        // 会话 ID（未知 ID 会自动创建）
  contentBlocks: SdkPromptContentBlock[]   // 提示内容块
}

type SdkPromptContentBlock =
  | ContentBlock                           // 文本/文件等内容块
  | SdkEncodedImageBlock                   // 内联图片

interface SdkEncodedImageBlock {
  type: 'image'
  data: string                             // base64 编码
  mimeType: 'image/png' | 'image/jpeg' | 'image/webp' | 'image/gif'
}
```

**结果**:
```typescript
interface SessionPromptResult {
  messageId: string    // 已入队消息的 ID
}
```

### 3. `shutdown` — 关闭

**参数**: 无

**结果**: `{}`（空对象）

## 通知方法（Server → Client）

### 1. `session.event` — 会话事件

```typescript
interface SessionEventNotification {
  sessionId: string      // 所属会话
  event: SessionEvent    // 完整的会话日志事件
}
```

### 2. `session.status` — 会话状态

```typescript
interface SessionStatusNotification {
  sessionId: string
  status: 'idle' | 'running'    // Agent 整体状态
}
```

### 3. `subagent.started` — 子 Agent 启动

```typescript
interface SubagentStartedNotification {
  parentSessionId: string    // 委托方会话
  childSessionId: string     // 新建的子会话
}
```

### 4. `subagent.finished` — 子 Agent 完成

```typescript
interface SubagentFinishedNotification {
  provider: string              // 子 Agent 提供方
  agentId: string               // 子 Agent ID
  parentSessionId: string       // 委托方会话
  childSessionId: string        // 子会话
  status: 'ok' | 'error'        // 运行结果
  stopReason: SubagentStopReason // 停止原因
  lastAssistantMessage?: ContentBlock[]  // 最后的助手输出
}
```

## TypeScript 客户端 API

### 高层 API: `DeepSeekHarness`

```typescript
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'

const harness = new DeepSeekHarness({
  provider: 'deepseek-official',
  model: 'deepseek-v4-flash',
  cwd: '/path/to/project',
})

// 执行单次对话
const result = await harness.run('帮我分析这个项目的结构')
console.log(result.finalResponse)

// 或使用 async disposable
await using harness2 = new DeepSeekHarness()
const session = harness2.session()
const r = await harness2.run('写一个 hello world')
```

**`DeepSeekHarnessOptions`**:
| 选项 | 默认值 | 说明 |
|------|--------|------|
| `dshBin` | 自动解析 | dsh 二进制路径 |
| `profile` | `'sdk'` | 使用的 Profile |
| `provider` | `'deepseek-official'` | LLM Provider |
| `model` | `'deepseek-v4-flash'` | 模型名称 |
| `reasoningEffort` | — | 推理强度 |
| `maxTokens` | — | 最大输出 token |
| `cwd` | `process.cwd()` | 工作目录 |
| `env` | `{}` | 环境变量 |
| `initializeTimeoutMs` | `10000` | 初始化超时 |
| `requestTimeoutMs` | — | 请求超时 |
| `shutdownTimeoutMs` | `1000` | 关闭超时 |

### 底层 API: `HarnessClient`

```typescript
import { HarnessClient } from '@deepseek-ai/dsh-sdk-client'

const client = new HarnessClient({ dshBin: '/path/to/dsh' })
client.start()

// 初始化
await client.initialize({
  cwd: '/project',
  provider: 'deepseek-official',
  model: 'deepseek-v4-flash',
})

// 发送提示
const response = await client.prompt('session-1', [
  { type: 'text', text: 'Hello' }
])

// 订阅通知
const subscription = client.subscribe()
for await (const notification of subscription) {
  console.log(notification)
}

await client.close()
```

### `RunResult` 结构

```typescript
interface RunResult {
  sessionId: string           // 会话 ID
  finalResponse: string       // 最终响应文本
  finishReason: string | null // 完成原因
  events: SessionEvent[]      // 所有会话事件
  notifications: Notification[] // 所有通知
}
```
