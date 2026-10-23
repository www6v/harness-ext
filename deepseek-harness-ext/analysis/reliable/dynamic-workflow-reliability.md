# Dynamic Workflow 可靠性分析

> 分析对象：`deepseek-harness` 中的 Dynamic Workflow 子系统
> 包路径：`packages/workflow/`

---

## 1. 概述

**Dynamic Workflow** 是 `deepseek-harness` 中**由模型编写、脚本驱动的多 Agent 编排接缝**。模型编写普通 JavaScript 编排脚本（带顶层 `await`），将工作扇出到多个 subagent 子节点，最终返回单个 JSON 值。

Workflow 调用携带三个要素：

- **`meta`** — 纯 JSON 身份块（`name`、`description`、`whenToUse`、`phases`）。仅作为数据，永不求值。
- **`script`** — 普通 JS 体（无 `export const meta` 语句，无 TypeScript）。
- **`args`** — 可选 JSON 输入，暴露为 `args` 全局变量。

脚本内可使用五个 hook：`agent()`、`parallel()`、`pipeline()`、`phase()`、`log()`。

两个模型可见工具暴露此接缝：

- **`workflow`**（来自 `@deepseek-ai/dsh-tool-workflow`）— 通用扇出编排
- **`ralph`**（来自 `@deepseek-ai/dsh-tool-ralph`）— 固定的 fresh-agent 迭代循环

### 包结构（`packages/workflow/` 下）

| 包 | 角色 |
|---|---|
| `workflow/` | 服务定义（`ctx.workflowEngine`）、类型、事件、`WorkflowError`、不变量 |
| `workflow-worker-thread/` | 服务提供者：每个 run 一个 `node:worker_threads` Worker |
| `tool-workflow/` | 模型可见 `workflow` 工具 + 持久化 Session 记录 |
| `tool-ralph/` | 模型可见 `ralph` 工具，构建为固定 workflow 脚本 |

### 关键文件

| 文件 | 角色 |
|------|------|
| `packages/workflow/workflow/src/index.ts` | `WorkflowEngine` 抽象类、`WorkflowError`（带 `fatal` 标志）、事件声明、监听器隔离 |
| `packages/workflow/workflow/src/types.ts` | 浏览器安全词汇：`WorkflowMeta`、`WorkflowResult`、`WorkflowStopReason` |
| `packages/workflow/workflow/src/runtime-types.ts` | 仅宿主的 `WorkflowStartRequest`、`WorkflowRun` |
| `packages/workflow/workflow/src/invariant.ts` | 事件配对不变量 |
| `packages/workflow/workflow-worker-thread/src/index.ts` | `WorkerThreadWorkflowEngine` 插件；`start()` 编排；meta+body 预校验 |
| `packages/workflow/workflow-worker-thread/src/host.ts` | `WorkerRun`：worker 生成、子注册、取消、优雅计时器、回收、worker 死亡处理、滞留 agent 合成 |
| `packages/workflow/workflow-worker-thread/src/runtime.ts` | `WorkflowExecution`：vm 上下文、hook 实现、致命/可空错误纪律、`drive()` 永不 reject 契约 |
| `packages/workflow/workflow-worker-thread/src/session.ts` | `runWorkerSession`：Ready/Go 握手、子 RPC 桥 |
| `packages/workflow/workflow-worker-thread/src/protocol.ts` | 类型化的 Worker↔Host 消息协议 |
| `packages/workflow/workflow-worker-thread/src/realm.ts` | `materializeFromRealm`（JSON 值边界）、`renderThrown`（永不抛出的异常渲染器） |
| `packages/workflow/workflow-worker-thread/src/meta.ts` | `validateMeta` 结构校验器 |
| `packages/workflow/tool-workflow/src/index.ts` | `workflow` 工具：schema、描述、执行生命周期、持久化 Session 记录 |
| `packages/workflow/tool-workflow/src/invariant.ts` | 持久化记录协议校验器 |
| `packages/workflow/tool-ralph/src/index.ts` | `ralph` 工具：固定脚本、结构化输出 schema、轮次校验、能力门控 |
| `packages/client/ui-workflow-run/src/client/workflow-definition.ts` | `workflow-run` Conversation Node；状态派生含 `interrupted` |

---

## 2. 执行流程

### 2.1 启动阶段

`WorkerThreadWorkflowEngine.start()`（同步）：

1. **校验 `meta`**（`validateMeta`）：拒绝未知字段、缺失名称、格式错误的阶段定义——以 `META_INVALID` 错误报告每个违规项
2. **解析脚本体**（`assertBodyParses`）：使用与 worker 编译相同的 `vm.Script` 包装器——拒绝时以 `SCRIPT_PARSE` 错误
3. **解析 subagent provider 路由**和每个 run 的 `maxTotalAgents`（对照部署上限）
4. **生成新的 `Worker`**（每个 run 一个），立即返回 `WorkerRun` 句柄

### 2.2 Worker 握手（`session.ts`）

- Worker 发送 `Ready` 并等待 `Go`
- 如果 `Cancel` 在 `Go` 之前到达 → 释放门控进入已取消驱动——**脚本体永不执行**

### 2.3 运行时（`runtime.ts`）

`WorkflowExecution` 在 vm 上下文中运行脚本体并暴露五个 hook。**`drive()` 永不 reject**——每个失败映射为带 `stopReason` 的 `WorkflowResult`。

### 2.4 子 RPC（`protocol.ts`）

每个 `agent()` 调用发送 `ChildStart` RPC 到宿主；宿主通过 `ctx.subagents` 启动 subagent，归属到 run 的父 agent，回复 `ChildStarted`/`ChildStartError`。结果通过 `ChildSettled`/`ChildFailed` 流回；回收通过 `ChildDispose`/`ChildDisposed`。

### 2.5 回收（`host.ts` 的 `dispose()`）

幂等。按需取消 → 立即启动宿主驱动的子回收（防止卡住的 worker 阻塞清理）→ 等待结果 + 子 quiescence 直到优雅期 → 无条件 `worker.terminate()` → 最终幸存子清扫。

### 2.6 结果结算（Result NEVER Rejects 契约）

`WorkflowResult` 总是以三种 `stopReason` 之一结算：

| stopReason | 说明 |
|------------|------|
| `completed` | 脚本运行到最终 `return`；`value` 是物化的 JSON |
| `cancelled` | run 被取消（调用者 `cancel()`、signal abort 或优雅强制结算） |
| `error` | 脚本抛出异常、致命 `WorkflowError` 传播、worker 死亡或结果物化失败 |

**先到先得终端声明**：已接受的外部取消覆盖后续非取消的 worker 结果；先声明的结果或死亡不能被重入的清理回调重写。

---

## 3. 可靠性机制

### 3.1 两类失败处理——致命 vs 普通

代码在**致命错误**和**普通子失败**之间划出清晰界限：

| 类别 | 行为 | 示例 |
|------|------|------|
| **致命 `WorkflowError`**（`fatal: true`） | `parallel()` 和 `pipeline()` **重新抛出**而非置 null。大声杀死脚本。 | 错误参数、未知/延迟选项（`effort`/`isolation`/`agentType`）、不支持的 schema、触发上限（`AGENT_CAP`/`ITEM_CAP`）、接缝启动失败（`AGENT_START`）、不可序列化的边界值（`RESULT_UNSERIALIZABLE`）、取消（`CANCELLED`） |
| **普通失败** | `agent()` 解析为 `null`；`pipeline`/`parallel` 项解析为 `null` 并跳过剩余阶段。 | 子 run 非 complete 停止原因、阶段内普通脚本抛出异常 |

`WorkflowError` 继承 `HarnessError`，携带机器可路由的 `code`，并通过**宿主域的 `instanceof`** 检查：脚本域构造的对象永远无法通过该检查，因此致命性**不可伪造或意外丢失**。

### 3.2 超时管理

| 超时 | 位置 | 默认值 | 用途 |
|------|------|--------|------|
| **`syncTimeoutMs`** | `WorkerLimits`（vm） | 5000 ms | 脚本在 worker 内部的初始同步片段的 VM 超时。阻止首次同步自旋永久阻塞 |
| **`disposeGraceMs`** | 宿主（`WorkerRun`） | 5000 ms | 取消后未结算脚本可继续运行的时间上限，之后强制结算 `cancelled` 并 `terminate()` worker |

所有优雅计时器都是 `unref()` 的，因此**永不阻止进程退出**。

### 3.3 取消——有界且全面

取消是优先级最高、多层级的机制：

1. `cancel(reason?)` 幂等；首个原因胜出
2. 向 worker 发送 `Cancel` → worker 的 hook 在**下一次 await** 时开始抛出 `WorkflowError('CANCELLED')`
3. 中止所有待处理和已发布的子节点共享的**唯一权威 `AbortController` signal**
4. 启动 `disposeGraceMs` 计时器
5. 如果 run 在截止时间仍未结算：`terminalClaimed = true`，为每个滞留的 agent 合成 `workflow/agent-end`（outcome `'cancelled'`），解析为 `cancelled`，调用 `worker.terminate()`
6. **启动信号处理**：如果在 `start()` 时 `AbortSignal` 已中止 → 在脚本体运行前就取消
7. **`throwIfCancelled()`** 在每个 hook 入口和每次向事件循环让步的 `await` 之后检查。如果取消发生在宿主启动和 continuation 恢复之间 → 回收新鲜子节点而非保留它活跃

### 3.4 并发与失控循环防护

| 限制 | 默认值 | 用途 |
|------|--------|------|
| `maxConcurrentAgents` | `0` → 自动 `min(16, max(1, cores - 2))` | 并发 `agent()` 上限（FIFO 槽获取） |
| `maxTotalAgents` | `1000` | 每个 run 的总 `agent()` 调用次数——失控循环防护 |
| `maxItemsPerCall` | `4096` | 一次 `parallel()`/`pipeline()` 接受的项数 |

每个 run 的 `maxTotalAgents` 可以降低（但永不提高）配置上限。Ralph 将其 `maxRounds` 作为此上限传入，确保轮次预算与失控防护一致。

槽获取是 FIFO 的；取消时拒绝所有排队中的等待者。

### 3.5 值边界（跨域物化）

`materializeFromRealm`（`realm.ts`）将离开 vm 进入普通 JSON 的值进行物化，拒绝：

- 函数、Symbol、BigInt、嵌套 `undefined`、非有限数字
- 异质原型（仅接受 `null` 或 `Object.prototype` 链）
- 循环引用、稀疏数组、Symbol 键属性
- 带非索引属性的数组

`"__proto__"` 键通过 `Object.defineProperty` 变为自有数据属性，而非原型修改。Getter 正常运行；抛出异常的 getter 大声失败。

此边界是**序列化契约**——子结果在从宿主传到 worker 之前被投影和快照。

### 3.6 幂等操作

- **`dispose()`**：幂等——`disposed` Promise 在首次调用时记忆化；后续调用加入同一个遍历。每个子的回收按 `callId` 记忆化，使 worker RPC、宿主取消、死亡清理和公共回收全部加入同一个操作
- **`cancel()`**：幂等；首个原因胜出；对已结算和已声明终端的 run 提供保护
- **`settleResult()`**：由 `this.settled` 守卫；解除优雅计时器
- **`endAgent()`**：使用 `liveAgents` 分类账（按 seq 的 Map）；同一 seq 的第二次 end 被丢弃。保证**每个已启动子节点恰好一个 `workflow/agent-end`**，覆盖所有停止路径

### 3.7 Worker 死亡处理

监控三个 worker 级信号：

- `error` → `onWorkerDeath(message, false)`
- `messageerror` → `onWorkerDeath(message, false)`
- `exit` → `onWorkerDeath(message, true)`

**第一个**死亡信号在清理回调之前关闭**消息准入屏障**（`workerDeathObserved = true`）——防止崩溃前排队的消息在 `workflow/end` 之后创建工作或叙述。然后：

1. 认领终端结果（如果未认领）
2. 收割子节点（中止 + 回收）
3. 通过 `endStrandedAgents()` 合成缺失的 `agent-end` 事件，结果为 `'cancelled'`
4. 结算为 `error`（如果已请求取消则为 `cancelled`）

### 3.8 事件配对与生命周期不变量

两个不变量伴侣强制执行正确性：

**`dsh-workflow/invariant`**（`packages/workflow/workflow/src/invariant.ts`）：

- 每个 `workflow/*` 事件必须与匹配的 `workflow/start` 共享相同的身份快照
- `workflow/agent-start`/`workflow/agent-end` 按 `seq` 配对；身份（label、phase、childId）必须精确匹配
- `workflow/end` 要求所有已启动 agent 均配对；`agentsStarted` 必须覆盖每个观察到的 start
- `error` 存在当且仅当 `stopReason !== 'completed'`
- 两阶段分发（`internal/dispatch` → event）在发布前捕获违规

**`dsh-tool-workflow/invariant`**（`packages/workflow/tool-workflow/src/invariant.ts`）：

- 在冷加载和实时追加时校验持久化 Session 记录协议
- 一个 `tool-workflow/run-start` 对应一个 run；正的唯一成员序列号
- 成员必须 start/end 配对；无开放成员时不可有 run-end；run-end 后不可有更新
- 日志尾部缺失的成员结束或 run 结束是**有效的打断证据**（非损坏）——支持部分失败恢复

### 3.9 部分失败处理与持久化记录

**持久化 Session 记录**（`tool-workflow/src/index.ts`）：

- 工具将顶层 run 投影到父 Session 的四个仅日志事件：`run-start`、`agent-start`、`agent-end`、`run-end`
- **首次追加失败策略**：失败的 Session 追加**禁用该 run 的后续所有写入**（带一次警告）。结果和清理**永不受影响**。这留下要么无记录，要么**合法的连续前缀**——永不产生损坏日志
- `run-end` 仅在结果已知且 `run.dispose()` 达到 quiescence 后才写入
- 嵌套传输调用不写记录（仅顶层调用写入）

**UI 重建**（`ui-workflow-run`）：

- `workflow-run` Conversation Node 按加载窗口从持久化事实重建
- 状态派生：`running`、`completed`、`failed`、`cancelled` 或 `interrupted`（关闭的 turn/step 无 run-end）
- **`interrupted` 状态是部分失败恢复信号**——日志尾部缺失的 run 或成员结束是工作停止位置的真实证据
- 状态驱动的展开：活跃/异常时自动展开，干净完成时自动折叠，保留焦点，在外层 hide/reopen 后仍存活

### 3.10 Ralph 特有可靠性

`ralph` 工具为其固定循环增加了额外的可靠性层：

- **结构化输出契约**：每轮要求校验的 `RalphRoundReport`，每个状态（`continue`/`complete`/`blocked`）有明确语义。字符串必须规范化；语义规则强制执行（如 `continue` 要求 nextSteps 且 blocker 为空）
- **超大交接保护**：`maxHandoffChars`（默认 16384）——超大报告大声失败而非静默截断
- **`maxResultChars`** 限制面向父代理的终端文本（含外层信封）
- **轮次失败**：普通子失败（非 complete 停止）→ `round-failed`，带失败轮次号 + 上次成功交接；工具将其作为工具错误暴露
- **Provider 能力门控**：启动前，Ralph 要求 provider 支持结构化输出且不继承父上下文（`inheritsParentContext: false`）。Fork 类 provider 大声失败
- **无重试策略**：Ralph 有意识地不加重试；轮次失败则结束 run 并保留上次良好交接

### 3.11 防御性模式

| 模式 | 位置 | 说明 |
|------|------|------|
| **清理的 worker 环境** | `workerSpawnEnv` | 无环境凭据、无 loader 标志。仅平台临时路径（Win: 从 `os.tmpdir()` 推导的 `TMP`/`TEMP`，非裸 env）和源码模式的 `TSX_TSCONFIG_PATH`。阻止代理 URL 凭据通过 `process.env` 泄漏 |
| **不可处理的 rejection 隔离** | `runtime.ts` 的 `contain()` | 每个返回的 Promise 都附加了 rejection 消费者，丢弃的脚本 Promise 无法产生未处理 rejection 杀死 worker |
| **`renderThrown()`** | `realm.ts` | 完全（永不抛出）的任何抛出值渲染——优先 `stack`，回退 `message`，然后 `String()`，最后固定标签 `'[unrenderable thrown value]'`。在结果契约必须持有的任何地方使用 |
| **监听器隔离** | `emitWorkflowEvent` | 每个监听器 try/catch；抛出异常的订阅者被记录，永不传播，不能使后续监听器挨饿。每个监听器收到自己的负载克隆 |
| **`childAdmissionFailure()`** | 宿主 | 一旦 run 已取消、worker 已消失或终端结果已认领，中央守卫拒绝新的子启动。子节点绝不能在已中止的信号上启动 |
| **Ready/Go 握手** | `session.ts` | 防止已中止的启动信号与 worker 启动竞态并执行同步片段 |

---

## 可靠性方案小结

| 机制 | 解决的问题 | 目的 |
|------|-----------|------|
| ⭐ **两类失败分离（致命 vs 普通）** | 所有错误被同等对待——一个子任务失败就中止整个编排，或致命错误被静默吞掉 | 致命错误（配置错误、上限触发、取消）立即杀死脚本；普通子失败解析为 `null` 并跳过剩余阶段。致命性通过宿主域 `instanceof` 不可伪造 |
| **syncTimeoutMs（初始同步超时）** | 模型生成的脚本包含无限循环或死锁，worker 线程永久阻塞 | 限制脚本首次同步执行为 5 秒，超时即终止，防止单个编排耗尽 worker 线程 |
| **disposeGraceMs（回收优雅期）** | 取消后脚本无限期运行不停止，或父 Agent 阻塞等待回收完成 | 取消后最多等待 5 秒，超时后强制 `worker.terminate()` 并合成 `cancelled` 结果 |
| ⭐ **有界取消（多层级）** | 取消信号只到达部分层级，子 Agent 未收到取消通知继续空转 | 7 层取消覆盖：幂等 cancel() → worker Cancel 消息 → 所有子 AbortSignal → disposeGraceMs 计时器 → 滞留 agent 合成 → 启动前信号检查 → 每个 await 后检查 |
| **并发上限（maxConcurrentAgents）** | 脚本同时启动过多子 Agent，系统资源（内存/CPU/连接）耗尽 | 自动根据 CPU 核数计算并发上限并 FIFO 槽获取，超出并发的调用排队等待 |
| **总调用上限（maxTotalAgents）** | 脚本中的失控循环无限生成子 Agent，导致拒绝服务 | 每个 run 最多 1000 次 `agent()` 调用，Ralph 用 `maxRounds` 作为此上限 |
| **单次项数上限（maxItemsPerCall）** | 单次 `parallel()`/`pipeline()` 传入超大数组导致内存溢出 | 限制为 4096 项，超出拒绝 |
| ⭐ **值边界物化（materializeFromRealm）** | vm 域泄漏函数/Symbol/循环引用到宿主域，导致序列化失败或原型污染 | 严格拒绝所有非纯 JSON 值，`__proto__` 通过 `Object.defineProperty` 安全处理，getter 异常大声失败 |
| ⭐ **dispose() 幂等** | 多个代码路径同时触发回收，导致重复释放或 use-after-free | 首次调用记忆化 Promise，所有后续调用返回同一个 Promise；每个子按 `callId` 去重 |
| **cancel() 幂等** | 取消被多次调用产生重复副作用 | 首次原因胜出，已结算/已声明终端的 run 被保护 |
| **endAgent() 恰好一次保证** | 同一子 Agent 的结束事件被多次写入，导致投影校验失败 | `liveAgents` Map 按 seq 去重，保证每个 agent 恰好一个 `agent-end` |
| ⭐ **Worker 死亡处理：消息准入屏障** | worker 崩溃后，崩溃前排队的消息继续被处理，产生无效工作或覆盖死亡结果 | 首个死亡信号立即设置 `workerDeathObserved = true`，阻止任何后续消息被处理 |
| ⭐ **Worker 死亡处理：滞留 agent 合成** | worker 死亡后，已启动但未结束的子 Agent 在持久化记录中永久"开放" | 遍历 `liveAgents`，为每个未结束的 agent 合成 `agent-end: cancelled` |
| ⭐ **事件配对不变量（引擎层 + 工具记录层）** | agent-start 无对应 agent-end，workflow-end 时还有开放 agent | 运行时 + 持久化双重校验每个事件的配对完整性；缺失项在日志尾部时识别为打断证据而非损坏 |
| ⭐ **首次追加失败策略** | Session 日志写入失败后继续尝试写入，产生损坏的部分日志 | 首次失败后禁用后续所有写入，留下无记录或合法连续前缀，永不产生损坏数据 |
| **interrupted 状态（UI 层）** | 进程被 kill 后，用户无法知道 workflow 执行到了哪一步 | 从关闭的 turn/step 无 run-end 事件诚实派生 `interrupted` 状态，显示停止位置 |
| **Ralph 结构化输出契约** | 模型返回格式错误的轮次报告被静默接受，导致后续轮次基于垃圾数据运行 | 每轮严格校验 schema + 语义规则（如 `continue` 必须有 nextSteps），不合法即拒绝 |
| **Ralph 超大交接保护** | 模型返回超长交接文本，截断后丢失关键信息 | `maxHandoffChars` 限制下超额报告大声失败而非截断 |
| **Ralph Provider 能力门控** | 使用 fork provider（继承父上下文）导致 Ralph 轮次间状态污染 | 启动前要求 provider 支持结构化输出且 `inheritsParentContext: false` |
| **清理的 worker 环境** | worker 继承父进程的环境变量，泄漏凭据和敏感配置 | 仅传递平台临时路径，清除所有凭据和 loader 标志 |
| **不可处理 rejection 隔离（contain）** | 脚本 Promise 的未处理 rejection 导致 worker 进程被 Node.js 杀死 | 每个返回的 Promise 附加 rejection 消费者，丢弃的 Promise 无法升级为致命错误 |
| **renderThrown() 永不抛出** | 结果契约要求渲染异常信息，但渲染过程自身抛出异常导致结果丢失 | 多级降级渲染：stack → message → String() → 固定标签，保证任何值都能渲染 |
| **监听器隔离** | 一个事件监听器抛出异常导致其他监听器被跳过 | 每个监听器独立 try/catch + 独立负载克隆，单个失败被记录但不传播 |
| **childAdmissionFailure 守卫** | 取消/死亡后仍有新的子 Agent 被启动 | 中央守卫在取消/worker 消失/终端已认领时拒绝所有新子启动 |
| **Ready/Go 握手** | 取消信号在 worker 启动前到达，但 worker 仍执行了脚本的同步片段 | 先发 Ready 等 Go；如果 Cancel 在 Go 前到达，释放门控进入已取消驱动，脚本永不执行 |

---

## 重点方案详解

> 以下对标注 ⭐ 的基石性机制展开分析，说明其设计原理、执行流程和为什么不可替代。

### ⭐ 1. 两类失败分离（致命 vs 普通）

这是 Dynamic Workflow **错误处理的核心哲学**。不是所有失败都应该中止编排，但也不是所有失败都应该被吞掉。

**错误分类决策树：**

```
         agent() / parallel() / pipeline() 中的异常
                        │
                        ▼
              ┌──────────────────┐
              │ isFatalWorkflow  │
              │ Error(err)?      │
              └────────┬─────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
      致命错误                    普通错误
   (fatal: true)              (非 WorkflowError
                              或 fatal: false)
          │                         │
          ▼                         ▼
  ┌─────────────────┐      ┌─────────────────┐
  │ parallel/       │      │ agent()         │
  │ pipeline:       │      │ → resolve(null) │
  │ → RE-THROW     │      │                 │
  │                 │      │ pipeline 项:    │
  │ 杀死整个脚本     │      │ → 该项变 null    │
  │                 │      │ → 跳过剩余阶段   │
  │ run → 'error'   │      │                 │
  └─────────────────┘      │ run 继续执行     │
                           └─────────────────┘

致命错误来源              普通失败来源
┌──────────────────┐    ┌──────────────────┐
│ CANCELLED        │    │ 子 agent 非       │
│ AGENT_CAP        │    │ completed 停止    │
│ ITEM_CAP         │    │ 原因              │
│ AGENT_START      │    │                  │
│ RESULT_UNSERIAL  │    │ 脚本内的普通      │
│ IZABLE           │    │ throw new Error  │
│ 错误的 effort/   │    │                  │
│ isolation 参数   │    │ Promise reject   │
└──────────────────┘    └──────────────────┘
```

**致命性不可伪造的原理：**

```
  ┌──────────────────────┐     ┌──────────────────────┐
  │  Host Realm (宿主域)  │     │  VM Realm (脚本域)    │
  │                      │     │                      │
  │  WorkflowError       │     │  throw new Error(...)│
  │  instanceof 检查       │     │                      │
  │                      │     │  脚本构造的对象永远     │
  │  只有宿主域构造的错误   │     │  不是宿主域            │
  │  才能通过检查          │     │  WorkflowError 的     │
  │                      │     │  instanceof           │
  └──────────────────────┘     └──────────────────────┘

  脚本中的 throw new Error("fatal") 永远不能
  通过 isFatalWorkflowError() 检查
  → 致命性只能由系统决定，不能由脚本伪造
```

**为什么这是基石：**
- 如果所有错误都中止编排，一个子任务失败就导致整批工作白费
- 如果所有错误都被吞掉，配置错误（如错误的 provider 名称）会静默失败
- `instanceof` 跨域检查保证致命性不可伪造——脚本不能"升级"普通错误的级别

---

### ⭐ 2. 有界取消（多层级）

取消不是发一个信号就完事——它是覆盖 7 个层级的纵深防御体系。

**取消传播路径图：**

```
  cancel(reason?) 被调用
        │
        ▼
  ╔══════════════════════════════════════════════════╗
  ║  Layer 1: cancel() 幂等守卫                       ║
  ║  首个 reason 胜出，已结算的 run 被保护              ║
  ╚══════════════════════════════════════════════════╝
        │
        ▼
  ╔══════════════════════════════════════════════════╗
  ║  Layer 2: worker.postMessage('Cancel')           ║
  ║  Worker 收到 Cancel → 所有 hook 在下次 await       ║
  ║  开始抛出 WorkflowError('CANCELLED')             ║
  ╚══════════════════════════════════════════════════╝
        │
        ▼
  ╔══════════════════════════════════════════════════╗
  ║  Layer 3: AbortController.abort()                ║
  ║  所有待处理和已发布子 Agent 共享的 signal 被中止    ║
  ║  → 子 Agent 的 AbortSignal 监听器触发回收          ║
  ╚══════════════════════════════════════════════════╝
        │
        ▼
  ╔══════════════════════════════════════════════════╗
  ║  Layer 4: disposeGraceMs 计时器启动 (5s)          ║
  ║  unref() 的 — 不阻止进程退出                      ║
  ╚══════════════════════════╤═══════════════════════╝
                             │
                   5 秒后仍未结算?
                             │
                             ▼
  ╔══════════════════════════════════════════════════╗
  ║  Layer 5: terminalClaimed = true                 ║
  ║  为每个滞留 agent 合成 agent-end: cancelled       ║
  ║  run 结算为 { stopReason: 'cancelled' }          ║
  ║  worker.terminate() 无条件终止                    ║
  ╚══════════════════════════════════════════════════╝

  额外防御层:
  ╔══════════════════════════════════════════════════╗
  ║  Layer 6: 启动前信号检查                          ║
  ║  如果 start() 时 signal 已 aborted               ║
  ║  → Ready/Go 握手被 Cancel 替代                    ║
  ║  → 脚本体永不执行                                 ║
  ╚══════════════════════════════════════════════════╝
  ╔══════════════════════════════════════════════════╗
  ║  Layer 7: 每个 await 后的 throwIfCancelled()     ║
  ║  在 hook 入口和每次 yield 后强制检查               ║
  ║  → 取消响应延迟不超过单次 await 的耗时              ║
  ╚══════════════════════════════════════════════════╝

时间轴:
────────────────────────────────────────────────────→
  cancel()  │ Layer 1-3  │ ...脚本运行中...  │ Layer 4-5
  被调用    │ 立即生效    │ (每个 await 被    │ 强制终止
            │            │  Layer 7 拦截)    │ 5s 上限
```

**为什么这是基石：**
- 单层取消不可靠——某个层级可能因状态卡住而失效
- 7 层覆盖确保无论 run 处于什么状态（启动中/运行中/卡住），取消最终一定生效
- disposeGraceMs 保证取消有确定性截止时间——不存在"无限等待取消完成"

---

### ⭐ 3. 值边界物化（materializeFromRealm）

Workflow 脚本运行在 `node:vm` 上下文中，与宿主域是隔离的。跨域传递的值必须经过安全物化。

**跨域数据流：**

```
  ┌──────────────────── VM Realm ────────────────────┐
  │                                                   │
  │  script:                                          │
  │    const data = {                                 │
  │      name: "ok",        ← 纯 JSON，安全            │
  │      fn: () => {},      ← 函数，拒绝               │
  │      circular: ...,     ← 循环引用，拒绝            │
  │      [Symbol()]: "x",   ← Symbol 键，拒绝          │
  │      __proto__: {...},  ← 原型污染尝试              │
  │    }                                              │
  │    return data                                    │
  │                                                   │
  └───────────────────────┬───────────────────────────┘
                          │
                          ▼
  ┌────────── materializeFromRealm ──────────────────┐
  │                                                   │
  │  遍历所有属性:                                     │
  │                                                   │
  │  ✅ name: "ok"         → 通过                      │
  │  ❌ fn: [Function]      → MaterializeError        │
  │  ❌ circular: [Circular] → MaterializeError        │
  │  ❌ [Symbol()]: "x"     → 跳过                     │
  │  ✅ __proto__: {...}    → Object.defineProperty   │
  │                           (安全处理为自有属性)       │
  │                                                   │
  │  额外检查:                                         │
  │  • 非有限数字 (NaN, Infinity) → 拒绝               │
  │  • 嵌套 undefined → 拒绝                           │
  │  • BigInt → 拒绝                                   │
  │  • 异质原型链 → 拒绝 (仅接受 null/Object.prototype) │
  │  • 稀疏数组 → 拒绝                                  │
  │  • 数组的非索引属性 → 拒绝                           │
  │                                                   │
  └───────────────────────┬───────────────────────────┘
                          │
                          ▼
  ┌──────────────── Host Realm ──────────────────────┐
  │                                                   │
  │  { name: "ok" }  ← 安全的纯 JSON                   │
  │                                                   │
  │  可被 JSON.stringify 序列化                         │
  │  可被 postMessage 传输                             │
  │  不会污染宿主域的原型链                              │
  │                                                   │
  └───────────────────────────────────────────────────┘
```

**为什么这是基石：**
- VM 域和宿主域之间的边界是安全关键点——跨域泄漏的函数/原型会造成难以调试的崩溃
- `__proto__` 的特殊处理防止了经典的原型污染攻击
- 物化失败大声暴露而非静默截断——不会出现"部分数据丢失"的隐形 bug

---

### ⭐ 4. dispose() 幂等 + endAgent() 恰好一次

多个代码路径可能同时触发回收：worker RPC、宿主取消、死亡清理、公共 dispose()。幂等保证所有路径收敛到同一个操作。

```
  回收的多条路径:
  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │ worker RPC   │  │   cancel()   │  │ worker death │
  │ ChildDispose │  │   触发回收    │  │   触发回收    │
  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
         │                 │                 │
         └─────────┬───────┴─────────┬───────┘
                   │                 │
                   ▼                 ▼
         ┌──────────────┐  ┌──────────────┐
         │  public      │  │  dispose()   │
         │  dispose()   │  │  (再次调用)   │
         └──────┬───────┘  └──────┬───────┘
                │                 │
                └────────┬────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   dispose() 守卫     │
              │                     │
              │ disposed !== undef? │
              │   → return disposed │  ← 返回记忆化的 Promise
              │                     │
              │ disposed === undef? │
              │   → 开始真正的回收   │
              └─────────────────────┘

每个子 Agent 的回收也按 callId 去重:
  ┌──────────────────────────────────────┐
  │  childDisposeMap: Map<callId, Promise>│
  │                                      │
  │  同一 callId 的第二次 ChildDispose    │
  │  请求 → 返回已存在的 Promise          │
  │  → 不会重复 terminate()              │
  └──────────────────────────────────────┘
```

**endAgent() 的恰好一次保证：**

```
  liveAgents: Map<seq, AgentRecord>

  endAgent(seq):
       │
       ▼
  liveAgents.has(seq)?
       │
  ┌────┴────┐
  ▼         ▼
 YES       NO
  │         │
  ▼         ▼
处理并    丢弃
删除       (第二次调用)
  │
  ▼
恰好一个 workflow/agent-end 事件
```

**为什么这是基石：**
- 在分布式/异步系统中，同一个操作被多次触发是常态而非异常
- dispose 不幂等 → use-after-free 或 double-free 崩溃
- endAgent 不恰好一次 → 投影校验失败（agent-start/agent-end 不配对）

---

### ⭐ 5. Worker 死亡处理

Worker 可能因任何原因死亡：脚本死循环被 syncTimeoutMs 杀死、OOM、未捕获异常。死亡处理确保不留下"开放"状态。

**死亡检测与处理全流程：**

```
  Worker 三个信号:
  ┌──────────┐  ┌──────────────┐  ┌──────────┐
  │ 'error'  │  │'messageerror'│  │  'exit'  │
  └────┬─────┘  └──────┬───────┘  └────┬─────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
        ┌──────────────┴──────────────┐
        │  第一个到达的信号触发:        │
        │  onWorkerDeath(message,     │
        │    exitSignal=true/false)   │
        └──────────────┬──────────────┘
                       │
                       ▼
  ╔══════════════════════════════════════════╗
  ║  Step 1: 消息准入屏障                     ║
  ║                                          ║
  ║  workerDeathObserved = true              ║
  ║                                          ║
  ║  此后到达的所有消息被忽略                   ║
  ║  防止崩溃前排队的消息:                      ║
  ║  - 创建新的子 Agent                       ║
  ║  - 写入 workflow/end 之后的事件            ║
  ╚══════════════════════════════════════════╝
                       │
                       ▼
  ╔══════════════════════════════════════════╗
  ║  Step 2: 认领终端结果                      ║
  ║                                          ║
  ║  if (!terminalClaimed) {                 ║
  ║    stopReason = cancelled 已请求?         ║
  ║      ? 'cancelled'                       ║
  ║      : 'error'                           ║
  ║  }                                       ║
  ╚══════════════════════════════════════════╝
                       │
                       ▼
  ╔══════════════════════════════════════════╗
  ║  Step 3: 收割子节点                        ║
  ║                                          ║
  ║  AbortController.abort()                 ║
  ║  + 回收所有活跃子 Agent                    ║
  ╚══════════════════════════════════════════╝
                       │
                       ▼
  ╔══════════════════════════════════════════╗
  ║  Step 4: 合成滞留 agent-end               ║
  ║                                          ║
  ║  for (const [seq, record] of             ║
  ║       liveAgents) {                      ║
  ║    if (!record.ended) {                  ║
  ║      合成 workflow/agent-end {            ║
  ║        seq,                              ║
  ║        outcome: 'cancelled'              ║
  ║      }                                   ║
  ║    }                                     ║
  ║  }                                       ║
  ║                                          ║
  ║  保证: 每个 agent-start 都有 agent-end     ║
  ║  → 事件配对不变量不被违反                   ║
  ╚══════════════════════════════════════════╝
                       │
                       ▼
  ╔══════════════════════════════════════════╗
  ║  Step 5: settleResult()                  ║
  ║  结算为 error 或 cancelled                ║
  ╚══════════════════════════════════════════╝
```

**为什么这是基石：**
- 消息准入屏障解决了经典的 TOCTOU 问题——崩溃与消息传递之间的竞态
- 滞留 agent 合成保证了持久化记录的完整性——不会出现"永久开放"的 agent 记录
- 不变量校验依赖 agent-start/agent-end 配对——如果没有合成，workflow-end 永远无法写入

---

### ⭐ 6. 事件配对不变量（双保险）

两份不变量伴侣分别在引擎层和工具记录层独立校验，形成纵深防御。

**双保险架构：**

```
  ┌─── 引擎层 ──────────────────────────────────┐
  │ dsh-workflow/invariant                      │
  │                                             │
  │ 校验时机: 每次 workflow/* 事件 dispatch       │
  │ 校验对象: 运行时内存中的事件流                  │
  │                                             │
  │ 规则:                                        │
  │ ① 所有事件的身份快照必须与 workflow/start 一致  │
  │ ② agent-start/agent-end 按 seq 配对          │
  │   身份(label, phase, childId) 必须完全一致     │
  │ ③ workflow/end 前所有 agent 必须已配对        │
  │   且 agentsStarted 覆盖所有 start             │
  │ ④ error 存在 ⟺ stopReason !== 'completed'  │
  │                                             │
  └─────────────────────────────────────────────┘
                       │
                       ▼
              事件写入 Session 日志
                       │
                       ▼
  ┌─── 工具记录层 ──────────────────────────────┐
  │ dsh-tool-workflow/invariant                 │
  │                                             │
  │ 校验时机: 冷加载 + 实时追加                    │
  │ 校验对象: 持久化 Session 记录                  │
  │                                             │
  │ 规则:                                        │
  │ ① 一个 run-start 对应一个 run               │
  │ ② 成员序列号唯一且为正整数                     │
  │ ③ 成员 start/end 必须配对                    │
  │ ④ 无开放成员时不可有 run-end                   │
  │ ⑤ run-end 后不可有更新                       │
  │                                             │
  │ 特殊: 日志尾部的缺失项                         │
  │ → 不是损坏，是有效的打断证据 (interrupted)      │
  └─────────────────────────────────────────────┘

两层的互补关系:
┌────────────────────────────────────────────────────────┐
│                                                        │
│  引擎层不变量                   工具记录层不变量          │
│  ────────────                  ───────────────         │
│  实时校验                      持久化校验                │
│  阻止无效事件进入日志            发现已持久化的损坏         │
│  严格: 所有违规都是错误          宽松: 尾部缺失 = 打断    │
│                                                        │
│  如果引擎层的 bug 让无效事件      如果磁盘损坏导致数据      │
│  漏过去了...                    篡改...                  │
│  → 工具记录层冷加载时发现         → 版本检查 + schema     │
│                                  校验挡住                │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**为什么这是基石：**
- 单层校验有盲区——实时校验可能被绕过，持久化校验只在加载时执行
- 两层互补：引擎层拦截运行时违规，记录层发现持久化损坏
- 尾部缺失的智能识别使得系统能区分"损坏"和"进程被 kill"——这是 UX 恢复的关键

---

### ⭐ 7. 首次追加失败策略（优雅降级）

持久化 Session 记录写入可能失败。关键设计决策：**失败就停止写，而不是反复重试产生损坏数据。**

```
正常路径:
─────────────────────────────────────────────────────→
  run-start     agent-start₁  agent-end₁  agent-start₂
  ✅            ✅            ✅           ✅
                                          
  agent-end₂   run-end
  ✅            ✅
  = 完整的合法记录

写入失败路径:
─────────────────────────────────────────────────────→
  run-start     agent-start₁  agent-end₁  agent-start₂
  ✅            ✅            ✅           ✅
                                          
  agent-end₂
  ❌ 首次 append 失败!
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │  禁用后续所有写入 (带一次警告)                  │
  │                                              │
  │  run-end → 不写入                             │
  │  后续 agent-end → 不写入                       │
  │                                              │
  │  最终持久化内容:                               │
  │  run-start                                    │
  │  agent-start₁                                 │
  │  agent-end₁                                   │
  │  agent-start₂  ← 合法连续前缀!                  │
  │                                              │
  │  UI 读取 → 看到 interrupted 状态               │
  │  → "agent-start₂ 没有 agent-end₂"             │
  │  → "run-start 没有 run-end"                   │
  │  → 诚实展示工作停止位置                         │
  └──────────────────────────────────────────────┘

错误路径（本方案避免的）:
─────────────────────────────────────────────────────→
  如果采用重试策略:
  agent-end₂  ❌ → 重试 → ❌ → 重试 → ...
  后续 agent-end  可能因时序交错而写入成功
  但 run-start 和 agent-start 是之前写入的
  
  结果: 日志中出现不可能的序列
  agent-end₂ 在 agent-start₂ 之后，但中间可能
  有其他 agent 的完整记录
  
  → 投影校验失败
  → 日志被视为损坏
```

**优雅降级的用户体验:**
```
┌────────────────────────────────────────────────────┐
│                                                    │
│  Workflow: "review-changes"                        │
│  Status: ⚡ INTERRUPTED                            │
│                                                    │
│  Phase: Review                                     │
│  ├── ✅ bugs-reviewer     completed                 │
│  ├── ✅ perf-reviewer     completed                 │
│  └── ⚡ security-reviewer  started (未完成)          │
│                                                    │
│  最后记录: agent-start "security-reviewer"           │
│  停止原因: Session 写入失败                          │
│                                                    │
│  [查看部分结果] [重新运行]                            │
│                                                    │
└────────────────────────────────────────────────────┘
```

**为什么这是基石：**
- 选择留下"合法但截断的记录"而非"损坏的记录"——这是一个关键的可靠性设计权衡
- 部分结果可被查看——已完成的 agent 输出没有丢失
- interrupted 状态 + 上次成功交接 = 用户有足够信息决定下一步（查看结果 / 重新运行 / 手动继续）
- 一次警告而非告警风暴——失败后的静默不会淹没日志

### `dsh-workflow-worker-thread` Config

| 字段 | 默认值 | 可靠性作用 |
|------|--------|-----------|
| `provider` | `'spawn'` | 宿主端 `agent()` 调用的 subagent provider |
| `maxConcurrentAgents` | `0`（自动） | 并发 `agent()` 上限；限制并行资源使用 |
| `maxTotalAgents` | `1000` | 每个 run 的总子节点上限；失控循环防护 |
| `maxItemsPerCall` | `4096` | 每次 `parallel()`/`pipeline()` 调用的项数上限 |
| `syncTimeoutMs` | `5000` | 脚本初始同步片段的 VM 超时 |
| `disposeGraceMs` | `5000` | 取消后强制结算的时限；也限制 `dispose()` |

### 每个 Run 的覆盖

- `subagentProvider` — 单次 run 的显式 provider 路由（对照已注册 provider 校验）
- `maxTotalAgents` — 可以降低但永不提高引擎上限

### `dsh-tool-workflow` Config

| 字段 | 默认值 | 可靠性作用 |
|------|--------|-----------|
| `toolName` | `'workflow'` | 重命名模型可见工具 |
| `maxResultChars` | `50000` | 渲染结果上限；更长 JSON 截断 |

### `dsh-tool-ralph` Config

| 字段 | 默认值 | 可靠性作用 |
|------|--------|-----------|
| `subagentProvider` | `'spawn'` | 新鲜结构化输出 provider |
| `maxRounds` | `256` | 轮次数的默认和部署上限 |
| `maxHandoffChars` | `16384` | 每轮结构化交接限制 |
| `maxResultChars` | `16384` | 面向父代理的终端文本限制 |

---

## 5. 设计决策边界

### 提供的能力

- ✅ 永不 reject 的结果契约
- ✅ 有界取消（带优雅计时器）
- ✅ 严格的致命-vs-普通错误分离
- ✅ 值边界物化（跨域安全）
- ✅ 事件配对不变量（运行时 + Session 记录）
- ✅ 持久化 Session 记录，追加失败时优雅降级（留下合法前缀）
- ✅ Worker 死亡处理（消息准入屏障 + 滞留 agent 合成）
- ✅ 并发上限和失控循环防护
- ✅ 幂等回收/取消/结算
- ✅ 监听器隔离
- ✅ 防御性环境清理

### 明确不提供的能力（有意的设计非目标）

- ❌ **检查点/日志/恢复** — 脚本、子进度和中间值不持久化；进程重启不能继续 run
- ❌ **后台收集** — 仅前台；父 turn 阻塞直到整个 workflow 结算
- ❌ **重试策略** — workflow 接缝和 Ralph 都不加重试。普通子失败解析为 `null`；Ralph 在轮次失败时结束 run 并保留上次良好交接
- ❌ **断路器/回退** — 未建模
- ❌ **DAG 执行/依赖解析** — 脚本是带有 `parallel()`（屏障）和 `pipeline()`（逐项链，无跨阶段屏障）的命令式程序；没有声明式 DAG，没有自动依赖解析
- ❌ **补偿/回滚** — 已完成子节点的部分工作不会在 run 失败时撤销
- ❌ **整体 run 挂钟超时** — 仅有 `syncTimeoutMs`（初始 vm 片段）和 `disposeGraceMs`（取消防限）。总运行时间上限明确标记为"后台重设计的策略旋钮"
- ❌ **Token 预算词汇** — 上限基于并发、项数和子节点数，非模型 token
- ❌ **嵌套 workflow** — workflow 脚本不接收 `workflow()` hook
- ❌ **恶意代码沙箱** — worker 线程和 vm 上下文是隔离而非安全边界。真正的沙箱需要独立进程或 isolated-vm 引擎在同一个接缝之后
- ❌ **幂等执行保证** — 每次 start 都是全新 run；无按 run-id 的去重
- ❌ **健康检查/心跳** — 未建模；worker 线程的存活通过消息流和 `exit` 事件推断

---

## 6. 总结

Dynamic Workflow 的可靠性围绕以下核心支柱构建：

1. **永不 Reject 的结果契约** — 所有代码路径（成功、取消、崩溃、超时）都产生类型化的 `WorkflowResult`
2. **有界取消** — 带优雅计时器的多层级取消，确保清理有确定性截止时间
3. **严格的两类错误分离** — 致命错误大声杀死脚本；普通子失败解析为 `null` 并跳过剩余阶段。致命性通过宿主域 `instanceof` 不可伪造
4. **值边界物化** — 每个跨域值安全地转换为纯 JSON
5. **事件配对不变量** — 代理的启动/结束始终成对出现；两份不变量伴侣（分别在引擎层和工具记录层）同时校验实时和持久化状态
6. **追加失败时优雅降级** — 持久化 Session 记录在写入失败时留下合法连续前缀（而非损坏日志），结果和清理永不受影响
7. **部分失败的真实恢复** — UI 的 `interrupted` 状态从缺失的 run-end 事件诚实派生，显示工作停止的具体位置

系统以检查点、重试、DAG 执行和补偿为代价，换取了更简单的推理模型：脚本是命令式的、run 是前台的、失败大声暴露、清理始终有界。