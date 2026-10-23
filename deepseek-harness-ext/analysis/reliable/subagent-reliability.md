# Subagent 可靠性分析

> 分析对象：`deepseek-harness` 中的 Subagent 子系统
> 包路径：`packages/subagent/`

---

## 1. 概述

**Subagent** 是 `deepseek-harness` 中由父 Agent 委派出去执行限定范围独立任务的子 Agent。它是 Cordis 插件架构中的一个**能力接缝（capability seam）**，通过 `ctx.subagents` 暴露给模型和浏览器控制面。

Subagent 支持两种模式：

| 模式 | 说明 |
|------|------|
| **One-shot** | 单次委派：启动 → 运行到结束 → 返回结果 → 回收。映射为后台 Task（通过 `ctx.jobs`） |
| **Continuable** | 持久对话：一个稳定的 session id 跨越多次激活；支持进程重启后的冷恢复（cold-resume）；消息可以在 turn 中途插入或排队到下一个 turn |

### 关键文件

| 文件 | 角色 |
|------|------|
| `packages/subagent/subagent/src/index.ts` | `SubagentRuntime` — 服务定义 |
| `packages/subagent/subagent/src/types.ts` | 所有类型契约（requests, results, capabilities, providers） |
| `packages/subagent/subagent/src/continuation.ts` | `SubagentContinuationManager` — continuable 编排 |
| `packages/subagent/subagent/src/continuation-activation.ts` | `ContinuableActivationRegistry` — 进程内 Activation 所有权 |
| `packages/subagent/subagent-spawn-in-process/` | spawn provider — 全新上下文子 Agent |
| `packages/subagent/subagent-fork-in-process/` | fork provider — 继承父 Agent 已完成 turns |
| `packages/subagent/subagent-acp/` | ACP provider — 进程外子 Agent |

---

## 2. 可靠性机制

### 2.1 取消信号传播（AbortSignal Propagation）

**每一项操作都接受一个必需的 `AbortSignal`** — 这是核心架构原则。

- 信号通过 `SubagentStartRequest.signal`、`ContinuableStartSpec.signal`、`SubagentSendMessageOptions.signal` 贯穿传递
- 在关键区段中多次调用 `throwIfAborted()` 检查
- 用于中止启动前（pre-publication）和启动后（post-publication）的 turn 工作
- 每条结算路径都会清理监听器（`signal.removeEventListener('abort', onAbort)`）

### 2.2 幂等回收（Idempotent Disposal）

`SubagentRun.dispose()` 是**记忆化/幂等**的——多次调用返回同一个 Promise：

```typescript
// out-of-process.ts: subprocessRunHandle()
let disposal: Promise<void> | undefined
dispose(): Promise<void> {
  if (disposal !== undefined) return disposal  // 幂等
  disposal = parts.teardown()
  return disposal
}
```

`SubagentInbox.close()` 同样记忆化——首次调用安装 `closingPromise`，后续调用全部返回它。

### 2.3 ChildLock 串行化

`ChildLock` 将每个子 Agent 的持久化操作串行化：

```typescript
class ChildLock {
  run<T>(childId: SessionId, operation: () => Promise<T>): Promise<T>
}
```

保证同一个子 Agent 的发送、释放、回收严格有序。失败的关键区段不会拒绝后续不相关的调用者（在链式 tail 中被吸收）。

### 2.4 深度限制（递归预算）

委派深度被追踪为非负安全整数：
- 每个 Agent 的 `subagentDepth` 选项和 session header 中的 `delegationDepth`
- 持久化的 header 是**单调下限**——被恢复的子 Agent 不能假装比实际更浅：
  ```typescript
  return Math.max(agent.session.header.delegationDepth ?? 0, runtime ?? 0)
  ```
- `assertSubagentMaxDepth()` 在启动时校验
- 通过 `tool-subagent` config 的 `maxDepth` 配置（默认 3，0 = 禁止委派，`'provider-managed'` = 不限制）

### 2.5 描述符版本化与持久化

每个 subagent 获得一个**版本化的持久描述符**（`subagent/descriptor` session 事件），记录：

- 模式（one-shot / continuable）
- Provider 名称
- Label、agent provider/model/reasoning effort
- Persona、tool filter

描述符在启动工作前**快照校验**（确保可无损 JSON 序列化）。冷恢复时，`foldSubagentDescriptor()` 从持久化事件重建组合。未知版本被安全拒绝（返回 `undefined` 而非抛出异常）。

### 2.6 冷恢复（Cold Resume）

Continuable 子 Agent 通过 **session 持久化**在进程重启后存活：

1. `SubagentContinuationManager.coldResume()`：
   - 通过 `SessionQueryEngine` 从持久化观察 session
   - 校验 lineage（父 session 匹配）
   - 从持久化事件读取描述符
   - 在 continuation manager 的作用域下恢复 Agent
   - 应用持久化的 composition（persona、tool filter）
2. 不需要 provider 分发——描述符包含所有重建所需输入
3. 冷恢复要求精确的活跃父 Agent 授权

### 2.7 结果永不 Reject（Post-Publication）

核心可靠性不变量：**publication 之后，`SubagentRun.result` 永不 reject**。

`settleRunResult()` 将所有失败扁平化：

```typescript
export async function settleRunResult(parts: RunResultSettlement): Promise<SubagentResult> {
  try {
    const result = await parts.attempt()
    return parts.cancelled()
      ? { output: parts.collectOutput(), stopReason: 'aborted' }
      : normalizeSubagentDiagnostic(result)
  } catch (error: unknown) {
    if (parts.cancelled()) return { output: parts.collectOutput(), stopReason: 'aborted' }
    return { output: parts.collectOutput(), stopReason: 'error', diagnostic }
  }
}
```

停止原因（stop reason）类型：`completed`、`aborted`、`error`、`max-tokens`、`refusal`——可合并扩展。

### 2.8 诊断字节限制

Provider 产生的失败诊断被限制为 **4096 UTF-8 字节**，且安全截断（不会拆分多字节序列）：

```typescript
const MAX_SUBAGENT_DIAGNOSTIC_BYTES = 4_096
```

### 2.9 协同回收阶梯（Out-of-Process）

ACP provider 实现多级回收：

1. **stdin EOF** → 子进程的持久化刷新窗口（EOF grace: 默认 6000ms）
2. **`terminate()`** → SIGTERM → grace 期 → SIGKILL（默认 3000ms）
3. **Exit proof** → 整个受管控范围的 quiescence

```typescript
export async function disposeAcpChild(child: SubprocessHandle, eofGraceMs: number): Promise<void>
```

### 2.10 子优先回收顺序

`ContinuableActivationRegistry` 确保子 Agent 在父 Agent 之前回收：

- `drainDescendants()` 计算目标根节点，先回收子节点，等待所有 materialization 完成
- `finishDisposal()` 递归回收父 Activation 前拥有的子节点
- Cordis 结构化的 owner 作用域注册在前、drain 在后，使得反向 Cordis 解开时 drain 先于作用域释放（正确的子优先顺序）

### 2.11 结算排序保证

子 Agent 消息**始终先于**结算通知：

- 所有模型产生的消息使用**固定的 Steer 投递**
- 当父 Agent 运行时，消息和结算通知进入同一个 `next-step` FIFO
- `SubagentInbox` 包装器阻止结算覆盖一个已接受的唤醒发送
- `sendWaking()` 续订 Activation 的唤醒代次

### 2.12 生命周期事件隔离

`createLifecycleEmitter()` 将每个监听器的异常独立隔离：

- 抛出异常的监听器被记录但**不影响**同级或 run
- 监听器的 rejected promise 被捕获并警告
- Provider 移除事件不会破坏回收流程

### 2.13 准入控制与血统授权

每个操作都被授权：

- **准入检查**：`assertAdmitting(agent)` 在 drain 期间拒绝新工作
- **血统检查**：`authorizeLineage()` 校验精确的活跃父 Agent 身份和 session 匹配
- **祖先追踪**：`WeakSet<Agent>` 追踪 materialization 时的精确活跃祖先
- **所有权追踪**：`ownedChildren` 阻止父 Agent 在有活跃子节点时结算
- **Hold 机制**：`holdOwnership()` 在创建前预注册子节点，带失败路径释放器

### 2.14 自然结算监视器

`watchSettlement()` 是一个异步循环，跟随每个 Activation 到自然完成：

1. 等待 Agent 变为 idle
2. 在 child lock 下，分类结算状态：`closed`、`retry`、`wait`、`ready`
3. 刷新最终 session 状态
4. 在 child lock 下，通过 `runMaintenance()` 启动回收
5. 按边界报告回收失败（聚合错误）
6. 通过结算消息通知直接父 Agent

### 2.15 错误分类与恢复

`SubagentError` 带有类型化错误码：

| 错误码 | 含义 |
|--------|------|
| `NO_PROVIDER` | Provider 未注册 |
| `DUPLICATE_PROVIDER` | Provider 重复注册 |
| `UNSUPPORTED_CAPABILITY` | 能力不匹配 |
| `UNAUTHORIZED` | 未授权操作 |
| `ACTIVATION_CLOSING` | Activation 正在关闭 |
| `PARENT_UNAVAILABLE` | 父 Agent 不可用 |
| `DRAINING` | 正在排空中 |
| `NOT_RESUMABLE` | 不可恢复 |
| `CONTINUATION_UNAVAILABLE` | 延续不可用 |
| `PERSISTENCE_UNAVAILABLE` | 持久化不可用 |
| `DUPLICATE_CHILD` | 子 Agent 重复 |
| `MODEL_DOES_NOT_SUPPORT_IMAGES` | 模型不支持图片 |
| `CANCELLED` | 已取消 |
| `ACTIVATION_TEARDOWN_FAILED` | Activation 回收失败 |

远程错误映射：`rejectPrompt()` 将内部错误码映射为稳定的 `RemoteError` 详情（`subagent/parent-unavailable`、`subagent/not-resumable`、`subagent/unauthorized` 等）。

**失败隔离**：`disposeRoots()` 聚合所有分支失败，在所有节点 settle 之后统一报告（不提前退出）。

**启动回滚**：如果 run 已发布后 catalog append 失败，run 被回收，catalog 错误被抛出。

### 2.16 结构化输出捕获

`subagent-in-process-driver/structured.ts` 实现结构化输出的两阶段提交：

1. 工具调用将值暂存在 `WeakMap<ToolExecution, ...>` 中
2. 权威的 `tools/result` 通知提交该值
3. **单调工具守卫**阻止后续调用重新打开已完成的 run
4. PTC 模式捕获等待外围的 `run_code` 结果

### 2.17 策略委派

子 Agent 继承受限策略：

- **沙箱模式**：在委派时刻从父 Agent 的显式覆盖同步捕获（在任何 await 之前）
- **审批策略**：固定为 `'never'`——子 Agent 不能请求用户审批
- 策略事件以 `source: 'delegation'` 追加到子 session 日志
- 冷恢复从持久化日志重放（永不重新捕获）

### 2.18 基于投影的列表

Subagent 枚举使用三级阶梯：

1. **活跃水位缓存**（活跃子 Agent，无 I/O）
2. **持久化投影缓存**（未播种的冷子 Agent）
3. **共享 Session 观察**，带限制并发（`COLD_READ_CONCURRENCY = 4`，其他冷子 Agent）

**每个子 Agent 隔离**：损坏/不可用的子 Agent 产生诊断行而不会使整个列表失败。生命周期见证键防止 id 重用 session 的过期条目。

---

## 可靠性方案小结

| 机制 | 解决的问题 | 目的 |
|------|-----------|------|
| ⭐ **取消信号传播（AbortSignal）** | 父 Agent 取消或超时后，子 Agent 继续运行造成资源泄漏和无效工作 | 确保取消信号贯穿整个调用链，子 Agent 在父 Agent 不再需要时立即停止，避免资源浪费 |
| ⭐ **幂等回收（Idempotent Disposal）** | 多次调用 `dispose()` 导致重复回收、状态不一致或崩溃 | 保证无论调用多少次，回收操作只执行一次，避免重复释放和竞态条件 |
| **ChildLock 串行化** | 同一子 Agent 的多个操作（发送消息、释放、回收）并发执行导致状态错乱 | 将同一子节点的所有持久化操作强制串行化，保证操作有序且互不干扰 |
| **深度限制（递归预算）** | 子 Agent 无限递归委派导致调用栈过深、资源耗尽、系统不可控 | 限制委派层级，防止无限递归，确保系统资源可控且有确定性的停止边界 |
| ⭐ **冷恢复（Cold Resume）** | 进程崩溃或重启后，continuable 子 Agent 丢失，已分配的工作无法继续 | 从持久化 session 日志重建子 Agent，使长时间运行的任务可跨进程重启存活 |
| ⭐ **结果永不 Reject 契约** | 子 Agent 发布后抛出未捕获异常，导致父 Agent 也崩溃，造成级联故障 | 将所有失败（包括异常、取消、超时）扁平化为类型化的停止原因，父 Agent 始终能获取确定性结果 |
| **诊断字节限制** | 子 Agent 产生超大错误信息，导致内存膨胀或日志存储爆满 | 限制错误诊断大小为 4096 字节，防止失控的错误信息耗尽系统资源 |
| **协同回收阶梯（多级回收）** | 进程外子进程在回收时卡住或残留僵尸进程 | 通过 stdin EOF → SIGTERM → SIGKILL 三级阶梯确保进程外子节点最终一定被终止 |
| ⭐ **子优先回收顺序** | 父 Agent 先于子 Agent 回收导致子节点成为孤儿，资源泄漏 | 强制子节点先回收、父节点后回收的拓扑排序，确保回收级联正确 |
| **结算排序保证** | 子 Agent 的结算通知先于最后一条消息到达，父 Agent 错过关键输出 | 保证消息始终先于结算通知投递，父 Agent 不会漏掉任何子 Agent 的输出 |
| **生命周期事件隔离** | 某个生命周期监听器抛出异常导致其他监听器被跳过或回收流程中断 | 每个监听器独立 try/catch，单个失败不影响其他监听器和整体流程 |
| ⭐ **准入控制与血统授权** | 非父 Agent 或过期 Agent 越权操作子 Agent，导致安全漏洞或状态污染 | 每个操作验证精确的活跃 Agent 身份和 session 血统，防止越权和身份伪造 |
| **自然结算监视器** | 子 Agent 完成后未被及时回收，资源长期占用 | 异步循环跟踪每个 Activation 到自然完成，自动触发回收并通知父 Agent |
| **错误分类与恢复** | 不同类型的错误被混为一谈，调用者无法区分可恢复和不可恢复的失败 | 用稳定错误码精确分类每种失败场景，调用者可据此做出正确的恢复决策 |
| **结构化输出两阶段提交** | 结构化输出在确认前被读取，或已完成后再被修改，导致数据不一致 | 暂存→确认两阶段提交，配合单调守卫确保结构化输出的原子性和不可变性 |
| **策略委派** | 子 Agent 继承父 Agent 的宽松权限，可绕过安全限制（如请求用户审批） | 在委派时刻同步捕获受限策略（审批固定为 never），确保子 Agent 权限不超出预期 |
| **基于投影的列表** | 枚举子 Agent 列表时某个损坏的子节点导致整个列表加载失败 | 三级阶梯查询 + 每个子节点故障隔离，单个损坏不影响整体列表可用性 |

---

## 重点方案详解

> 以下对标注 ⭐ 的基石性机制展开分析，说明其设计原理、执行流程和为什么不可替代。

### ⭐ 1. 结果永不 Reject 契约

这是整个 Subagent 系统的**核心可靠性不变量**。子 Agent 一旦发布（publication），其 `result` Promise 无论发生什么都必然 resolve——永不 reject。

**问题场景：级联故障**

```
父 Agent                          子 Agent
   │                                │
   ├──── start(subagent) ──────────→│
   │                                │ 运行中...
   │                                │
   │  await subagent.result         │
   │         ↓                      │  💥 未捕获异常！
   │  ❌ Promise REJECT ────────────┤
   │                                │
   │  父 Agent 也崩溃                │
   │  整个调用链断裂                  │
```

**采用契约后：故障隔离**

```
父 Agent                          子 Agent
   │                                │
   ├──── start(subagent) ──────────→│
   │                                │ 运行中...
   │  await subagent.result         │
   │         ↓                      │  💥 异常发生
   │  ✅ Promise RESOLVE ───────────┤ settleRunResult() 捕获
   │  {                             │
   │    stopReason: 'error',        │
   │    output: '...',              │
   │    diagnostic: '...'           │
   │  }                             │
   │                                │
   │  父 Agent 获取确定性结果         │
   │  根据 stopReason 决策下一步     │
```

`settleRunResult()` 是契约的执行者：

```
                ┌─────────────────────┐
                │   settleRunResult   │
                └─────────┬───────────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      try { attempt() }  catch(err)    finally
            │             │               │
            ▼             ▼               ▼
       result 成功?   cancelled?     collectOutput()
       → completed   → aborted       → error + diagnostic
```

**关键设计点：**
- `try/catch` 覆盖所有异常路径
- `cancelled` 在 catch 内外各检查一次——取消优先级高于异常
- `diagnostic` 被截断到 4096 字节，防止超大错误信息
- 停止原因类型化（`completed | aborted | error | max-tokens | refusal`），调用者可精确匹配

---

### ⭐ 2. 取消信号传播（AbortSignal）

AbortSignal 是**贯穿所有能力边界的必需参数**。这不是可选的"最佳实践"——每个操作必须接受它，否则无法通过类型检查。

**架构图：取消信号的传播路径**

```
User cancels / timeout
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │           AbortController                    │
  │           signal ──────────────────┐         │
  └────────────────────────────────────┼─────────┘
                                       │
          ┌────────────────────────────┤
          ▼                            ▼
   SubagentRuntime              ContinuationManager
   .start(signal)               .sendMessage(signal)
          │                            │
          ▼                            ▼
   ┌──────────────┐            ┌──────────────┐
   │ throwIfAbort │            │ throwIfAbort │
   │ - 启动前检查  │            │ - 投递前检查  │
   │ - 每个 await │            │ - 每个 await │
   │   之后检查    │            │   之后检查    │
   └──────────────┘            └──────────────┘
          │                            │
          ▼                            ▼
   child.dispose()              child.dispose()
   signal.removeEventListener   signal.removeEventListener
   ('abort', onAbort)           ('abort', onAbort)
```

**为什么这不可替代：**
- 没有它，父 Agent 取消后子 Agent 仍可能运行数分钟，消耗 tokens 和资源
- 每个 `await` 后的 `throwIfAborted()` 确保取消有**确定的响应时间上限**（不超过单次 await 的耗时）
- `removeEventListener` 防止内存泄漏——每次取消路径都清理自己的监听器

---

### ⭐ 3. 幂等回收（Idempotent Disposal）

**问题：多路径同时触发回收**

```
    cancel('timeout')
         │
         ▼
    dispose() ──────┐
         │          │
         ▼          ▼
    ┌─────────┐  ┌─────────┐
    │ worker  │  │ child   │
    │ .term() │  │ .close()│  ← 两个路径同时操作同一个子 Agent
    └─────────┘  └─────────┘
         │          │
         ▼          ▼
       💥 状态冲突 / 重复释放
```

**解决方案：记忆化 Promise**

```
第一次 dispose()
     │
     ├── disposal === undefined?  YES
     ├── disposal = parts.teardown()
     ├── return disposal ──────────────┐
     │                                  │
第二次 dispose()                        │
     │                                  │
     ├── disposal !== undefined?  NO ──┤
     └── return disposal  ← 返回同一个 Promise
                                       │
                                       ▼
                              teardown 只执行一次
```

所有相关操作都遵循此模式：

| 操作 | 记忆化方式 |
|------|-----------|
| `SubagentRun.dispose()` | `let disposal: Promise<void> \| undefined` |
| `SubagentInbox.close()` | `closingPromise` 首次安装后复用 |
| `cancel(reason?)` | 首个 reason 胜出，后续调用无副作用 |
| `settleResult()` | `this.settled` 守卫 |

---

### ⭐ 4. 子优先回收顺序

**问题：父先于子回收 → 孤儿进程**

```
错误顺序 ❌                    正确顺序 ✅
                                
  dispose(Parent)               drainDescendants()
       │                              │
       ▼                              ▼
  Parent scope 释放              ┌─ dispose(Child₁)
       │                        ├─ dispose(Child₂)
       ▼                        ├─ dispose(Child₃)
  Child 成为孤儿！              └─ 等待所有子 settle
       │                              │
       ▼                              ▼
  资源永远无法回收               finishDisposal(Parent)
```

**Cordis 作用域保证正确顺序：**

```
┌─────────────────────────────────────────┐
│          Cordis Context (父 Agent)       │
│                                          │
│   ownerCtx.onDispose(() => {            │
│     注册顺序:                             │
│     ① ownerCtx (子持有者作用域)            │
│     ② drain     (排空处理器)              │
│                                          │
│     反向解开时:                           │
│     ② drain 先执行 → dispose 所有子       │
│     ① ownerCtx 后释放 → 父作用域安全退出   │
│   })                                     │
└─────────────────────────────────────────┘
```

**关键保证：**
- `ownedChildren` Set 追踪父拥有的所有活跃子节点
- `holdOwnership()` 预注册——在子创建前就占位，失败时自动释放
- `drainDescendants()` 递归处理，从叶子向上回收

---

### ⭐ 5. 冷恢复（Cold Resume）

Continuable 子 Agent 在进程重启后可以从持久化 Session 日志完整重建。

```
进程 A (崩溃前)                           进程 B (重启后)
───────────────                          ───────────────

  session.log ───────── 磁盘持久化 ──────→ session.log
  ┌──────────┐                           ┌──────────┐
  │ descriptor│  ◄── 子 Agent 的完整     │ descriptor│
  │ persona   │      配置快照            │ persona   │
  │ tools     │                         │ tools     │
  │ model     │                         │ model     │
  ├──────────┤                           ├──────────┤
  │ messages  │  ◄── 对话历史            │ messages  │
  │ turns     │                         │ turns     │
  └──────────┘                           └──────────┘
                                               │
                    coldResume() 流程:          │
                                               ▼
                    ① SessionQueryEngine
                       .observe(sessionId)
                           │
                           ▼
                    ② 验证 lineage
                       parentSession === 当前活跃父 Session?
                           │ YES
                           ▼
                    ③ foldSubagentDescriptor()
                       从事件中重建 composition
                           │
                           ▼
                    ④ 在 ContinuationManager 作用域下
                       恢复 Agent
                           │
                           ▼
                    ⑤ 应用 persisted
                       persona + toolFilter
                           │
                           ▼
                    ⑥ ✅ Agent 恢复运行
```

**为什么这是基石机制：**
- 长时间运行的子 Agent（如代码分析、大规模重构）可能跨越数小时
- 没有冷恢复，进程重启意味着所有进度丢失
- 描述符包含重建所需的全部信息——不需要 provider 重新分发

---

### ⭐ 6. 准入控制与血统授权

每个操作在执行前必须通过两层安全检查。

```
                  操作请求到达
                       │
                       ▼
              ┌─────────────────┐
              │ assertAdmitting │  ← 第一层：准入控制
              │ (agent)         │
              └────────┬────────┘
                       │
            ┌──────────┼──────────┐
            ▼                     ▼
      正在 drain?             正常状态
      → DRAINING 错误         → 通过
                                   │
                                   ▼
              ┌─────────────────┐
              │ authorizeLineage│  ← 第二层：血统验证
              │ (agent)         │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    Agent 不匹配   Session 不匹配   全部匹配
    → UNAUTHORIZED → UNAUTHORIZED  → ✅ 执行操作

授权检查的技术细节:
┌──────────────────────────────────────────────┐
│                                              │
│  WeakSet<Agent> 追踪 materialization 时      │
│  的精确活跃祖先                                │
│                                              │
│  不是简单比较 sessionId ——                    │
│  过期或伪造的身份在 WeakSet 中不存在            │
│                                              │
│  ownedChildren 防止父在有活跃子时结算          │
│  holdOwnership() 预注册 + 失败路径释放器       │
│                                              │
└──────────────────────────────────────────────┘
```

**为什么不可替代：**
- 仅比较 `sessionId` 字符串可以被重放攻击绕过
- `WeakSet<Agent>` 绑定到精确的内存对象引用，无法伪造
- 准入控制在 drain 期间阻止新工作——没有它，优雅关闭不可能

---

## 3. 配置选项

`tool-subagent` Config：

| 字段 | 默认值 | 可靠性作用 |
|------|--------|-----------|
| `maxDepth` | `3` | 递归预算（0 = 禁止，`'provider-managed'` = 无上限） |
| `enableRunInBackground` | — | 控制前台/后台默认 |
| `backgroundMode` | — | `'one-shot'`（Task 支持）或 `'continuable'`（持久对话） |
| `agentOptions` | — | 固定的 provider/model/reasoning effort/max tokens |
| `toolFilter` | — | 每个子 Agent 的工具范围（allow/deny 列表） |
| `persona` | — | 每个子 Agent 的 persona |

ACP provider Config：

| 字段 | 默认值 | 可靠性作用 |
|------|--------|-----------|
| `disposeEofGraceMs` | `6000` | stdin EOF 后的优雅期 |
| `disposeGraceMs` | `3000` | SIGTERM→SIGKILL 的优雅期 |
| `cwd` | — | 子进程工作目录配置覆盖 |
| `permission` | — | 子进程权限提示的自动应答策略 |

---

## 4. 架构可靠性原则总结

1. **"大声失败，不静默降级"** — 能力不匹配在启动时即拒绝，而非使用时
2. **发布后结果永不 reject** — 所有失败扁平化为类型化的停止原因
3. **万物幂等** — 回收、inbox 关闭、生命周期边界
4. **每个子操作串行化** — `ChildLock` 防止竞态条件
5. **进程内状态 + 持久化存储** — Activations 是临时的，sessions 是持久的
6. **子优先回收** — 结构化作用域排序确保正确的回收级联
7. **必需的取消** — `AbortSignal` 在每个能力边界都是强制的
8. **描述符版本化的冷恢复** — 组合状态可仅从 session 日志重建
9. **监听器隔离** — 单个观察者失败无法破坏接缝
10. **精确身份授权** — 每个操作检查精确的活跃 Agent 身份，而非仅 session id