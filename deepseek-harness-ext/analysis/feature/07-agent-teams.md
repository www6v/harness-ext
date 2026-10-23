# Agent Teams 分析

## 结论

**⚠️ 实验性支持** — deepseek-harness 拥有完整的 Agent Teams 功能，但标记为**实验性 (experimental)**，无稳定性保证。Agent Teams 将一个 coding session 变成一个小型工作团队：Lead agent 创建命名的 teammates，通过持久化消息相互通信，共享任务板协调工作。消息和任务状态在崩溃、重载和中断后依然保留。

## 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-experimental-agent-team` | `packages/experimental/agent-team/` | **核心服务** — TeamService, Roster, Mailbox, TaskBoard |
| `@deepseek-ai/dsh-experimental-tool-agent-team` | `packages/experimental/tool-agent-team/` | **模型工具** — 9 个 scoped 工具 (spawn_teammate, send_message, etc.) |
| `@deepseek-ai/dsh-experimental-client-ui-agent-team` | `packages/experimental/client-ui-agent-team/` | **浏览器 UI** — Team roster 和 task board 展示 |
| `@deepseek-ai/dsh-experimental-agent-team-profile` | `packages/experimental/agent-team-profile/` | **Host profile** — 启用 Team 的 cordis patch |
| `@deepseek-ai/dsh-experimental-agent-team-web-profile` | `packages/experimental/agent-team-web-profile/` | **Web profile** — 浏览器端 Team UI 层 |

## 架构设计

### 整体架构

```
Team Lead Session (隐式 Team root, TeamId = SessionId)
  │
  ├── TeamService (ctx.agentTeams)
  │   ├── TeamRoster — 身份管理, teammate 创建, 恢复
  │   ├── TeamMailbox — 持久化消息队列, 分发, 确认
  │   ├── TeamTaskBoard — DAG 任务管理, CAS 操作
  │   ├── TeamJournal — Lead Session log 事务
  │   ├── TeamProjection — 从事件流重放状态
  │   ├── TeamActivity — 变更等待器
  │   └── TeamLifecycle — 共享准入控制和清理
  │
  ├── Teammate A (continuable subagent)
  ├── Teammate B (continuable subagent)
  └── Teammate C (continuable subagent)
```

### 设计哲学

1. **Durable log, derived state** — Lead Session log 是唯一真相源；roster、mailbox、task 状态都是从中重放的
2. **Process-local ownership** — 所有协调在同一进程内；保证是 retry + de-duplication，不是跨进程共识
3. **Explicit authority** — 每个方法都需要精确的 live calling Agent；只有 Lead 可以 spawn/reassign/interrupt
4. **Bounds that fail loud** — 每个限制都是验证过的部署值，耗尽时报告类型化错误而非重用 id/name

## TeamService — 核心服务

```typescript
class TeamService extends TypertRemoteService {
  static inject = ['agents', 'sessions', 'sessionPersistence', 'sessionProjections', 'subagents']
  
  // ═══════════════════════════════════════
  // Roster 操作
  // ═══════════════════════════════════════
  
  // 解析 Agent 的 Team 角色
  membership(agent: Agent): TeamMembership
  
  // 列出 roster
  listMembers(agent: Agent): TeamMemberView[]
  
  // 创建 teammate (Lead only)
  async spawnTeammate(caller: Agent, request: SpawnTeammateRequest): Promise<SpawnTeammateResult>
  
  // 中断 teammate (Lead only)
  interrupt(caller: Agent, targetName: string): { previousStatus }
  
  // ═══════════════════════════════════════
  // Mailbox 操作
  // ═══════════════════════════════════════
  
  // 发送持久化消息
  async sendMessage(caller: Agent, request: SendTeamMessageRequest): Promise<SendTeamMessageResult>
  
  // ═══════════════════════════════════════
  // Task Board 操作
  // ═══════════════════════════════════════
  
  async createTask(caller: Agent, request: CreateTeamTaskRequest): Promise<TeamTaskView>
  getTask(caller: Agent, id: TeamTaskId): TeamTaskView
  listTasks(caller: Agent): TeamTaskView[]
  async updateTask(caller: Agent, request: UpdateTeamTaskRequest): Promise<TeamTaskView>
  
  // ═══════════════════════════════════════
  // 等待与活动
  // ═══════════════════════════════════════
  
  async waitForChange(caller: Agent, timeoutMs: number, signal: AbortSignal): Promise<TeamWaitResult>
  
  // ═══════════════════════════════════════
  // Remote API (Typert RPC)
  // ═══════════════════════════════════════
  
  @Remote('view') remoteView(agent: Agent): TeamView
  @Remote('createTask') remoteCreateTask(agent, request): Promise<TeamTaskMutationResult>
  @Remote('updateTask') remoteUpdateTask(agent, request): Promise<TeamTaskMutationResult>
}
```

## 核心概念

### Team Identity — 隐式 Team

每个普通 runtime root 是一个隐式 Team 的 Lead，`TeamId` 等于其 `SessionId`。没有创建事件，持久化状态从第一个 member/message/task 记录开始。

### Teammate — 命名成员

```typescript
interface SpawnTeammateRequest {
  readonly name: string           // 唯一的小写 kebab-case 名称
  readonly description: string    // 职责描述
  readonly prompt: ContentBlock[] // 初始任务
  readonly context: 'fresh' | 'fork'  // fresh: 无 Lead 历史; fork: 继承完成的 turns
  readonly provider: string       // subagent provider
  readonly signal: AbortSignal
}
```

**Teammate 生命周期**:

```typescript
type TeamMemberPhase = 'provisioning' | 'active' | 'failed'
type TeamMemberStatus = 'running' | 'idle' | 'inactive' | 'provisioning' | 'failed'
```

- 名字是**永久的** — 即使创建失败也保留名字，永不重用
- Lead 是唯一可以创建 teammate 的角色
- Teammate 是 **continuable subagent** — 持久化、可恢复

### Roster — 花名册

```typescript
interface TeamMemberView {
  readonly id: SessionId
  readonly name: string
  readonly role: 'lead' | 'teammate'
  readonly status: 'running' | 'idle' | 'inactive' | 'provisioning' | 'failed'
  readonly description?: string
  readonly provider?: string
  readonly context?: 'fresh' | 'fork'
  readonly model?: string
  readonly diagnostics: string[]
}
```

### Mailbox — 持久化消息

```typescript
interface SendTeamMessageRequest {
  readonly target: string          // 目标名字 (或 "lead")
  readonly content: ContentBlock[]
  readonly signal: AbortSignal
}

interface SendTeamMessageResult {
  readonly messageId: TeamMessageId
  readonly status: 'accepted' | 'queued'
}
```

**消息保证**:
- 消息**永不丢失**，**永不重复投递**
- 离线成员的消息排队，恢复后接收
- 发送成功 = 安全存储 (即使状态是 `queued` 也不要重发)
- 投递使用 **Steer**: running → 下一步边界接收; idle → 开始 turn; inactive → 冷恢复
- 保证是 process-local retry + target-Session de-duplication，非跨进程 exactly-once

### Task Board — 共享任务板

```typescript
interface TeamTaskSnapshot {
  readonly id: TeamTaskId           // "task-<n>" 格式
  readonly revision: number         // CAS 版本号
  readonly subject: string
  readonly description: string
  readonly status: 'pending' | 'in_progress' | 'completed' | 'deleted'
  readonly ownerId?: SessionId
  readonly blockedBy: TeamTaskId[]  // DAG 依赖
  readonly writeScopes: string[]    // 建议写入范围
}
```

**任务操作 (CAS — Compare-and-Set)**:

| 操作 | 权限 | 说明 |
|------|------|------|
| `claim` | 任何成员 | 认领 ready 的任务 |
| `release` | owner/Lead | 释放任务回 pending |
| `edit` | owner/Lead | 修改 subject/description/writeScopes |
| `set_dependencies` | owner/Lead | 设置依赖关系 |
| `complete` | owner/Lead | 标记完成 |
| `reopen` | owner/Lead | 重新打开已完成任务 |
| `reassign` | **Lead only** | 重新分配给其他成员 |
| `delete` | owner/Lead | 删除 (保留墓碑) |

**关键特性**:
- 每次修改携带 `expectedRevision` — 过期版本被拒绝 (`TEAM_TASK_STALE_REVISION`)
- DAG 验证 — 防止循环依赖
- Write scope 重叠产生**警告**但**不阻止**
- 删除的任务保留在历史中但不占用 `maxTasks` 配额

### Wait & Activity — 等待变更

```typescript
interface TeamWaitResult {
  readonly timedOut: boolean
}

// 等待 roster/task/mailbox/status 变更
// 超时范围: 10,000ms ~ 3,600,000ms
async waitForChange(caller: Agent, timeoutMs: number, signal: AbortSignal): Promise<TeamWaitResult>
```

- 不会唤醒 inactive 成员
- 如果没有 active peer，立即返回 `noProgress`
- 超时后需重新读取状态

## 模型工具 (9 个)

`@deepseek-ai/dsh-experimental-tool-agent-team` 为每个 Team 成员安装 9 个 scoped 工具：

### 创建与消息

| 工具 | 权限 | 说明 |
|------|------|------|
| `spawn_teammate` | **Lead only** | 创建命名 teammate |
| `send_message` | 所有成员 | 发送持久化消息 |
| `interrupt_agent` | **Lead only** | 中断 teammate 当前 turn |

### 查看与等待

| 工具 | 权限 | 说明 |
|------|------|------|
| `list_agents` | 所有成员 | 列出 roster 与状态 |
| `wait_agent` | 所有成员 | 等待下次团队变更 |

### 任务板

| 工具 | 权限 | 说明 |
|------|------|------|
| `team_task_create` | 所有成员 | 创建任务 |
| `team_task_list` | 所有成员 | 列出任务 (支持过滤/分页) |
| `team_task_get` | 所有成员 | 读取单个任务 |
| `team_task_update` | 所有成员 (CAS) | 更新任务 (claim/complete/etc.) |

### 系统策略注入

每个 Team 成员收到一个 `team:policy` 系统提示段，包含：
- 共享 cwd 和文件系统行为
- FS_STALE_VERSION 恢复指导
- Bash/formatter/codegen 风险提示
- 任务协调和 write scope 规则
- 消息投递 (Steer) 行为
- Lead 必须在最终答案前等待所需 teammate

## 配置

```typescript
interface Config {
  maxMembers: 8                    // 最大 teammate 数量 (含失败)
  maxTasks: 256                    // 最大活跃任务数
  maxPendingMessagesPerMember: 64  // 每成员最大排队消息
  maxMessageBytes: 65_536          // 单条消息最大字节
  disposalTimeoutMs: 5_000         // 关闭清理超时
}
```

## 部署最小配置

```yaml
# 最小 Team 设置
- name: '@deepseek-ai/dsh-session-persistence-jsonl'  # 持久化存储 (必须)
- name: '@deepseek-ai/dsh-experimental-agent-team'     # Team 核心服务
- name: '@deepseek-ai/dsh-experimental-tool-agent-team' # 模型工具
```

或使用 profile:

```sh
# Headless profile
dsh plugin --profile headless add @deepseek-ai/dsh-experimental-agent-team-profile

# Web profile (需要 Team host + web 层)
dsh plugin --profile web add @deepseek-ai/dsh-experimental-agent-team-profile
dsh plugin --profile web add @deepseek-ai/dsh-experimental-agent-team-web-profile
```

## 事件类型 (持久化)

```typescript
interface SessionEventMap {
  // Teammate 生命周期
  'team/member': { version: 2; teamId: TeamId; member: TeamMemberSnapshot }
  
  // 共享任务
  'team/task': { version: 2; teamId: TeamId; task: TeamTaskSnapshot }
  
  // 消息入队 (投递前)
  'team/message/queued': { version: 2; teamId: TeamId; message: TeamMessageSnapshot }
  
  // 消息投递确认
  'team/message/delivered': { version: 2; teamId: TeamId; messageId: TeamMessageId; targetId: SessionId }
}
```

这些事件是 **log-only** — 不进入对话表面，不影响模型历史。

## 错误码

| 错误码 | 含义 |
|--------|------|
| `TEAM_NOT_MEMBER` | Agent 不是 Team 成员 |
| `TEAM_LEAD_REQUIRED` | 操作需要 Lead 权限 |
| `TEAM_MEMBER_NAME_TAKEN` | teammate 名字已被占用 |
| `TEAM_MEMBER_LIMIT` | 达到成员上限 |
| `TEAM_MEMBER_NOT_FOUND` | 未找到活跃 teammate |
| `TEAM_INVALID_TARGET` | 无效目标 (如 Lead 中断自己) |
| `TEAM_TASK_LIMIT` | 任务数量上限 |
| `TEAM_TASK_NOT_FOUND` | 任务不存在 |
| `TEAM_TASK_STALE_REVISION` | CAS 版本过期 |
| `TEAM_TASK_BLOCKED` | 任务被依赖阻塞 |
| `TEAM_TASK_ALREADY_CLAIMED` | 任务被他人认领 |
| `TEAM_TASK_UNAUTHORIZED` | 无权限修改任务 |
| `TEAM_TASK_INVALID_TRANSITION` | 无效状态转换 |
| `TEAM_TASK_DEPENDENCY_CYCLE` | 依赖图有环 |
| `TEAM_TASK_HAS_DEPENDENTS` | 任务仍被其他任务依赖 |
| `TEAM_TASK_DELETED` | 任务已删除 |
| `TEAM_PROVISIONING_CONFLICT` | 创建过程中状态冲突 |
| `TEAM_WAIT_ABORTED` | 等待被取消 |
| `TEAM_DISPOSED` | 服务正在关闭 |
| `TEAM_INVALID_CONFIG` | 配置值无效 |
| `TEAM_INVALID_MEMBER_NAME` | teammate 名字格式无效 |

## 已知限制

| 限制 | 说明 |
|------|------|
| **实验性** | 无稳定性保证，合约可能自由变更 |
| **单进程单 checkout** | 成员共享 cwd，无 worktree、远程成员、合并或文件锁 |
| **建议性 write scope** | Bash/formatter/codegen 可绕过版本检查 |
| **扁平不可变 roster** | 无嵌套 Team、重命名、删除或名字重用 |
| **无自动所有权释放** | idle/中断/进程退出/失败工作不释放任务所有者 |
| **非跨进程 exactly-once** | 不支持并发 harness 进程操作同一 Team |
| **无自主 Team 创建** | 普通任务不触发委派，需用户明确要求 |

## 与 Claude Code 的对比

| 特性 | Claude Code | deepseek-harness Agent Teams |
|------|-------------|------------------------------|
| 多 agent 协作 | ✅ (teammates via SendMessage) | ✅ (Agent Teams) |
| 持久化消息 | 部分 | ✅ (durable mailbox) |
| 共享任务板 | ❌ | ✅ (CAS task board with DAG) |
| Roster 展示 | 部分 | ✅ (TeamMemberView) |
| 崩溃恢复 | 部分 | ✅ (log replay) |
| Write scope 协调 | ❌ | ✅ (advisory) |
| 依赖管理 | ❌ | ✅ (blockedBy DAG) |
| Web UI | ❌ | ✅ (experimental) |
| 稳定性 | ✅ (稳定) | ⚠️ (实验性) |
| 嵌套团队 | ❌ | ❌ (未实现) |
| 远程成员 | ❌ | ❌ (未实现) |
| Worktree 隔离 | ❌ | ❌ (未实现) |

## 关键代码位置

| 文件 | 说明 |
|------|------|
| `packages/experimental/agent-team/src/index.ts` | TeamService 核心 — facade, 配置, 恢复调度 |
| `packages/experimental/agent-team/src/types.ts` | 公共类型 — TeamId, TeamTaskId, TeamMessageId, Config |
| `packages/experimental/agent-team/src/roster.ts` | TeamRoster — 身份管理, spawn, recover, interrupt |
| `packages/experimental/agent-team/src/mailbox.ts` | TeamMailbox — 持久化队列, 分发, 确认, 恢复 |
| `packages/experimental/agent-team/src/task-board.ts` | TeamTaskBoard — CAS 命令, DAG 验证, 派生视图 |
| `packages/experimental/agent-team/src/task-graph.ts` | TeamTaskGraph — DAG 循环检测 |
| `packages/experimental/agent-team/src/journal.ts` | TeamJournal — Lead-log 事务, commit 通知 |
| `packages/experimental/agent-team/src/projection.ts` | TeamProjection — 严格事件重放 |
| `packages/experimental/agent-team/src/activity.ts` | TeamActivity — 一次性变更等待器 |
| `packages/experimental/agent-team/src/lifecycle.ts` | TeamLifecycle — 共享准入控制, 有界清理 |
| `packages/experimental/agent-team/src/error.ts` | TeamError — 类型化错误 |
| `packages/experimental/tool-agent-team/src/index.ts` | 9 个模型工具注册 |
| `packages/experimental/client-ui-agent-team/src/client/` | 浏览器 UI 挂载 |
