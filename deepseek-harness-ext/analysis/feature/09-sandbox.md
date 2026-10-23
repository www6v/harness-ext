# Sandbox 系统分析

## 结论

deepseek-harness 的 sandbox 系统是一个**多层、平台自适应、per-call policy 驱动的进程文件访问隔离框架**。它通过抽象 `SandboxProvider` 服务接口、本地平台后端链、Per-Call Policy 服务、升级 (Escalation) 机制以及多个消费者集成，实现了对子进程文件写入的精确控制。

| 能力 | 支持状态 | 实现方式 |
|------|----------|----------|
| 进程文件沙箱 | **✅ 完整** | SandboxProvider + 本地后端链 |
| 多平台后端 (bwrap/Landlock/Seatbelt/Windows ACL) | **✅ 完整** | sandbox-local 自动选择 |
| Per-Call Policy (每次调用策略) | **✅ 完整** | SandboxPolicyService.resolve() |
| 沙箱模式升级 (Escalation) | **✅ 完整** | approveEscalation + 用户批准 |
| 文件系统工具沙箱 (fs-sandbox) | **✅ 完整** | In-process 文件写入围栏 |
| Shell 命令沙箱 (bash-sandbox) | **✅ 完整** | Subprocess 包裹执行 |
| 持久化终端沙箱 | **✅ 支持** | terminal-bash 集成 |
| 动态代码沙箱 (Cordis Host Runner) | **⚠️ 不同机制** | `node:vm` 沙箱 + Context Facade |
| 远程沙箱 (E2B) | **✅ 支持** | 替代整个 capability seam |
| 网络/进程隔离 | **❌ 不支持** | 仅文件效果策略 |

---

## 一、系统架构概览

Sandbox 系统由 4 个子包和 4 个主要消费者组成：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Sandbox 系统架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  sandbox (抽象层)                                                │
│  ├── SandboxProvider (抽象服务)                                  │
│  ├── SandboxMode (read-only | workspace-write | danger-full-access)│
│  ├── SandboxPolicy (per-call 策略)                               │
│  ├── ConfinedArgv (包裹后的 argv)                                │
│  └── Escalation (升级词汇与编排)                                 │
│                                                                 │
│  sandbox-local (本地后端)                                        │
│  ├── Linux: bwrap → Landlock (链式选择)                          │
│  ├── macOS: Seatbelt (sandbox-exec)                             │
│  ├── Windows: ACL Restricted Token                               │
│  └── 功能性探测 + 缓存裁决                                       │
│                                                                 │
│  sandbox-policy (策略服务)                                       │
│  ├── 部署默认模式                                                │
│  ├── Session 级 override (sandbox/mode event)                   │
│  ├── workspace-write 根路径解析                                  │
│  └── 系统 prompt 注入                                            │
│                                                                 │
│  sandbox-windows-acl (Windows 后端)                              │
│  ├── WRITE_RESTRICTED Token                                     │
│  ├── Workspace/Temp SID + DACL                                   │
│  └── 跨 Session 复用的 ACE                                      │
│                                                                 │
│  消费者:                                                        │
│  ├── bash-sandbox: ctx.shell → 包裹 bash -c                     │
│  ├── pwsh-sandbox: ctx.shell → 包裹 pwsh -Command              │
│  ├── fs-sandbox: ctx.fs → In-process 路径围栏                   │
│  ├── terminal-bash: 持久化终端 → 模式变更防护                    │
│  └── cordis-host-runner: 动态代码 → node:vm 沙箱                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、Sandbox 模式 (SandboxMode)

Sandbox 的文件效果策略定义了三种递减限制的模式：

```typescript
type SandboxMode = 'read-only' | 'workspace-write' | 'danger-full-access'

// 只有前两种需要 confinement，danger-full-access 直接跳过
type ConfinedSandboxMode = 'read-only' | 'workspace-write'
```

### 模式详解

| 模式 | 文件写入 | 文件读取 | 适用场景 |
|------|----------|----------|----------|
| `read-only` | 仅允许必须的 sink（如 `/dev/null`） | 允许 | 代码审查、分析任务 |
| `workspace-write` | 允许工作目录 + 临时目录写入 | 允许 | 正常编码任务（默认） |
| `danger-full-access` | 完全允许 | 允许 | 需要无限制访问的任务 |

### 执行完备性 (SandboxEnforcement)

```typescript
type SandboxEnforcement = 'full' | 'partial'
```

- `full`: 后端完全控制所有承诺的文件效果 (bwrap, Seatbelt, 完整 Landlock ABI)
- `partial`: 活跃后端或旧内核 ABI 只能控制部分效果 (旧版 Landlock ABI, Windows ACL)

---

## 三、核心抽象层 (`@deepseek-ai/dsh-sandbox`)

### 3.1 SandboxProvider — 抽象服务

```typescript
abstract class SandboxProvider extends Service {
  constructor(ctx: Context) { super(ctx, 'sandbox') }

  // 将 argv 包裹为受限执行
  abstract confine(argv: readonly string[], policy: SandboxPolicy): ConfinedArgv
}
```

`confine()` 接收原始 argv 和 per-call policy，返回包裹后的 argv。**Fail-closed**: 如果无法执行，抛出 `SandboxUnavailableError`（错误码 `SANDBOX_UNAVAILABLE`），绝不无声绕过。

### 3.2 Per-Call Policy

Policy 是**每次调用携带的完整策略**，而非固定在 Provider 上：

```typescript
interface SandboxExecutionPolicy {
  mode: SandboxMode                    // 文件效果模式
  workspaceRoot: string                // workspace-write 的根目录（绝对路径）
  sessionId?: SessionId                // 调用 Session 的标识（用于 per-session 状态）
}

interface SandboxPolicy extends SandboxExecutionPolicy {
  mode: ConfinedSandboxMode            // 仅限 confinement 模式
}
```

设计原则：两个消费者可以同时以不同 policy 运行（bash 以 `read-only`，子 agent 以 `workspace-write`）；升级后的重试是新调用，携带更宽松的 policy。

### 3.3 可写根路径 (Writable Roots)

`workspace-write` 的可写区域统一由 `writableRoots()` 派生：

```typescript
function writableRoots(policy: SandboxExecutionPolicy): string[] {
  // workspace-write: 返回 [workspaceRoot, '/tmp', tmpdir()]
  // read-only / danger-full-access: 返回 []
}
```

这是 Seatbelt profile 和 in-process fs fence 共同的许可列表来源，确保两者不会产生不对称。

### 3.4 ConfinedArgv — 包裹结果

Provider 不只是返回 argv，还携带分类信息：

```typescript
interface ConfinedArgv {
  argv: string[]                          // 包裹后的 argv
  enforcement: SandboxEnforcement         // 执行完备性
  denialSignatures: readonly string[]     // 该后端的拒绝标记（stderr 子串）
  runnerFailureRules: readonly RunnerFailureRule[]  // Runner 失败证据规则
}
```

`denialSignatures` 是各后端的拒绝"方言"：
- bwrap: `['read-only file system']`
- Landlock: `['permission denied']`
- Seatbelt: `['operation not permitted']`
- Windows ACL: `['access is denied', 'access to the path', 'permission denied']`

### 3.5 升级机制 (Escalation)

#### 严格扩展阶梯

```typescript
WIDER_MODES = {
  'read-only': ['workspace-write', 'danger-full-access'],
  'workspace-write': ['danger-full-access'],
}
```

`ESCALATION_TARGETS: ['workspace-write', 'danger-full-access']` — 这是所有可能升级到的目标。

#### 升级编排

```typescript
async function approveEscalation(request, approval): Promise<SandboxMode>
```

流程：
1. 验证 `sandbox_permissions` 和 `justification` 参数配对
2. 检查请求的模式是否严格宽于当前有效模式（拒绝非扩展请求，不提示用户）
3. 通过 `ctx.approval` 请求用户批准
4. 批准 → 返回新模式；拒绝/取消/不可用 → 抛出对应错误

#### 拒绝标记和升级提示

```typescript
sandboxDenialMarker(mode)   // → "[sandbox: file access denied under <mode> mode]"
escalationHintMarker(subject) // → "[sandbox: escalation available — retry this exact <subject>...]"
```

这些是模型看到的共享词汇，bash 和 fs 两个系列使用相同的文本。

---

## 四、本地后端 (`@deepseek-ai/dsh-sandbox-local`)

### 4.1 平台链选择

```typescript
PLATFORM_CHAINS = {
  linux: ['bwrap', 'landlock'],    // bwrap 优先
  darwin: ['seatbelt'],
  win32: ['windows-acl'],
}
```

选择逻辑：
- 链中只有一个候选时：直接选择，不探测（执行时拒绝仍然 fail-closed）
- 多个候选时：按顺序功能性探测，选择第一个可用的
- 无可用候选时：抛出 `SandboxUnavailableError`

### 4.2 各后端详解

#### Bubblewrap (bwrap) — Linux 首选

```typescript
bwrapProfileArgs(policy): string[]
// read-only: --ro-bind / / --dev /dev --unshare-pid --proc /proc --die-with-parent
// workspace-write: 额外 --tmpfs /tmp --bind <workspaceRoot> <workspaceRoot>
```

- **优点**: Mount namespace 隔离，接近模式词汇表的语义表达
- **执行完备性**: `full`

#### Landlock — Linux 备选

```typescript
landlockProfileArgs(policy): string[]
// read-only: readWrite=['/dev/null'], readOnly=['/']
// workspace-write: readWrite 额外包含 '/tmp', workspaceRoot
```

- **优点**: 无需特权，无 SUID 二进制
- **执行完备性**: 根据内核 ABI 可能 `full` 或 `partial`
- **Runner 失败检测**: 退出码 `125` + stderr 子串 `landlock-run: `

#### Seatbelt (sandbox-exec) — macOS

```typescript
seatbeltProfileArgs(policy): string[]
// 基于 SBPL (Sandbox Profile Language)
// (version 1) (allow default) (deny file-write*) (allow file-write* (literal "/dev/null"))
// workspace-write 时额外添加可写根路径的 (allow file-write* (subpath ...))
```

- **优点**: macOS 原生支持
- **执行完备性**: `full`
- **注意**: Apple 标记 `sandbox-exec` 为 deprecated 但仍发布在所有 macOS 上

#### Windows ACL Restricted Token — Windows

- **机制**: `WRITE_RESTRICTED` Token，携带限制 SID
- **检测**: 写入时检查调用方 SID 是否在限制列表的 ACE 中
- **执行完备性**: `partial`（已知限制：WRITE_RESTRICTED 需要 Everyone 在限制列表中；NTFS hard link 可以别名文件）
- **授权生命周期**:
  - Workspace ACE: 永久 (per-Workspace 复用，跳过重复的树传播)
  - Temp ACE: 可撤销 (Provider dispose 时清理，每次 Session 随机路径)
- **Runner 失败检测**: 退出码 `127` + stderr 子串 `windows-acl-run: `

### 4.3 `!!js` 表达式与 Runner 覆盖

配置中支持通过 `runnerCommand` 覆盖后端：

```yaml
- id: sandbox
  name: '@deepseek-ai/dsh-sandbox-local'
  config:
    runnerCommand: ['custom-sandbox', '--profile', 'strict']
    runnerFailureSignatures: ['custom-sandbox: fatal']
```

使用 `runnerCommand` 时自动断言 `full` enforcement，跳过内置选择和探测。

### 4.4 `!!js` 表达式在 base bundle 配置中的使用

```yaml
- id: sandbox-policy
  name: '@deepseek-ai/dsh-sandbox-policy'
  config:
    mode: !!js process.env.DSH_PERMISSION_MODE ?? 'workspace-write'
    workspaceRoot: !!js process.cwd()
```

---

## 五、策略服务 (`@deepseek-ai/dsh-sandbox-policy`)

### 5.1 策略决议层次

`ctx.sandboxPolicy.resolve()` 的优先级（从高到低）：

1. **批准的升级模式** — 经 `ctx.approval` 批准的严格更宽模式
2. **Session 级覆盖** — Session 日志中最后的 `sandbox/mode` event
3. **部署默认** — 配置的 `mode` 字段（默认 `'workspace-write'`）

workspace root 优先取 Session 的 cwd（不可变），fallback 到部署配置。

### 5.2 Session 模式切换

```typescript
// 写入路径
function setSandboxMode(session: Session, mode: SandboxMode): void {
  session.append('sandbox/mode', { mode })
}

// 读取路径  
function overrideOf(session: Session): SandboxMode | undefined {
  return ctx.sessionProjections.stateOf(session, 'sandboxMode') ?? undefined
}
```

- `sandbox/mode` 是日志级 event（像 `approval/*`），不进入模型 transcript
- 通过 `sessionProjections` 机制持久化和回放
- 切换立即对 Session 的下一个受限调用生效

### 5.3 系统 Prompt 注入

`SandboxPolicyService` 在每个 agent request 前向系统 prompt 注入当前策略描述：

```typescript
// read-only 模式:
"Current DSH file policy: read-only. Any available operation enforced by
 the DSH file sandbox cannot modify files in the standing mode..."

// workspace-write 模式:
"Current DSH file policy: workspace-write. Any available operation enforced by
 the DSH file sandbox may modify files under the session workspace: \"<path>\"..."

// danger-full-access 模式:
"Current DSH file policy: danger-full-access. The DSH file sandbox does not
 restrict file modifications by available operations."
```

### 5.4 Invariant 验证

`sandbox-policy` 注册了 Invariant 验证，检查所有 `sandbox/mode` event 的 mode 值是否有效。

---

## 六、消费者集成

### 6.1 Bash Sandbox (`@deepseek-ai/dsh-bash-sandbox`)

继承 `LocalBashExecutor`，在每次命令执行前通过 `ctx.sandbox.confine()` 包裹：

```typescript
class SandboxBashExecutor extends LocalBashExecutor {
  async run(spec: ShellExecSpec): Promise<ShellRunResult> {
    const policy = spec.sandboxPolicy
    if (mode === 'danger-full-access') return super.run(spec)  // 直接执行
    const confined = this.confine(spec.command, { ...policy, mode })
    const result = await this.runArgv(spec, confined.argv)    // 执行包裹后的 argv
    // 先检测 Runner 失败（命令根本没运行）
    // 再检测 Policy 拒绝（沙箱正常工作但阻止了操作）
    return { ...result, sandbox: { mode, denied: classifyDenial(...), enforcement: confined.enforcement } }
  }
}
```

**背景进程**同样受限：`start()` 方法包裹后启动，`onProcessDone()` 中分类结果。

**错误分类顺序**:
1. Runner 失败 — 错误码 + stderr 匹配 runner failure rules → `SANDBOX_UNAVAILABLE`
2. Policy 拒绝 — 非零退出 + stderr 匹配 denial signatures → `sandbox.denied = true`
3. 正常命令失败 — 非零退出但不匹配以上两类 → 普通退出码错误

### 6.2 FS Sandbox (`@deepseek-ai/dsh-fs-sandbox`)

继承 `LocalFileSystem`，在写入/编辑前做 in-process 路径检查：

```typescript
class SandboxedFileSystem extends LocalFileSystem {
  // read-only: 直接拒绝所有写入 → FS_SANDBOX_DENIED
  // workspace-write: 重新 canonicalize 目标路径，检查是否在 writableRoots 下
  // danger-full-access: 直接委托给本地实现
}
```

**与 bash-sandbox 的差异**:
- FS sandbox 是内核级隔离，而是**可信代码中的路径检查**
- 存在 TOCTOU 窗口（祖先 symlink 在检查后到 syscall 前被交换），对当前威胁模型可接受
- 拒绝 error 携带 `FS_SANDBOX_DENIED` 结构化 error code

### 6.3 Terminal Bash 集成

持久化终端 (`terminal-bash`) 额外要求：**模式切换时不得有活动的终端 session**：

```typescript
if (event.type === 'sandbox/mode') {
  const currentMode = folded ?? state.sandboxPolicy.defaultMode
  // 如果有活动终端，拒绝切换模式
  throw new Error(
    `cannot change sandbox mode from "${currentMode}" to "${event.data.mode}" 
     while persistent terminal sessions are open or being created...`
  )
}
```

### 6.4 工具层的升级集成

#### Bash 工具升级

```typescript
interface BashToolArgs {
  command: string
  description: string
  sandbox_permissions?: string    // 升级目标模式
  justification?: string          // 升级理由（模型提供的一句话）
}
```

工具描述中根据是否有 confining backend 决定是否展示升级参数。

#### FS 工具升级

`FsSandboxController` 为 write 和 edit 工具提供统一的升级 API：

```typescript
class FsSandboxController {
  async resolvePolicy(toolName, args, exec): Promise<SandboxExecutionPolicy | undefined> {
    // 1. 验证 escalation 参数配对
    // 2. 解析 standing policy
    // 3. 如果没有升级请求，返回 standing policy
    // 4. 如果有升级请求，通过 approveEscalation 请求用户批准
    // 5. 返回携带批准模式的 policy
  }

  mapError(error, policy): unknown {
    // FS_SANDBOX_DENIED → 映射为携带 [sandbox: …] 标记和升级提示的 error
  }
}
```

---

## 七、动态代码沙箱 (`cordis-host-runner`)

动态 Cordis Plugin 的代码执行使用**不同的沙箱机制**——不是进程级文件沙箱，而是 `node:vm` 沙箱：

### 7.1 `node:vm` 沙箱

```typescript
function createSandbox(id: string): object {
  const sandbox = {
    ...nodeApiTraps(),           // Node API 陷阱（重定向到 cordis 服务）
    console: taggedConsole(id),  // 带标签的写通控制台
    harness: { defineTool, registerTool },  // 工具注册边界
    btoa, atob, TextEncoder, TextDecoder,  // 编码原语
  }
  createContext(sandbox)         // vm context 隔离
  patchDualRealmInstanceof(sandbox)
  return sandbox
}
```

### 7.2 Context Facade (guard.ts)

运行的 plugin 不是拿到真实的 `ctx`，而是一个**白名单代理**：

- ✅ 允许: `ctx.tools.register`, `ctx.on`, `ctx.provide`, `ctx.effect`, `ctx.get`, timer helpers
- ✅ 允许: 声明注入的服务的代理（DenyContext on return value）
- ❌ 拒绝: 框架内部成员 (root, fiber, registry, extend, plugin...)
- ❌ 拒绝: `require`, `setTimeout`, `setInterval`, `fetch` 等 Node API（报错引导使用 cordis 服务替代）

### 7.3 Node API 重定向

```typescript
const NODE_API_REDIRECTS = {
  require:    'Node modules are unavailable. Use the cordis services on ctx instead...',
  setTimeout: 'Node timers are unavailable. Use the cordis timer service instead...',
  fetch:      'Network access goes through the cordis web service...',
}
```

### 7.4 安全边界

这个沙箱**不是安全隔离**——host realm 的 helper 函数仍然是逃逸路径。它的设计目标是：
- 使协同包可检查和可处置
- 防止意外访问框架内部
- 引导使用 cordis 服务替代 Node API

---

## 八、组合配置 (Composition)

### 8.1 Base Bundle 中的 Sandbox 堆栈

```yaml
# packages/bundle/base/cordis.patch.yml

# 本地 sandbox 后端
- id: sandbox
  name: '@deepseek-ai/dsh-sandbox-local'

# 策略服务
- id: sandbox-policy
  name: '@deepseek-ai/dsh-sandbox-policy'
  config:
    mode: !!js process.env.DSH_PERMISSION_MODE ?? 'workspace-write'
    workspaceRoot: !!js process.cwd()

# 受限 Shell 执行器
- id: bash-sandbox
  name: '@deepseek-ai/dsh-bash-sandbox'
  disabled: !!js process.platform === 'win32'

- id: pwsh-sandbox
  name: '@deepseek-ai/dsh-pwsh-sandbox'
  disabled: !!js process.platform !== 'win32'

# 审批服务
- id: approval
  name: '@deepseek-ai/dsh-user-approval'
  config:
    policy: !!js "(process.env.DSH_PERMISSION_MODE ?? 'workspace-write') === 'danger-full-access' ? 'never' : 'ask'"

# 权限预设
- id: permission
  name: '@deepseek-ai/dsh-permission-presets'
  config:
    presets:
      read-only:         { sandbox: read-only, approval: ask }
      workspace-write:   { sandbox: workspace-write, approval: ask }
      danger-full-access: { sandbox: danger-full-access, approval: never }

# 受限文件系统
- id: fs-sandbox
  name: '@deepseek-ai/dsh-fs-sandbox'
```

### 8.2 环境变量控制

通过 `DSH_PERMISSION_MODE` 环境变量控制默认模式：

```bash
# 只读模式
DSH_PERMISSION_MODE=read-only dsh

# 默认 (可写工作区)
dsh  # 等效于 DSH_PERMISSION_MODE=workspace-write

# 无限制
DSH_PERMISSION_MODE=danger-full-access dsh
```

### 8.3 Agent Preset 与 Sandbox 的关系

Sandbox 后端 (`sandbox`, `bash-sandbox`, `fs-sandbox`) 和审批服务在 **Host 平面 (base bundle)**，不在 Agent Preset 中。Agent Preset 只包含模型可见工具（`tool-bash`, `tool-fs`），这些工具解析 Host 平面的能力。

---

## 九、E2B 远程沙箱

`@deepseek-ai/dsh-e2b` 不实现 `SandboxProvider`，而是**替换整个 capability seam**（`ctx.shell`、`ctx.fs`），将进程和文件系统操作委托给远程 E2B 沙箱：

```
sandbox (本地) → ctx.sandbox.confine() → 本地运行
E2B (远程)     → ctx.shell/ctx.fs     → 远程沙箱运行
```

这遵循设计哲学："containers, microVMs, and remote execution replace the surrounding capability seam instead"。

---

## 十、关键代码位置

| 文件 | 角色 |
|------|------|
| `packages/sandbox/sandbox/src/index.ts` | SandboxProvider 抽象服务、SandboxMode、ConfinedArgv、SandboxUnavailableError |
| `packages/sandbox/sandbox/src/escalation.ts` | 升级词汇（WIDER_MODES）、审批编排（approveEscalation）、拒绝/提示标记 |
| `packages/sandbox/sandbox/src/roots.ts` | writableRoots 派生（Seatbelt 和 fs-sandbox 共用） |
| `packages/sandbox/sandbox-local/src/index.ts` | LocalSandboxProvider：平台链选择、功能性探测、各后端 argv 构建 |
| `packages/sandbox/sandbox-local/src/profiles.ts` | bwrap/Landlock/Seatbelt 的 profile 参数构建 |
| `packages/sandbox/sandbox-policy/src/index.ts` | SandboxPolicyService：部署默认、Session 覆盖、policy 决议、系统 prompt 注入 |
| `packages/sandbox/sandbox-policy/src/session-mode.ts` | setSandboxMode 写入路径、sandbox/mode event 声明 |
| `packages/sandbox/sandbox-policy/src/invariant.ts` | sandbox/mode event 的 invariant 验证 |
| `packages/sandbox/sandbox-windows-acl/src/index.ts` | AclSandbox：WRITE_RESTRICTED Token + DACL 管理 |
| `packages/shell/bash-sandbox/src/index.ts` | SandboxBashExecutor：通过 ctx.sandbox 包裹 bash 命令 |
| `packages/shell/bash-sandbox/src/helpers.ts` | 结果分类（Runner 失败 vs Policy 拒绝 vs 正常失败） |
| `packages/fs/fs-sandbox/src/index.ts` | SandboxedFileSystem：In-process 文件写入围栏 |
| `packages/fs/fs-sandbox/src/containment.ts` | 路径包含检查（词汇快速路径 + 文件系统 identity fallback） |
| `packages/fs/tool-fs/src/sandbox.ts` | FsSandboxController：FS 工具的升级 API |
| `packages/extensions/cordis-host-runner/src/sandbox.ts` | 动态代码的 node:vm 沙箱创建 |
| `packages/extensions/cordis-host-runner/src/guard.ts` | Context Facade（动态代码的 ctx 白名单代理） |
| `packages/bundle/base/cordis.patch.yml` | 生产环境 sandbox 堆栈组合配置 |
| `docs/subsystems/sandbox.md` | 官方子系统参考文档 |

---

## 十一、设计哲学总结

1. **Same-world by contract**: `ctx.sandbox` 包裹 argv 在同一宿主机上运行；容器/microVM/远程执行替换整个 capability seam
2. **Policy rides the call**: Policy 每次调用携带，不固定在 provider 上
3. **Fail closed**: `confine()` 返回强制执行 argv 或抛错；绝不无声绕过
4. **One vocabulary**: 拒绝和升级的文本标记由 sandbox 包统一提供，bash 和 fs 两个系列共享
5. **Platform adaptive**: 根据平台自动选择最合适的后端，功能性探测确保可用性
6. **Two sandbox types**: 进程沙箱 (kernel 级，隔离不可信命令) 和代码沙箱 (`node:vm`，隔离协同包)