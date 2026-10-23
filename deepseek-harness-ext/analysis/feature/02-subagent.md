# 子代理 (Subagent) 分析

## 结论

**✅ 支持** — deepseek-harness 拥有完整且高度成熟的子代理 (Subagent) 功能，支持多种 provider、一次性运行和可续接子代理。

## 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-subagent` | `packages/subagent/subagent/` | Service Definition — 子代理能力接缝 |
| `@deepseek-ai/dsh-subagent-spawn-in-process` | `packages/subagent/spawn-in-process/` | Provider — 进程内 spawn (全新 agent) |
| `@deepseek-ai/dsh-subagent-fork-in-process` | `packages/subagent/fork-in-process/` | Provider — 进程内 fork (继承父上下文) |
| `@deepseek-ai/dsh-subagent-acp` | `packages/subagent/acp/` | Provider — ACP 远程子代理 |
| `@deepseek-ai/dsh-subagent-codex` | `packages/subagent/codex/` | Provider — Codex (官方 app-server 协议) |
| `@deepseek-ai/dsh-subagent-claude-code` | `packages/subagent/claude-code/` | Provider — Claude Code (Agent SDK) |
| `@deepseek-ai/dsh-subagent-dsh-sdk` | `packages/subagent/dsh-sdk/` | Provider — DSH SDK (TypeScript SDK 远程) |
| `@deepseek-ai/dsh-tool-subagent` | `packages/subagent/tool-subagent/` | Consumer — 模型面委托工具 |
| `@deepseek-ai/dsh-tool-subagent-control` | `packages/subagent/tool-subagent-control/` | Consumer — `send_message`, `interrupt_agent`, `list_agents` 工具 |
| `@deepseek-ai/dsh-ui-subagent` | `packages/client/ui-subagent/` | UI 展示 — 子代理状态 |
| `@deepseek-ai/dsh-agent-team` | `packages/experimental/agent-team/` | **实验性** — Agent Teams (持久化 roster + task board + mailbox) |

## 架构设计

### SubagentRuntime — 核心服务

`SubagentRuntime` 是 `TypertRemoteService`，提供命名 provider 注册、一次性运行、可续接子代理和远程 RPC 接口。

```typescript
class SubagentRuntime extends TypertRemoteService {
  // 一次性子代理
  async start(name: string, request: SubagentStartRequest): Promise<SubagentRun>
  
  // 可续接子代理
  async startContinuable(spec: ContinuableStartSpec): Promise<ContinuableStart>
  
  // 消息传递
  async sendMessage(sender, targetId, content, options): Promise<MessageId>
  
  // 中断
  interrupt(targetSessionId, authority): void
  
  // 发现
  async listChildren(parentSessionId, signal?): Promise<SubagentListEntry[]>
  async listDescendants(rootSessionId, signal?): Promise<SubagentDescendantListEntry[]>
  
  // Provider 管理
  registerProvider(provider: SubagentProvider): () => void
  getProvider(name: string): SubagentProvider | undefined
  list(): string[]
  
  // Remote 接口 (Typert)
  @Remote('list') async remoteExportList(...): Promise<SubagentCatalog>
  @Remote('prompt') async prompt(...): Promise<SubagentPromptReceipt>
  @Remote('interruptByParent') interruptByParent(...): SubagentInterruptReceipt
}
```

### Provider 接口

```typescript
interface SubagentProvider {
  readonly name: string
  readonly capabilities: SubagentCapabilities
  readonly inheritsParentContext: boolean
  readonly agentRouteDefaults?: Readonly<{ provider: string; model: string }>
  
  start(request: ResolvedSubagentStartRequest): Promise<SubagentRun>
  prepareContinuable?(request: ContinuableCreateRequest): Promise<ContinuableCreateSpec>
}
```

### Capabilities — 能力声明

```typescript
interface SubagentCapabilities {
  readonly agentOptions: boolean    // 支持 model/provider override
  readonly outputSchema: boolean    // 支持结构化输出 schema
  readonly depthLimit: boolean      // 支持委托深度限制
  readonly toolFilter: boolean      // 支持工具过滤
  readonly persona: boolean         // 支持 persona 覆盖
}
```

### 一次性子代理 (One-Shot)

```typescript
interface SubagentStartRequest {
  readonly label?: string
  readonly prompt: ContentBlock[]
  readonly parent: Agent
  readonly signal: AbortSignal
  readonly agentOptions?: AgentOptions    // model/provider override
  readonly outputSchema?: ObjectJsonSchema // 结构化输出
  readonly maxDepth?: number               // 深度限制
  readonly toolFilter?: ToolRestriction    // 工具过滤
  readonly persona?: string                // persona 覆盖
}
```

运行结果：

```typescript
interface SubagentRun {
  readonly id: SessionId
  readonly localAgent: Agent | undefined  // 进程内子代理 or undefined (远程)
  readonly result: Promise<SubagentResult>
  dispose(): Promise<void>
}

interface SubagentResult {
  readonly output: ContentBlock[]          // 最终助手输出
  readonly structured?: unknown            // 结构化结果
  readonly diagnostic?: string             // 失败诊断
  readonly stopReason: SubagentStopReason
}

type SubagentStopReason = 'completed' | 'aborted' | 'error' | 'max-tokens' | 'refusal'
```

### 可续接子代理 (Continuable)

可续接子代理是**持久化的对话实体**，不是一次性运行。它们有 inbox、支持消息传递、冷恢复：

```typescript
interface ContinuableStartSpec {
  readonly provider: string
  readonly label: string
  readonly childId?: SessionId
  readonly request: Omit<SubagentStartRequest, 'label' | 'signal' | 'outputSchema'>
  readonly signal: AbortSignal
}

interface ContinuableStart {
  readonly childId: SessionId       // 持久子代理 id
  readonly messageId: MessageId     // 接受的初始消息 id
}
```

可续接子代理的特性：
- **持久化** — 跨会话恢复
- **Inbox** — 消息队列，支持多轮对话
- **中断** — 支持 `interrupt()` 取消当前 turn
- **消息传递** — `sendMessage()` 支持 steer/queue 两种投递模式
- **树发现** — `listChildren()` / `listDescendants()` 遍历子代理树

### 事件生命周期

```typescript
interface Events {
  'subagent/provider-added'(provider: SubagentProvider): void
  'subagent/provider-removed'(name: string): void
  'subagent/start'(info: SubagentRunInfo): void     // scope-filtered by parent
  'subagent/end'(info: SubagentRunEndInfo): void     // scope-filtered by parent
}
```

### 描述符 (Descriptor) — 持久化身份

子代理描述符记录了子代理的创建意图和配置，支持持久化：

```typescript
type SubagentDescriptorData = OneShotSubagentDescriptorData | ContinuableSubagentDescriptorData
```

## Remote API (Typert RPC)

SubagentRuntime 暴露了 Typert Remote 接口，支持浏览器客户端直接操作：

| Remote 方法 | 功能 |
|-------------|------|
| `subagent.list(parentSessionId)` | 列出直接子代理 |
| `subagent.prompt(request)` | 向可续接子代理发送消息 |
| `subagent.interruptByParent(childId, parentId, mode)` | 中断子代理 |

## 与 Claude Code 的对比

| 特性 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| spawn/fork | ✅ | ✅ (spawn, fork, acp providers) |
| 结构化输出 | ✅ | ✅ (outputSchema) |
| 深度限制 | ✅ | ✅ (maxDepth) |
| 工具过滤 | ✅ | ✅ (toolFilter) |
| 可续接子代理 | ✅ (teammates) | ✅ (Continuable) |
| 消息传递 | ✅ (SendMessage) | ✅ (sendMessage) |
| 远程子代理 | ✅ | ✅ (ACP provider) |
| 树发现 | ✅ (ListAgents) | ✅ (listChildren/listDescendants) |
| Persona 覆盖 | 部分 | ✅ |

## 关键代码位置

| 文件 | 说明 |
|------|------|
| `packages/subagent/subagent/src/index.ts` | SubagentRuntime 核心服务 |
| `packages/subagent/subagent/src/types.ts` | 请求/结果/provider 类型 |
| `packages/subagent/subagent/src/continuation.ts` | 可续接子代理管理器 |
| `packages/subagent/subagent/src/child-agent.ts` | 子代理组合逻辑 |
| `packages/subagent/subagent/src/descriptor.ts` | 持久化描述符 |
| `packages/subagent/subagent/src/list-children.ts` | 子代理发现 |
| `packages/subagent/subagent/src/inbox.ts` | 消息 inbox |
| `packages/subagent/subagent/src/control.ts` | Remote 控制接口 |
