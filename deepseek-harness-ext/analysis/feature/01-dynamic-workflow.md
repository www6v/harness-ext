# 动态工作流 (Dynamic Workflow) 分析

## 结论

**✅ 支持** — deepseek-harness 拥有完整的动态工作流 (Dynamic Workflow) 功能。

## 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-workflow` | `packages/workflow/workflow/` | Service Definition — 工作流能力接缝定义 |
| `@deepseek-ai/dsh-workflow-worker-thread` | `packages/workflow/worker-thread/` | Service Provider — worker-thread 执行引擎 |
| `@deepseek-ai/dsh-tool-workflow` | `packages/workflow/tool-workflow/` | Consumer — 模型面工具 (tool Consumer) |
| `@deepseek-ai/dsh-ui-workflow-run` | `packages/client/ui-workflow-run/` | UI 展示 — 工作流运行状态展示 |

## 架构设计

### Service Definition 模式

工作流遵循 deepseek-harness 的 **capability seam** 模式：

```
WorkflowEngine (Service Definition)
  ├── WorkflowStartRequest → WorkflowRun
  ├── WorkflowMeta (name, description, phases)
  ├── WorkflowResult (value, stopReason, agentsStarted)
  └── Events: workflow/start, workflow/phase, workflow/log, 
              workflow/agent-start, workflow/agent-end, workflow/end
```

### 关键类型定义

#### WorkflowMeta — 工作流身份块

```typescript
interface WorkflowMeta {
  name: string              // kebab-case 工作流名称
  description: string       // 一行描述
  whenToUse?: string        // 可选使用时机说明
  phases?: WorkflowPhase[]  // 可选阶段声明
}
```

#### WorkflowPhase — 阶段定义

```typescript
interface WorkflowPhase {
  title: string
  detail?: string
  provider?: string   // 信息性：预期 provider 覆盖
  model?: string      // 信息性：预期 model 覆盖
}
```

#### WorkflowStartRequest — 启动请求

```typescript
interface WorkflowStartRequest {
  script: string              // 纯 JS 脚本体 (允许 top-level await)
  meta: WorkflowMeta          // 身份块 (JSON 数据)
  args?: unknown              // 可选输入参数，作为 `args` 全局暴露给脚本
  subagentProvider?: string   // 可选子代理 provider 覆盖
  maxTotalAgents?: number     // 可选总子代理上限
  parent: Agent               // 父代理 (每个 agent() 调用的归属)
  signal?: AbortSignal        // 取消信号
}
```

#### WorkflowRun — 运行句柄

```typescript
interface WorkflowRun {
  readonly id: WorkflowRunId
  readonly meta: WorkflowMeta
  readonly result: Promise<WorkflowResult>
  cancel(reason?: string): void
  dispose(): Promise<void>
}
```

#### WorkflowResult — 运行结果

```typescript
interface WorkflowResult {
  value: unknown                    // 脚本 return 值 (plain JSON)
  stopReason: WorkflowStopReason    // 'completed' | 'cancelled' | 'error'
  error?: string                    // 失败消息
  agentsStarted: number             // 已启动的 agent() 调用计数
}
```

### 脚本执行模型

工作流脚本是**纯 JavaScript 字符串**，在 worker-thread 中执行。脚本可以：

1. 调用 `agent()` 生成子代理
2. 调用 `parallel()` 并行执行
3. 调用 `pipeline()` 管道执行
4. 调用 `phase(title)` 声明阶段
5. 调用 `log(message)` 输出日志
6. 通过 `return <json-value>` 返回结果
7. 支持 `top-level await`

### 事件生命周期

```
workflow/start → [workflow/phase → ...] → [workflow/agent-start → workflow/agent-end]... → workflow/end
                  workflow/log...
```

### 错误处理

```typescript
type WorkflowErrorCode =
  | 'SCRIPT_PARSE'           // 脚本解析错误
  | 'META_INVALID'           // meta 块无效
  | 'INVALID_ARGUMENT'       // 参数无效
  | 'UNSUPPORTED_OPTION'     // 不支持的选项
  | 'UNSUPPORTED_SCHEMA'     // 不支持的 schema
  | 'AGENT_CAP'              // 子代理数量上限
  | 'ITEM_CAP'               // 项目数量上限
  | 'AGENT_START'            // 子代理启动失败
  | 'AGENT_RESULT'           // 子代理结果错误
  | 'RESULT_UNSERIALIZABLE'  // 结果不可序列化
  | 'CANCELLED'              // 运行被取消
```

`WorkflowError` 继承自 `HarnessError`，具有 `fatal` 标志：
- `fatal: true` — 组合器 (`parallel()`/`pipeline()`) 必须重新抛出
- `fatal: false` — 子代理失败映射为 `null`

## 与 Claude Code 的对比

deepseek-harness 的工作流设计与 Claude Code 的 dynamic workflow 高度对齐：

| 特性 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| 脚本式工作流 | ✅ | ✅ |
| 动态 agent() 生成 | ✅ | ✅ |
| parallel()/pipeline() | ✅ | ✅ |
| phase 阶段声明 | ✅ | ✅ |
| meta 身份块 | ✅ | ✅ |
| Worker-thread 隔离 | ✅ | ✅ |
| 事件生命周期 | ✅ | ✅ |
| 错误分类 | ✅ | ✅ |

## 两个工作流工具

deepseek-harness 提供两个模型面工作流工具：

| 工具 | 包名 | 说明 |
|------|------|------|
| `workflow` | `packages/workflow/tool-workflow/` | 通用动态工作流 — 模型编写脚本，支持任意 agent/parallel/pipeline 组合 |
| `ralph` | `packages/workflow/tool-ralph/` | 固定迭代循环 — 新鲜 agent 迭代模式，适合需要多轮迭代的工作 |

### `ralph` 工具

`ralph` 是一个特殊的**固定新鲜代理迭代循环**工具：
- 每次迭代创建一个**全新的 agent**（不继承之前的上下文）
- 适合需要多轮独立尝试的任务
- 循环直到满足条件或达到迭代上限

## 使用示例

工作流通过 `@deepseek-ai/dsh-tool-workflow` 工具暴露给模型，模型可以通过 tool call 启动工作流：

```json
{
  "tool": "workflow",
  "args": {
    "meta": {
      "name": "review-changes",
      "description": "Review changed files across dimensions",
      "phases": [{ "title": "Review" }, { "title": "Verify" }]
    },
    "script": "...",
    "args": { "pr": 123 }
  }
}
```

## 关键代码位置

| 文件 | 说明 |
|------|------|
| `packages/workflow/workflow/src/index.ts` | WorkflowEngine Service Definition |
| `packages/workflow/workflow/src/types.ts` | 工作流词汇类型 |
| `packages/workflow/workflow/src/runtime-types.ts` | Host-only 运行时类型 |
| `packages/workflow/workflow/src/invariant.ts` | 运行时不变量 |
