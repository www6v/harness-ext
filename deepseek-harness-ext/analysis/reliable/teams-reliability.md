# Teams 可靠性分析

> 分析对象：`deepseek-harness` 中的 Agent Teams 子系统
> 包路径：`packages/experimental/agent-team/`

---

## 1. 概述

**Agent Teams** 是 `deepseek-harness` 中的一个**实验性、可选加入的协调层**，将单个编码会话转变为一个由命名 Agent 组成的小型工作团队。它位于 `packages/experimental/` 下，以五个 npm 包发布：

| 包 | 角色 |
|---|---|
| `dsh-experimental-agent-team` | 核心服务：`ctx.agentTeams` — 持久花名册、邮箱、任务板 |
| `dsh-experimental-tool-agent-team` | 模型可见工具（`spawn_teammate`、`send_message`、`team_task_*` 等） |
| `dsh-experimental-agent-team-profile` | Cordis profile 包，将上述包接入 dsh 组合 |
| `dsh-experimental-agent-team-web-profile` | Web UI 覆盖层（团队面板） |
| `dsh-experimental-client-ui-agent-team` | 客户端 React 组件（团队面板） |

**核心设计原则**：每个普通运行时根（顶级 session）隐式地是其 SessionId 标识的团队的 **Lead**。没有创建事件——团队在第一个成员、消息或任务记录出现时物化。Lead 是根 session 的 agent；队友是命名的持续型子 agent。

---

## 2. 团队架构

### 2.1 花名册管理（`src/roster.ts`）

- **身份**：`TeamId` 是 Lead 的 `SessionId` 的品牌别名。每个队友通过 `randomUUID()` 分配 `SessionId`。
- **名称保留**：名称不可变、小写 kebab-case、最长 64 字符，由第一个 `provisioning` 记录保留，且**永不重用**——即使失败后也不重用。
- **阶段**：`provisioning` → `active` | `failed`。运行时状态（`running`/`idle`/`inactive`）独立派生。
- **Spawn 协议**：
  1. 仅限 Lead 授权检查
  2. 附带 `phase: 'provisioning'` 的 `team/member` 事件追加并 **flush** 到 Lead 的 session 日志
  3. 通过 `ctx.subagents.startContinuable()` 启动可继续的子 agent
  4. 初始 inbox 项在 `active` 转换前 **checkpoint**（flush 到持久化）
  5. 任何失败 → `failed` 快照被持久记录
- **上下文模式**：`fresh`（无 Lead 历史）或 `fork`（一次性继承 Lead 的已完成 turn 前缀）

### 2.2 协调架构（`src/index.ts` — `TeamService`）

`TeamService` 是一个**门面**，组合了五个内部所有者：

```
TeamService
├── TeamActivity          — 变更等待器和回收释放
├── TeamRuntimeLifecycle  — 准入截断和有界结算
├── TeamJournal           — 序列化的 Lead 日志事务
├── TeamRoster            — 身份、供应、拆除
├── TeamMailbox           — 持久队列、分发、确认、恢复
└── TeamTaskBoard         — CAS 命令、DAG 验证、视图
```

所有状态从 **Lead 的 session 日志**通过**严格重放投影**（`src/projection.ts`）派生。`foldTeam()` 函数在每次读取时将事件重放到花名册、任务板和邮箱状态。

### 2.3 权限模型

- **只有 Lead** 可以：生成队友、中断队友、重新分配任务
- **任何成员** 可以：发送消息、创建任务、认领无主就绪任务、编辑/完成/释放自己的任务
- 每个服务方法接受**精确的活跃调用 `Agent`** 作为凭证——过期身份被拒绝

---

## 3. 可靠性机制

### 3.1 持久状态存储

**Lead Session 日志是唯一真相来源。**所有协调状态（花名册、任务、邮箱）存储为 session 事件：

- `team/member` — 队友生命周期快照（每次变更的完整值）
- `team/task` — 完整任务快照，带单调递增修订号
- `team/message/queued` — 持久邮箱入队（在投递尝试之前）
- `team/message/delivered` — 目标已记录消息身份的确认

这些事件是**仅日志的**——它们不会进入对话表面或模型可见历史。

**关键可靠性属性**：每个操作在报告成功或唤醒等待者**之前**追加 + flush 到持久日志。这意味着：

- 崩溃恢复可通过重放日志实现
- 不会因 HMR、子 settlement 或进程中断丢失协调状态

### 3.2 恢复/崩溃韧性（`src/roster.ts`、`src/mailbox.ts`）

**触发条件**：任何 agent 的 `agent/session-start` 事件，或在服务构建时对已活跃的 agent。

**花名册恢复**（`reconcileProvisioning`）：

1. 找到卡在 `provisioning` 阶段的成员
2. 对每个成员，从磁盘读取子节点的独立持久化 session
3. 校验：匹配的 `parentSession`、`continuable` 描述符模式、匹配的 provider、接受的初始提示
4. 全部校验通过 → 标记为 `active`；否则 → 标记为 `failed`
5. 处理竞态：如果恢复标记为 `failed` 但创建同时成功 → 排空子节点并报告 `TEAM_PROVISIONING_CONFLICT`

**邮箱恢复**（`recoverFor`）：

1. 过滤消息：对目标成员的 `queued - delivered`
2. 按原始持久队列顺序重试分发
3. 投递时检查活跃和持久化的目标 inbox/history 以防重复投递

### 3.3 消息投递可靠性（`src/mailbox.ts`）

持久邮箱提供**进程内重试 + 目标 Session 去重**：

- **先入队后投递**：`team/message/queued` 在投递尝试**之前**追加并 flush
- **按目标串行化**：每个目标的投递通过 `dispatchTails` map 串行化——发给同一目标的消息按持久队列顺序投递
- **飞行中追踪**：`inFlightMessages` 集合防止同一消息的重复投递尝试
- **确认**：`team/message/delivered` 仅在目标 session 持久持有消息身份后追加
- **去重**：目标 session 保留 `TeamMessageSource`（kind、teamId、messageId、senderId、senderName）——投递前，`targetRecorded()` 检查消息身份是否已存在于 session 事件中
- **冷恢复**：对不活跃的目标，邮箱读取其持久化日志以检查是否已有该消息，然后再冷恢复它们

**Steer 投递模型**：

| 目标状态 | 投递方式 |
|----------|----------|
| 运行中（running） | 在最近的步骤边界接收 |
| 空闲（idle） | 开始新的 turn |
| 不活跃（inactive） | 从持久化 session 冷恢复 |
| 发送者 | 始终看到 `accepted`（已投递到目标 inbox）或 `queued`（已安全存储但投递暂时不可用） |

**保证**：进程内重试 + 去重，**非**跨进程的 exactly-once。

### 3.4 任务板可靠性（`src/task-board.ts`）

**Compare-and-Set (CAS)**：

- 每个任务变更携带 `expectedRevision`
- 修订号过期 → `TEAM_TASK_STALE_REVISION` 错误（防止丢失更新）
- 每次变更修订号递增 1，由投影校验强制执行

**DAG 验证**（`src/task-graph.ts`）：

- `blockedBy` 边必须指向未删除的任务
- 通过 DFS（visiting/visited 集合）进行完整循环检测
- 自引用、重复和缺失的阻塞者均被拒绝
- 每次创建和更新时在追加前校验

**ID 空间安全**：

- 任务 ID 格式为 `task-<n>`，带安全整数后缀校验
- `nextTaskNumber` 在投影状态中追踪
- ID 耗尽 → `TEAM_TASK_LIMIT` 而非 ID 重用

**授权矩阵**：

| 操作 | 权限 |
|------|------|
| `claim` | 必须 pending + ready（所有阻塞者已完成）+ 无主（或自己持有） |
| `release/complete/edit/set_dependencies` | 持有者 或 Lead |
| `reassign` | 仅限 Lead |
| `delete` | 持有者 或 Lead，仅当无活跃依赖者 |

**写范围（Write Scopes）**：咨询性路径前缀，产生重叠警告但**从不阻止**认领或授权写入。明确的设计决策——不进行虚假的互斥。

### 3.5 事务序列化（`src/journal.ts`）

**`TeamJournal.transact()`**：给定 Lead 的所有变更通过每个 Lead 的 Promise 链（`tails` map）序列化。防止：

- 并发读取看到不一致状态
- 两个任务变更交错导致修订号损坏
- 名称保留中的竞态条件

**`appendAndFlush()`**：将事件追加到 Lead 的 session 并**flush**（等价于 fsync），然后通知等待者。这是原子提交点。

### 3.6 生命周期管理（`src/lifecycle.ts`）

**`TeamRuntimeLifecycle`**：

- 单个 `AbortController` 管理整个团队运行时
- `close()` 以 `TEAM_DISPOSED` 错误中止——不再接受新操作
- `settle()` 等待所有飞行中的创建和分发，带超时
- `withTimeout()` 通过 `disposalTimeoutMs`（默认 5000ms）限制单个结算操作
- 通过遍历错误原因链的 `isCancellation()` 区分期望的回收拒绝和意外失败

**回收协议**（有序）：

1. 关闭准入（`lifecycle.close()`）
2. 释放所有等待者（`activity.close()`）
3. 带超时结算待处理的创建
4. 带超时结算待处理的邮箱分发
5. 通过 `drainContinuableChildren()` 停止所有活跃花名册子节点
6. 聚合所有失败 → 如有则 `AggregateError`

### 3.7 变更通知/等待系统（`src/activity.ts`）

**`TeamActivity`**：

- `waitForChange()`：有界等待（10s–1h）下一个花名册/邮箱/任务/状态变更
- 一次性等待者在调用**开始后**注册——不重放之前的变更
- 调用者必须在唤醒/超时后重新读取权威状态
- 通过以下方式通知：日志提交（`onCommit` 回调）、agent 状态变更
- 回收时释放所有当前等待者
- 取消保留 `Error` 原因或通过 `TEAM_WAIT_ABORTED` 包装

**智能等待快捷方式**（在 `tool-agent-team` 中）：在真正等待之前，`wait_agent` 工具检查是否有任何对等方处于 `running` 或 `provisioning` 状态。如果没有 → 立即返回 `noProgress`，并指导改用 `send_message` 唤醒不活跃的队友。

### 3.8 不变量校验（`src/invariant.ts`）

**运行时不变量的伴侣**在事件进入日志前校验每个候选 Team 事件：

- 挂接到 `internal/dispatch` 的 `session/event`
- 克隆当前投影状态，应用候选事件
- 如果克隆产生 `failure` → 报告不变量违规
- 捕获：无效的阶段转换、名称重用、修订号间隙、重复消息、DAG 违规

### 3.9 投影校验（`src/projection.ts`）

**严格重放**，带全面 Zod schema：

- 每个持久化负载在解码时校验（`parsePersisted`）
- 版本检查（强制 `version: 2`，未来版本显式拒绝）
- 成员转换规则：必须从 `provisioning` 开始，不可变身份字段，禁止名称重用
- 任务规则：修订号必须从 1 开始，严格递增 1，无间隙
- 消息规则：禁止重复入队、禁止无入队的投递、禁止重复投递、目标必须匹配
- 内容块校验：核心类型严格 schema，插件扩展宽松

**状态版本**：`stateVersion: 3` — 支持未来迁移。

### 3.10 错误传播

所有错误为类型化 `TeamError extends HarnessError`，带稳定错误码：

| 错误码 | 含义 |
|--------|------|
| `TEAM_DISPOSED` | 服务正在关闭 |
| `TEAM_NOT_MEMBER` | 调用者不在团队中 |
| `TEAM_LEAD_REQUIRED` | 操作需要 Lead 角色 |
| `TEAM_MEMBER_NOT_FOUND` | 命名成员未活跃 |
| `TEAM_MEMBER_NAME_TAKEN` | 名称已被使用 |
| `TEAM_MEMBER_LIMIT` | 花名册已满 |
| `TEAM_MAILBOX_FULL` | 目标队列达到容量上限 |
| `TEAM_MESSAGE_TOO_LARGE` | 消息超过字节限制 |
| `TEAM_SELF_MESSAGE` | 成员试图给自己发消息 |
| `TEAM_TASK_STALE_REVISION` | CAS 冲突 |
| `TEAM_TASK_LIMIT` | 任务板已满或 ID 耗尽 |
| `TEAM_TASK_BLOCKED` | 任务未就绪 |
| `TEAM_TASK_ALREADY_CLAIMED` | 已被其他成员持有 |
| `TEAM_TASK_UNAUTHORIZED` | 调用者缺少权限 |
| `TEAM_TASK_DELETED` | 任务已标记删除 |
| `TEAM_TASK_HAS_DEPENDENTS` | 无法删除有活跃阻塞者的任务 |
| `TEAM_TASK_DEPENDENCY_CYCLE` | DAG 违规 |
| `TEAM_PROVISIONING_CONFLICT` | 恢复与创建之间的竞态 |
| `TEAM_WAIT_ABORTED` | 等待被取消 |
| `TEAM_DISPOSAL_TIMEOUT` | 关闭超时 |
| `TEAM_INVALID_CONFIG` | 部署限制配置错误 |
| `TEAM_INVALID_ARGUMENT` | 格式错误的输入 |
| `TEAM_INVALID_MEMBER_NAME` | 名称格式错误 |
| `TEAM_INVALID_TIMEOUT` | 等待时长超出范围 |
| `TEAM_INVALID_WRITE_SCOPE` | 路径前缀错误 |

远程 API 将其映射为 `team-task-conflict`（CAS 过期）或 `team-rejected`（其他领域错误），跨浏览器边界保留领域语义。

---

## 可靠性方案小结

| 机制 | 解决的问题 | 目的 |
|------|-----------|------|
| ⭐ **持久状态存储（Session 日志）** | 团队协调状态（花名册、任务、消息）仅存于内存，进程重启全部丢失 | 以 Lead Session 日志作为唯一真相来源，所有协调状态追加即 flush，崩溃后可完整重放恢复 |
| ⭐ **花名册恢复（reconcileProvisioning）** | 队友生成过程中进程崩溃，成员卡在 `provisioning` 中间状态 | 自动检测卡住的成员，从磁盘校验子 session 完整性后决定标记 `active` 或 `failed`，且处理恢复与创建的竞态 |
| **邮箱恢复（recoverFor）** | 进程重启后未投递的消息丢失，队友错过关键通信 | 计算 `queued - delivered` 差值，按原始队列顺序重试投递，配合持久化日志去重 |
| ⭐ **消息投递：先入队后投递** | 消息投递过程中崩溃，消息既未送达也未记录，发送方无感知 | 先持久化 `team/message/queued`，再尝试投递，确保消息不丢失且可恢复 |
| **消息投递：按目标串行化** | 同一目标的多条消息并发投递导致乱序或竞态 | 每个目标维护独立的 Promise 链，确保消息按持久队列顺序投递 |
| **消息投递：去重** | 恢复重试导致同一条消息被投递多次，队友收到重复内容 | 目标 session 保留 `TeamMessageSource` 身份，投递前检查去重；冷恢复时先读持久化日志验证 |
| ⭐ **任务板 CAS（Compare-and-Set）** | 两个成员同时修改同一任务，后提交者覆盖前提交者的更改 | 每次变更携带 `expectedRevision`，修订号不匹配则拒绝，防止丢失更新 |
| **任务板 DAG 验证** | 任务依赖形成循环、自引用或指向已删除任务，导致死锁 | DFS 循环检测 + 边有效性校验，每次创建和更新前强制验证 |
| **ID 空间安全** | 任务 ID 重复使用导致引用错乱 | 安全整数后缀 + 单调递增计数器 + 耗尽时报 `TEAM_TASK_LIMIT` 而非重用 |
| **授权矩阵** | 任意成员可修改他人任务或认领不应属于自己的工作 | 按操作类型分级授权（持有者/Lead/任何成员），严格区分 claim/release/reassign/delete |
| ⭐ **事务序列化（TeamJournal）** | 两个并发变更交错执行导致修订号跳跃或名称重复分配 | 每个 Lead 维护 Promise 链，所有变更串行化通过 `appendAndFlush()` 原子提交 |
| **生命周期管理：有界关闭** | 团队关闭时无限等待飞行中操作，进程无法正常退出 | `AbortController` + `disposalTimeoutMs`（5s）分阶段结算：准入关闭 → 释放等待者 → 结算创建 → 结算分发 → 停止子节点 |
| **变更通知/等待系统** | 队友忙等轮询导致 CPU 空转，或永久阻塞无法检测状态变更 | 事件驱动的有界等待（10s–1h），配合智能快捷方式避免无效等待不活跃的队友 |
| ⭐ **不变量校验（invariant）** | 代码缺陷导致无效事件写入日志，污染唯一真相来源 | 每次事件追加前克隆投影并试应用，违规立即拦截，捕获阶段转换、名称重用、修订间隙等问题 |
| **投影校验（Zod schema）** | 持久化数据格式演化后旧数据无法解析，或被恶意/意外损坏 | 每次解码时完整 schema 校验 + 版本检查，未来版本显式拒绝，核心类型严格约束 |
| **类型化错误传播** | 调用者收到通用 Error，无法区分"暂时不可用"和"永久拒绝" | 25 种稳定错误码，远程 API 映射为 `team-task-conflict`/`team-rejected`，跨边界保留语义 |
| **配置上限（maxMembers/maxTasks/maxPendingMessages/maxMessageBytes）** | 无界增长导致内存耗尽或性能退化 | 每个维度独立上限，启动时校验，防止资源滥用 |

---

## 重点方案详解

> 以下对标注 ⭐ 的基石性机制展开分析，说明其设计原理、执行流程和为什么不可替代。

### ⭐ 1. 持久状态存储（Session 日志）

这是整个 Teams 系统的**唯一真相来源（Single Source of Truth）**。所有协调状态——花名册、任务板、邮箱——不是存在内存里，而是存在 Lead 的 Session 日志中。

**架构全景：**

```
┌──────────────────────────────────────────────────────────────┐
│                    Lead Session Log                           │
│                    (唯一真相来源)                               │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ team/member      │  │ team/task        │  │ team/message │ │
│  │                  │  │                  │  │              │ │
│  │ phase lifecycle  │  │ CAS revisions    │  │ queued       │ │
│  │ identity snapshot│  │ DAG edges        │  │ delivered    │ │
│  │ context mode     │  │ owner/status     │  │ sender info  │ │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘ │
│           │                     │                    │         │
└───────────┼─────────────────────┼────────────────────┼─────────┘
            │                     │                    │
            ▼                     ▼                    ▼
     ┌────────────┐       ┌────────────┐       ┌────────────┐
     │ TeamRoster │       │TeamTaskBoard│      │ TeamMailbox │
     │   花名册    │       │   任务板     │      │    邮箱     │
     └────────────┘       └────────────┘       └────────────┘
            │                     │                    │
            └─────────────────────┼────────────────────┘
                                  │
                        严格的日志重放投影
                        foldTeam(events[]) → TeamState

写路径保证:                    读路径保证:
┌──────────────────┐          ┌──────────────────┐
│ appendAndFlush() │          │ foldTeam()       │
│                  │          │                  │
│ ① 构建事件       │          │ ① 从日志头开始    │
│ ② 追加到 session │          │ ② 逐事件 apply    │
│ ③ flush (fsync) │          │ ③ Zod schema 校验 │
│ ④ 通知等待者     │          │ ④ 返回投影状态    │
│                  │          │                  │
│ 仅在 flush 后    │          │ 每次读取都是      │
│ 才对外可见       │          │ 确定性的重放       │
└──────────────────┘          └──────────────────┘
```

**为什么这是基石：**
- 不是"数据库 + 缓存"双写模式——没有缓存失效问题
- 写路径的 flush-before-notify 保证：任何观察到的状态变更在崩溃后仍可恢复
- 读路径的确定重放意味着：给定相同的事件序列，投影状态完全一致，没有"幻读"

---

### ⭐ 2. 花名册恢复（reconcileProvisioning）

队友生成（spawn）是一个多步骤过程。如果进程在步骤之间崩溃，成员会卡在 `provisioning` 中间状态。

**恢复流程：**

```
进程重启 / agent:session-start 事件触发
                │
                ▼
     ┌─────────────────────────┐
     │ reconcileProvisioning() │
     └────────────┬────────────┘
                  │
    遍历花名册中的所有成员
    找到 phase === 'provisioning' 的成员
                  │
                  ▼
    ┌─────────────────────────────┐
    │  对每个卡住的成员:            │
    │                             │
    │  ① 从磁盘读取子 Session      │
    │     readPersistedSession()  │
    │           │                 │
    │           ▼                 │
    │  ② 校验完整性                │
    │     ├── parentSession 匹配?  │
    │     ├── continuable 模式?    │
    │     ├── provider 匹配?       │
    │     └── initial prompt 匹配? │
    │           │                 │
    │     ┌─────┴─────┐           │
    │     ▼           ▼           │
    │   全部通过    任一失败        │
    │     │           │           │
    │     ▼           ▼           │
    │  → active   → failed        │
    │                             │
    │  ③ 竞态处理                  │
    │     如果恢复标记为 failed     │
    │     但创建同时成功:           │
    │     → 排空子节点             │
    │     → TEAM_PROVISIONING     │
    │       _CONFLICT             │
    └─────────────────────────────┘

名称永不重用:
┌────────────────────────────────────────────────────┐
│  name: "code-reviewer"                             │
│                                                    │
│  第一次 provisioning → 保留此名称                    │
│  即使该成员最终 failed，名称也不会被回收              │
│  新成员必须使用新名称                                │
│                                                    │
│  原因: 如果名称被重用，持久化日志中的旧事件           │
│  会与新成员混淆，恢复逻辑无法区分                     │
└────────────────────────────────────────────────────┘
```

**为什么这是基石：**
- 没有恢复，spawn 过程中的任何崩溃都会导致花名册中永久存在"幽灵成员"
- 竞态处理保证了恢复和创建并发时的正确性——这在 HMR（热模块替换）场景下经常发生
- 名称不重用策略消除了"同名不同人"的歧义问题

---

### ⭐ 3. 消息投递：先入队后投递

这是消息不丢失的核心保证。持久入队先于投递尝试——发送方不需要信任投递会成功。

**投递时序：**

```
发送方调用 send_message()
        │
        ▼
  ┌──────────────────────────┐
  │ ① appendAndFlush         │
  │   team/message/queued    │  ← 持久化入队
  │   {                      │     (此时消息已安全存储)
  │     messageId,           │
  │     targetId,            │
  │     content              │
  │   }                      │
  └──────────┬───────────────┘
             │ flush 完成
             ▼
  ┌──────────────────────────┐
  │ ② 投递尝试                │
  │                          │
  │  目标状态?                │
  │  ┌─────────────────┐     │
  │  │ running → Steer  │     │  ← 最近步骤边界接收
  │  │ idle    → 新 turn │     │  ← 开始新 turn
  │  │ inactive→ 冷恢复  │     │  ← 从持久化 session 恢复
  │  └─────────────────┘     │
  └──────────┬───────────────┘
             │
      ┌──────┴──────┐
      ▼              ▼
   投递成功       投递失败
      │              │
      ▼              ▼
  ┌──────────┐  留在队列中
  │③ append  │  下次恢复时
  │ delivered│  重试
  └──────────┘

发送方看到的返回值:
┌──────────────────────────────────────────────┐
│ accepted: 消息已进入目标 inbox                 │
│ queued:   消息已安全存储但目标暂时不可用         │
│                                              │
│ 永远不会看到: "投递失败"或"未知状态"            │
└──────────────────────────────────────────────┘
```

**去重机制：**

```
投递前检查 targetRecorded():
        │
        ▼
  目标 Session 是否有 TeamMessageSource{
    kind:      'team-message',
    teamId:    'xxx',
    messageId: 'yyy',
    senderId:  'zzz',
    senderName:'alice'
  }?
        │
   ┌────┴────┐
   ▼         ▼
  存在      不存在
  → 跳过    → 投递
  (已收到过)
```

**为什么这是基石：**
- 消息在投递尝试之前就已持久化——即使投递过程中崩溃，消息不会丢失
- 去重保证恢复重试不会产生重复消息——目标 Session 的 `TeamMessageSource` 是幂等键
- 目标不可用时的 `queued` 语义明确：发送方知道消息安全但还在路上

---

### ⭐ 4. 任务板 CAS（Compare-and-Set）

在多人协作场景中，两个 Agent 可能同时修改同一个任务。CAS 是防止丢失更新的唯一手段。

**丢失更新场景 vs CAS 保护：**

```
没有 CAS ❌                          有 CAS ✅

Agent A          Agent B            Agent A          Agent B
  │                │                  │                │
  ├─ 读 Task#3 ──┐ │                  ├─ 读 Task#3 ──┐ │
  │  rev=5       │ │                  │  rev=5       │ │
  │              ▼ │                  │              ▼ │
  │  status→done  │ 读 Task#3         │  status→done  │ 读 Task#3
  │              │ rev=5             │              │ rev=5
  │              │ │                 │              │ │
  │              │ ▼                 │              │ ▼
  ├─ 写 Task#3 ──┤ status→cancelled  ├─ 写 Task#3 ──┤ status→cancelled
  │  rev=5       │      │            │  expected=5  │      │
  │  ✅ 成功      │      │            │  ✅ 成功      │      │
  │              │      ▼            │  rev→6       │      ▼
  │              ├─ 写 Task#3        │              ├─ 写 Task#3
  │              │  rev=5            │              │  expected=5
  │  结果:        │  ✅ 成功          │              │  ❌ STALE_REVISION
  │  A 的修改     │                  │  结果:        │  (当前 rev=6)
  │  被 B 覆盖!   │                  │  A 的修改被保护 │
```

**CAS 在投影校验中的执行：**

```
  写请求: { taskId: "task-3", expectedRevision: 5, ... }
        │
        ▼
  ┌──────────────────────────┐
  │ foldTeam() → 当前投影状态  │
  │                          │
  │ task-3.revision = 6      │  ← 已经被 A 更新过了
  │ expectedRevision = 5     │  ← 不匹配！
  └──────────┬───────────────┘
             │
             ▼
  ┌──────────────────────────┐
  │ TEAM_TASK_STALE_REVISION │
  │                          │
  │ 调用者必须:               │
  │ ① 重新读取最新状态         │
  │ ② 基于 revision=6 重试    │
  └──────────────────────────┘
```

**为什么这是基石：**
- Teams 是多人协作系统——没有 CAS，后提交者总覆盖先提交者
- 修订号由投影强制执行单调递增——不能跳过，不能回退
- 拒绝而非静默覆盖保证了数据完整性

---

### ⭐ 5. 事务序列化（TeamJournal）

给定 Leader 的所有变更通过 Promise 链串行化。这不是全局锁——每个 Leader 独立串行。

**并发控制模型：**

```
          Lead A                          Lead B
     (独立的 tails Map 条目)         (独立的 tails Map 条目)
            │                               │
     ┌──────┴──────┐                 ┌──────┴──────┐
     │  tails[A]   │                 │  tails[B]   │
     │  Promise链  │                 │  Promise链  │
     └──────┬──────┘                 └──────┬──────┘
            │                               │
    ┌───────┼───────┐               ┌───────┼───────┐
    ▼       ▼       ▼               ▼       ▼       ▼
  op₁  →  op₂  →  op₃            op₁  →  op₂  →  op₃
  (串行) (串行) (串行)            (串行) (串行) (串行)

  Lead A 和 Lead B 之间并行
  同一 Lead 内部串行
```

**appendAndFlush 原子提交：**

```
  transact(leadSessionId, async () => {
        │
        ▼
  ① 等待 tails[id] 的前一个操作完成
        │
        ▼
  ② 执行业务逻辑
     - 构建 team/member 或 team/task 事件
     - 校验不变量 (invariant)
        │
        ▼
  ③ appendAndFlush(event)
     - 追加到 Lead Session 日志
     - fsync 到磁盘
        │ flush 成功
        ▼
  ④ 通知等待者 (onCommit callbacks)
        │
        ▼
  ⑤ 返回结果
  })
```

**防止的问题：**

| 场景 | 没有事务序列化 | 有事务序列化 |
|------|---------------|-------------|
| 两个 spawn 同时执行 | 同一个名称可能被分配两次 | 第二个必须等第一个完成，名称冲突立即可见 |
| 两个 task update 并发 | 修订号可能从 5 跳到 7（6 被跳过） | 严格递增 1 |
| 并发读写 | 读取可能看到半写状态 | 读只发生在提交点之间 |

**为什么这是基石：**
- 没有事务序列化，投影中的单调递增约束无法保证
- Promise 链比互斥锁更轻量——利用 JS 的事件循环自然顺序
- 每个 Lead 独立串行：不同团队之间零争用

---

### ⭐ 6. 不变量校验（invariant）

这是 Teams 系统的**最后一道防线**。在事件写入日志之前，不变量伴侣拦截无效事件。

**校验管道：**

```
  事件进入系统
       │
       ▼
  session/event dispatch
       │
       ▼
  ┌────────────────────────────────────────┐
  │         invariant companion            │
  │                                        │
  │  ① 克隆当前投影状态                      │
  │     clonedState = structuredClone(     │
  │       currentProjection               │
  │     )                                  │
  │           │                            │
  │           ▼                            │
  │  ② 试应用候选事件                        │
  │     result = clonedState.apply(        │
  │       candidateEvent                  │
  │     )                                  │
  │           │                            │
  │     ┌─────┴─────┐                      │
  │     ▼           ▼                      │
  │  success     failure                   │
  │     │           │                      │
  │     ▼           ▼                      │
  │  ③ 放行     ④ 拦截并报告违规             │
  │  写入日志     事件永不进入日志             │
  └────────────────────────────────────────┘

捕获的违规类型:
┌────────────────────────────────────────────────┐
│ • 无效阶段转换 (active → provisioning)          │
│ • 名称重用 (已被 failed 记录占用的名称)          │
│ • 修订号间隙 (revision: 3 → 5, 缺少 4)          │
│ • 重复消息入队 (相同 messageId 两次 queued)      │
│ • 无入队的投递 (delivered 但没有 queued)         │
│ • DAG 违规 (循环依赖)                            │
│ • 身份字段不可变违规 (修改已设置 name/teamId)     │
└────────────────────────────────────────────────┘
```

**为什么是最后一道防线：**
- 位于数据写入之前——被拦截的事件从不污染日志
- 克隆试验而非原地修改——即使校验本身有问题也不会影响当前状态
- 捕获的是代码缺陷而非用户错误——每次触发都意味着有 bug 需要修复

---

## 4. 配置选项

所有在 `Config` 接口（`types.ts`）中，启动时校验：

| 字段 | 默认值 | 可靠性作用 |
|------|--------|-----------|
| `maxMembers` | `8` | 花名册大小上限（含失败成员）；防止无界资源消耗 |
| `maxTasks` | `256` | 活跃任务上限；防止无界任务板增长 |
| `maxPendingMessagesPerMember` | `64` | 每个目标的邮箱容量；防止失控消息队列 |
| `maxMessageBytes` | `65,536` | 单条消息大小限制；防止内存耗尽 |
| `disposalTimeoutMs` | `5,000` | 关闭超时；限制清理时间防止挂起 |

---

## 5. 设计决策边界

### 提供的能力

- ✅ 持久日志作为唯一真相来源
- ✅ 进程内重试 + 去重（消息）
- ✅ Compare-and-set（任务，防止丢失更新）
- ✅ 崩溃恢复（日志重放）
- ✅ 有界回收（带超时）
- ✅ 不变量强制执行（每次事件追加）
- ✅ 严格 schema 校验（重放时）
- ✅ 类型化错误（稳定错误码）
- ✅ 序列化事务（每个 Lead）

### 明确不提供的能力（有意的设计边界）

- ❌ **跨进程协调** — "一个 Team 上的并发 harness 进程不受支持"
- ❌ **Worktree 隔离** — "Team 域不推断分支、合并变更或静默更改 cwd"
- ❌ **文件系统锁** — "writeScopes 是产生重叠诊断的规范化路径前缀，但从不阻止认领或授权写入"
- ❌ **自动所有权释放** — "idle、中断、进程退出和失败的工作不会释放任务持有者"
- ❌ **Exactly-once 投递** — "进程内重试 + target-Session 去重，非跨进程 exactly-once"
- ❌ **嵌套团队** — "扁平不可变花名册；只有 Lead 创建直接队友"
- ❌ **名称重用** — "名称由第一个 provisioning 记录保留且永不重用"
- ❌ **共识/领导者选举** — 单一 Lead（按身份），无选举协议