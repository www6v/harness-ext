# E2B 远程沙箱 — 机制和使用分析

## 概述

E2B（Environment to Box）远程沙箱是 deepseek-harness 的一项**实验性 POC 功能**，允许 agent 的文件操作和命令执行完全运行在远程 Linux 沙箱中，而非宿主机。与本地 sandbox 系统（见 [09-sandbox.md](./09-sandbox.md)）不同，E2B **不是** `SandboxProvider` 的实现——它是一套**能力接缝替换（capability seam replacement）**，通过替换 `ctx.fs`（文件系统）和 `ctx.subprocess`（子进程）两个 Cordis 服务，将整个执行世界迁移到远程。

### 核心设计理念

```
┌─────────────────────────────────────────────────────┐
│                    Host Machine                       │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Harness  │  │  Model Calls │  │ Session State │  │
│  │  (Local)  │  │   (Local)    │  │   (Local)     │  │
│  └─────┬─────┘  └──────────────┘  └───────────────┘  │
│        │                                              │
│        │ E2B SDK (HTTP/SSE)                           │
│        ▼                                              │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Remote Linux Sandbox                │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │  │
│  │  │   Files   │  │ Commands │  │   Terminals   │  │  │
│  │  │ (fs-e2b)  │  │ (subpr.) │  │  (subpr-e2b)  │  │  │
│  │  └──────────┘  └──────────┘  └───────────────┘  │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**关键特性**：

| 特性 | 说明 |
|------|------|
| **共享沙箱** | 一个 harness 实例共享一个远程 Linux 沙箱，文件和命令在同一世界执行 |
| **接缝替换** | 替换 `ctx.fs` 和 `ctx.subprocess`，不替换 harness 本身 |
| **完全隔离** | 宿主机环境变量和凭据绝不隐式传入沙箱 |
| **临时性** | 沙箱是临时的，无重连、快照、模板支持 |
| **实验性** | 不在默认发布 composition 中，需要显式配置 |

---

## 一、包族架构

E2B 功能由 3 个包组成，按依赖关系排列：

```
packages/e2b/
├── e2b/                  # 沙箱生命周期所有者
│   ├── src/index.ts      # E2BRuntime — 共享 SDK handle
│   └── src/api-url.ts    # API URL 派生
├── fs-e2b/               # 远程文件系统
│   └── src/index.ts      # E2BFileSystem extends FileSystem
└── subprocess-e2b/       # 远程进程管理
    ├── src/index.ts      # E2BSubprocessRuntime extends SubprocessRuntime
    ├── src/process.ts    # E2BSubprocessHandle — 进程生命周期
    ├── src/terminal.ts   # E2BTerminalHandle — PTY 和会话管理
    ├── src/environment.ts # 远程环境探测、清洗、序列化
    ├── src/output.ts     # Base64 解码器、有界输出读取器
    └── src/remote.ts     # 共享控制 shell 辅助函数
```

| 包 | Cordis 键 | 角色 |
|----|-----------|------|
| `@deepseek-ai/dsh-e2b` | `ctx.e2b` | 共享远程 Linux 沙箱的 SDK handle 所有者 |
| `@deepseek-ai/dsh-fs-e2b` | `ctx.fs` | 远程沙箱内的文件读、写、编辑、列表 |
| `@deepseek-ai/dsh-subprocess-e2b` | `ctx.subprocess` | 远程沙箱内的 shell 命令和交互式终端 |

---

## 二、E2BRuntime — SDK Handle 所有者

`E2BRuntime` 是沙箱的唯一所有者，提供共享的 E2B SDK handle。`packages/e2b/e2b/src/index.ts`

### 2.1 初始化

```typescript
class E2BRuntime extends Service {
  // 延迟创建 — 只有首次 consumer 请求时才连接
  private sandboxPromise: Promise<Sandbox> | undefined

  async getSandbox(): Promise<Sandbox> {
    if (this.sandboxPromise === undefined) {
      this.sandboxPromise = this.createSandbox()
    }
    return this.sandboxPromise
  }
}
```

沙箱通过 `Sandbox.create()` 创建，参数为：

| 参数 | 值 | 说明 |
|------|-----|------|
| `apiKey` | `ctx.config.e2bApiKey` | E2B API 密钥 |
| `timeoutMs` | `ctx.config.e2bTimeoutMs` | 沙箱超时（默认 300000ms = 5分钟） |
| `secure` | `true` | 强制安全连接 |
| `lifecycle.onTimeout` | `'kill'` | 超时后终止沙箱 |

创建后，runtime 初始化两个关键目录：

```typescript
// 共享工作目录 — 由 ctx.config.cwd 配置
await sandbox.files.makeDir(this.cwd)
await sandbox.commands.run(`chmod 700 -- ${quoteE2BShellArg(this.cwd)}`)

// 私有运行时根目录 — .dsh-e2b，存放进程状态和 spill 文件
this.runtimeRoot = posix.join(this.cwd, '.dsh-e2b')
await sandbox.files.makeDir(this.runtimeRoot)
```

### 2.2 销毁

```typescript
async [Symbol.asyncDispose]() {
  await this.sandbox?.kill()  // 直接终止远程沙箱
}
```

### 2.3 API URL 派生

`packages/e2b/e2b/src/api-url.ts` 中的 `e2bApiUrl()` 函数按以下优先级派生控制面 URL：

1. **`E2B_API_URL`** 环境变量 — 显式覆盖
2. **`E2B_DEBUG=true`** — 切换到 `http://localhost:3000`（本地调试）
3. **默认** — `https://api.{E2B_DOMAIN}`（默认 `e2b.app`）

---

## 三、E2BFileSystem — 远程文件系统

`packages/e2b/fs-e2b/src/index.ts` — `E2BFileSystem` 完整实现了 `FileSystem` 接口，将所有文件操作路由到远程沙箱。

### 3.1 路径规范化

使用 `realpath -mz | base64 -w0` 管道来获取规范路径：

```bash
# 通过 base64 编码传输，保证路径中的换行符和特殊字符完整性
realpath -mz "${path}" | base64 -w0
```

- `-m`: 不要求路径存在（missing）
- `-z`: NUL 分隔（处理换行路径）
- `base64 -w0`: 单行 base64（避免 SDK 回调分块损坏数据）

### 3.2 原子写入

写入采用**分期目录 + 原子 rename** 模式：

```
1. 创建随机 staging 目录（模式 0700）
2. 上传内容写入 staging 目录中的文件
3. 保留现有文件的 POSIX 模式
4. 通过同文件系统 rename 原子发布
5. 返回提交后的版本元数据
6. 清理 staging 目录（失败不转义为写入失败）
```

**createIfAbsent** 使用 `ln -T` 进行原子保护，防止目标处出现目录时意外覆盖。

### 3.3 文本编辑

文件编辑采用以下流程：

1. 读取完整文件到宿主机内存
2. 对匹配文本进行 LF 规范化
3. 执行精确替换
4. 通过原子写入流程回写完整文件
5. 恢复文件的原始 CRLF 风格

### 3.4 并发控制

- **每文件内存锁**：序列化同一文件的写入操作
- **版本守卫**：如果文件在读取后被修改（通过扩展属性 `dsh-version` 检测），写入被拒绝
- **限界**：跨 harness 连接的竞争条件不在保护范围内（POC 限制）

### 3.5 错误映射

E2B 特定的错误被映射到标准 `FsError` 代码：

| E2B 错误 | FsError |
|----------|---------|
| 文件不存在 | `FS_NOT_FOUND` |
| 权限不足 | `FS_PERMISSION_DENIED` |
| 操作中止 | `FS_ABORTED` |
| 一般 I/O 错误 | `FS_IO_ERROR` |
| 非 UTF-8 文本 | `FS_NOT_TEXT` |
| 文件过大 | `FS_TOO_LARGE` |

---

## 四、E2BSubprocessRuntime — 远程进程管理

`packages/e2b/subprocess-e2b/src/index.ts` — `E2BSubprocessRuntime` 扩展 `SubprocessRuntime`，提供远程命令和终端能力。

### 4.1 配置

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `pollMs` | `20` | 运行中命令的状态轮询间隔（毫秒）|

### 4.2 命令生成 (spawn)

`spawn()` 创建 `E2BSubprocessHandle`，支持三种输出模式：

| 模式 | 说明 |
|------|------|
| **Pipe** | 输出流向宿主机 Node.js 流（通过 base64 编码传输） |
| **Inherit** | 输出直接写入 harness 进程流 |
| **Collect** | 在宿主机保留有界尾部，可选完整 spill 文件 |

同时支持：
- **批处理 stdin**：一次性发送完整输入
- **流式 stdin**：通过 SDK handle 增量发送

### 4.3 终端生成 (spawnTerminal)

`spawnTerminal()` 创建 `E2BTerminalHandle`，分配远程 PTY，支持：
- 交互式输入/输出
- 前台进程组检查与信号
- 完整的会话生命周期管理

---

## 五、进程生命周期 — E2BSubprocessHandle

`packages/e2b/subprocess-e2b/src/process.ts` — 这是整个 E2B 子系统中**最复杂的部分**，包含完整的 bootstrap、output transport、termination ladder 实现。

### 5.1 Bootstrap Wrapper

每个命令通过一个**自包含的 bootstrap shell 脚本**运行：

```bash
#!/bin/bash
set -euo pipefail
dsh_state=$1

# 从私有状态文件读取环境变量和参数
mapfile -d '' -t dsh_env < "$dsh_state/environment"
mapfile -d '' -t dsh_argv < "$dsh_state/argv"

# 消费后立即删除状态文件（防止泄露）
rm -f -- "$dsh_state/environment" "$dsh_state/argv"

# 在 setsid 下使用完全干净的环境启动目标进程
exec setsid --wait env -i -- "${dsh_env[@]}" "${dsh_argv[@]}"
```

关键设计：

| 设计点 | 说明 |
|--------|------|
| **`env -i`** | 完全清空环境，只使用显式提供的变量 |
| **`setsid --wait`** | 创建新会话，隔离进程组，等待所有子进程退出 |
| **状态文件消费后删除** | 环境变量和参数不在远程磁盘上持久化 |
| **工具发现** | 从沙箱 PATH 中自查必需工具，缺失则拒绝启动 |

### 5.2 私密进程身份和发布

Bootstrap 完成后，wrapper 将进程组 ID 和退出码发布到私有状态目录：

```
.dsh-e2b/
└── processes/
    └── <uuid>/
        ├── pgid          # 进程组 ID
        ├── exit-code      # 退出码
        └── output/       # spill 文件
```

**重要限制**：发布的进程组 ID **不是**请求的目标 PID。同步接缝立即返回句柄，命令异步启动。在分配 SDK handle 之前，启动信号可以中止环境准备和私有状态准备；一旦开始分配，取消操作将等待一个可用于清理的临时 SDK handle。

### 5.3 输出编码和传输

远程 wrapper 将 stdout/stderr 通过 **base64 编码** 传输：

```bash
# 远程端编码器
exec 1> >(base64 -w0 | tee -a "$output_file")
exec 2> >(base64 -w0 | tee -a "$error_file")
echo '!dsh-e2b-output-complete!'  # 保留的完成帧
```

| 组件 | 说明 |
|------|------|
| **`tee` + `head -c`** | 可选的限界 spill 文件 |
| **base64 帧** | 换行分隔的 ASCII base64 帧，可跨任意 SDK 回调分块 |
| **`!dsh-e2b-output-complete!`** | 保留非 base64 帧，标记编码器干净 EOF |

宿主机端由 `E2BBase64Decoder`（`output.ts`）解码：

```typescript
class E2BBase64Decoder {
  push(text: string): Buffer  // 解码每个完整的换行分隔帧
  finish(requireComplete: boolean): void  // 验证完成帧
}
```

### 5.4 E2BOutputReader — 有界读取器

`output.ts` 中的 `E2BOutputReader` 实现在宿主机内存中保留有界尾部，溢出部分通过 spill 文件访问：

```
宿主机内存 (maxBytes 尾部)
    ↓ 溢出
远程 spill 文件 (完整输出)
```

- **内存尾部**：保留最近 `maxBytes` 字节
- **Spill 路径**：输出长度在 `maxSpillBytes` 内时提供完整对等文件路径
- **Spill 验证**：仅编码器达到干净 EOF 时才视为有效
- **Offset 读取**：支持从任意字节偏移量读取

### 5.5 终止阶梯 (Termination Ladder)

进程终止和回滚共享**同一信号路径**，按阶梯逐步升级：

```
1. SIGTERM → 等待 graceMs
   ↓ 仍有存活进程组
2. SIGKILL → 等待 graceMs
   ↓ 仍有存活进程组
3. SDK handle.kill() — 最终兜底
   ↓ 验证
4. 进程表探针确认静止（quiescence）
```

**关键容忍性**：

| 容忍结果 | 处理方式 |
|----------|----------|
| `SandboxNotFoundError` | 视为静止 — 沙箱消失即终止 |
| `CommandExitError`（kill 返回非零） | 视为进程组已消失 |
| 只含 Zombie 的进程组 | 视为空组 |

进程组活性通过 `ps -eo sid=,pgid=,stat=` 轮询检查，过滤掉 `Z`（zombie）、`X`（dead）、`x` 状态。

### 5.6 取消流程

取消操作经过精心编排：

```
spawn() 被取消
  ├── 分配前 → 中止环境准备和私有状态准备
  └── 分配后 → 等待临时 SDK handle，然后执行终止阶梯
```

- handle.disconnect() 断开 SDK 连接

---

## 六、终端生命周期 — E2BTerminalHandle

`packages/e2b/subprocess-e2b/src/terminal.ts` — 终端管理比普通进程更复杂，因为它需要 PTY 分配、会话管理和前台进程组信号。

### 6.1 PTY 分配和 Bootstrap

终端通过 `sandbox.pty.create()` 分配 PTY，然后通过私有的 **terminal runner** 替换 E2B 的默认登录 shell：

```bash
#!/bin/bash
set -euo pipefail
dsh_state=$1
# 读取环境、argv、输出标记
mapfile -d '' -t dsh_env < "$dsh_state/environment"
mapfile -d '' -t dsh_argv < "$dsh_state/argv"
dsh_output_marker=$(<"$dsh_state/output-marker")
# 消费后删除状态文件
rm -f -- "$dsh_state/environment" "$dsh_state/argv" "$dsh_state/output-marker" "$dsh_state/runner.bash"
# 发布输出标记（边界信号）
printf '%s' "$dsh_output_marker"
# 用显式环境替换终端进程
exec env -i -- "${dsh_env[@]}" "${dsh_argv[@]}"
```

### 6.2 Bootstrap 边界检测

`BootstrapOutputFilter` 是一个关键组件——它在终端输出流中搜索唯一的输出标记（UUID），以此确定 bootstrap shell 已完成设置、目标进程已接管终端：

```
Bootstrap Shell 输出             目标进程输出
┌─────────────────────┬──────────────────────────────┐
│ dsh-e2b-bootstrap:  │  实际程序的 stdout/stderr     │
│ <uuid>              │                              │
└─────────────────────┴──────────────────────────────┘
                      ↑
               BootstrapOutputFilter 在此处发布 "ready"
```

- 标记之前的输出被过滤掉（来自 bootstrap shell）
- 标记之后的输出直接透传给 `PassThrough` 流
- 如果终端在发布标记前退出，则报错

### 6.3 会话和进程组管理

终端使用 **会话 ID (SID)** 而非单个 PID 来管理进程：

```typescript
// 获取终端会话 ID
const sessionId = await terminalSessionId(sandbox, pid, envs)
// 查询会话中所有活动的进程组
const groups = await sessionProcessGroups(sandbox, sessionId, envs)
// ps -eo sid=,pgid=,stat= | awk '$1 == {sid} && $3 !~ /^[ZXx]/ { print $2 }'
```

**安全防护**：
- 进程组 ID ≤ 1 被视为不安全，会抛出错误
- 前台进程组不能是终端 shell 本身（拒绝 SIGKILL 终端 PID）

### 6.4 终端终止

与普通进程相同的阶梯式终止，但作用于整个**会话**的所有进程组：

```
1. SIGTERM → 等待 graceMs → 轮询 sessionProcessGroups
2. SIGKILL → 等待 graceMs → 轮询 sessionProcessGroups
3. handle.kill()（E2B PTY 终止）
4. handle.disconnect()
5. 删除私有状态目录
```

### 6.5 回滚（Rollback）

如果终端在 **bootstrap 阶段** 失败（尚未发布到消费者），执行专门的 `rollbackUnpublishedTerminal` 流程：

```
1. 获取终端会话 ID
2. 查询会话中所有进程组
3. SIGTERM → 等待 → SIGKILL → 验证
4. 如果顶层仍未退出，调用 handle.kill()
5. 最终验证所有进程组已清除
6. handle.disconnect()
```

回滚失败会抛出 `AggregateError`，汇总所有清理失败。

### 6.6 前台进程组信号

终端支持向前台进程组发送信号：

```typescript
signalForeground(signal: SubprocessTerminalSignal): Promise<number> {
  // 先检查前台进程组
  const foreground = await inspectForegroundOnce(signal)
  // 通过 kill -SIGNAL -- -PGID 发信号
  await sandbox.commands.run(`kill -${signal} -- -${pgid}`)
}
```

**限制**：E2B 暴露前台进程组 ID，但不暴露 `/proc` 内存访问来证明特定系统调用正在等待 fd 0。因此，`inputWaiting` 始终返回 `false`，通用的 PTY 后端回退到受控的提示标记和有界静默。

---

## 七、环境隔离

`packages/e2b/subprocess-e2b/src/environment.ts` — 环境管理是整个 E2B 系统中最严格的安全措施。

### 7.1 远程环境探测

通过一个可信的控制 shell 命令获取远程环境：

```bash
set -o pipefail
# 获取用户 home 目录
dsh_e2b_passwd="$(getent passwd "$(id -u)")"
IFS=: read -r _ _ _ _ _ dsh_e2b_home _ <<<"$dsh_e2b_passwd"
test -n "$dsh_e2b_home" -a -d "$dsh_e2b_home"
printf '%s' "$dsh_e2b_home" | base64 -w 0
printf '\n'
# 获取完整环境（NUL 分隔）
env -0 | base64 -w 0
```

| 传输机制 | 说明 |
|----------|------|
| **base64 编码** | 保证 SDK 回调分块不会破坏 UTF-8 |
| **严格解码** | `TextDecoder('utf-8', { fatal: true })`，无效 UTF-8 直接报错 |
| **HOME 修复** | 从 passwd 条目解析用户登录 home，覆盖可能损坏的 `HOME` 环境变量 |

### 7.2 环境清洗

`scrubRemoteEnvironment()` 删除敏感环境变量：

```typescript
function scrubRemoteEnvironment(raw: string): Map<string, string> {
  for (const [name, value] of remoteEnvironmentEntries(raw)) {
    // 删除 harness 内部变量
    if (name.startsWith('DSH_')) continue
    // 删除凭据形状的变量
    if (SENSITIVE_ENV_PATTERN.test(name)) continue
    environment.set(name, value)
  }
}
```

**清洗规则**：

| 匹配项 | 说明 |
|--------|------|
| `DSH_*` | 所有 harness 私有变量 |
| `*KEY*`, `*SECRET*`, `*TOKEN*` (大小写不敏感) | 凭据形状的变量名 |

### 7.3 Bootstrap 环境隔离

命令和 PTY 登录 shell 接收一个**净化后的最小环境**：

```typescript
function bootstrapEnvironment(raw: string): Record<string, string> {
  const environment: Record<string, string> = { TERM: 'dumb' }
  for (const [name] of remoteEnvironmentEntries(raw)) {
    if (name.startsWith('DSH_') || SENSITIVE_ENV_PATTERN.test(name)) {
      environment[name] = ''  // 空覆盖，防止 shell profile 重新设置
    }
  }
  return environment
}
```

**关键防护**：
- 敏感变量被设为**空字符串**（而非不设置），防止 shell profile（`.bashrc`等）重新暴露
- 全新的随机 `HOME` 目录防止 `~/.profile` 泄露凭据
- 每个命令的环境是完全显式的——只包含 `spec.env` 中显式请求的条目

### 7.4 环境序列化

```typescript
function serializeRemoteEnvironment(
  raw: string,
  explicit: Readonly<NodeJS.ProcessEnv> | undefined,
): string {
  const environment = scrubRemoteEnvironment(raw)
  for (const [name, value] of Object.entries(explicit ?? {})) {
    // undefined 值表示删除此条目
    if (value === undefined) environment.delete(name)
    else environment.set(name, value)
  }
  // 返回 NUL 分隔的 name=value 条目
  return [...environment].map(([name, value]) => `${name}=${value}\0`).join('')
}
```

**验证规则**：
- 名称不能为空、不能包含 `=`、不能包含 `\0`
- 值不能包含 `\0`
- 违反上述规则的条目在启动前被拒绝

---

## 八、远程控制辅助函数

`packages/e2b/subprocess-e2b/src/remote.ts` — 所有进程和终端终止共享这些辅助函数。

### 8.1 signalRemoteGroups

```typescript
async function signalRemoteGroups(
  sandbox: Sandbox,
  envs: Record<string, string>,
  groups: readonly number[],
  signal: 'TERM' | 'KILL',
): Promise<void>
```

通过 `kill -TERM -- -PGID1 -PGID2 ...` 向远程进程组发信号。

**容忍性**：
- `CommandExitError`（kill 返回非零）：视为进程组已消失（正常 — 与进程终止阶梯的容忍性一致）
- `SandboxNotFoundError`：视为静止

### 8.2 轮询辅助

| 函数 | 用途 |
|------|------|
| `delay(ms)` | 等待指定毫秒数 |
| `waitTick(pollMs, signal?)` | 等待一个轮询间隔或直到 abort 信号 |
| `commandOpts(envs, signal?)` | 生成控制命令的 SDK 选项（带隔离的 HOME 覆盖） |
| `signalOpts(signal?)` | 生成可选信号的 SDK 选项 |

---

## 九、组合和使用

### 9.1 加载顺序

`packages/e2b/README.md` 指定了组合顺序：

```yaml
# 1. 先加载沙箱所有者
- name: '@deepseek-ai/dsh-e2b'
# 2. 再加载文件和子进程适配器（顺序无关）
- name: '@deepseek-ai/dsh-fs-e2b'
- name: '@deepseek-ai/dsh-subprocess-e2b'
```

E2B **不替换**以下本地组件：
- Harness 进程本身
- 模型调用
- 会话状态
- Skill 系统
- 审批/权限系统

### 9.2 配置

```yaml
# E2B 沙箱配置
e2bApiKey: "<E2B_API_KEY>"          # 必需
e2bTimeoutMs: 300000                 # 沙箱超时（毫秒），默认 5 分钟
e2bCwd: "/home/user"                 # 远程工作目录

# 子进程配置
pollMs: 20                           # 命令状态轮询间隔
```

### 9.3 工作目录约定

- `cwd` 是共享工作目录，文件和命令都在此上下文中运行
- `cwd` 是约定而非强制（非沙箱 containment）
- `cwd` 初始为空，随 agent 工作逐渐填充
- 宿主机文件**不**被上传到 `cwd`

---

## 十、已知限制

### 10.1 POC 级别的限制

| 限制 | 影响 |
|------|------|
| **无宿主机同步** | cwd 始终保持空白，宿主机文件不会被导入 |
| **无重连** | 沙箱消失后无法恢复 |
| **无快照/模板** | 每次都是全新的沙箱 |
| **不支持 Windows** | 依赖 Linux 工具和传输语义 |
| **非全局 harness 运行时** | 只有 agent 的文件和命令执行在远程 |

### 10.2 安全性限制

| 限制 | 说明 |
|------|------|
| **控制状态共享 UID** | `.dsh-e2b` 控制文件与用户进程在同一 UID 下，`0700`/`0600` 模式无法完全隔离 |
| **数字进程身份可重用** | 无原子身份绑定，存在 PID/PGID 重用竞态条件 |
| **初始环境探针继承默认值** | E2B 合并环境变量，无法在枚举前清除未知凭据形状的名称 |
| **无信号事实** | E2B 不暴露信号信息，适配器请求的 SIGTERM/SIGKILL 可能被报告为退出码 |

### 10.3 性能和资源限制

| 限制 | 说明 |
|------|------|
| **SDK 在宿主机内存中保留完整输出** | E2B `CommandHandle.stdout/.stderr` 累积完整内容，无视适配器的有界尾部 |
| **私有状态存活至沙箱生命周期** | `.dsh-e2b` 下的进程目录和 spill 文件持续增长 |
| **全文件操作成本** | 覆盖和编辑需要完整读取文件到宿主机内存 |
| **每次操作有 E2B 控制器延迟** | 与本地操作相比，增加了显著的网络延迟 |

### 10.4 实现限制

| 限制 | 说明 |
|------|------|
| **读操作通过路径重开文件** | 并发路径替换在解析和流打开之间存在 TOCTOU 窗口 |
| **突变协调是宿主机进程本地的** | 另一个 harness 连接或命令可能竞争替换 |
| **没有 stdin-wait 检查** | PTY 后端无法确认前台进程是否真正在等待输入 |
| **跨宿主连接竞争** | 版本守卫不能跨不同 harness 实例工作 |

---

## 十一、与本地 Sandbox 的对比

| 维度 | 本地 Sandbox (09-sandbox.md) | E2B 远程沙箱 |
|------|------------------------------|-------------|
| **隔离层级** | 进程级（bwrap/Landlock/Seatbelt/ACL） | 机器级（远程 Linux VM） |
| **架构模式** | SandboxProvider + SandboxPolicy | 接缝替换（fs + subprocess） |
| **模式系统** | read-only → workspace-write → danger-full-access | 无模式系统（完全隔离） |
| **升级机制** | approveEscalation choreography | 不适用（无升级需求） |
| **审批集成** | 通过 ctx.approval | 不适用 |
| **文件沙箱** | 路径 containment 检查（FS_SANDBOX_DENIED） | 物理隔离（不同机器） |
| **命令沙箱** | ConfinedArgv + bwrap 包装 | 远程进程生成（HTTP/SSE） |
| **平台** | Linux/macOS/Windows | 仅 Linux |
| **延迟** | 极低（本地内核调用） | 较高（网络往返 + setup） |
| **配置复杂度** | 中等（策略和模式） | 低（API key + 超时） |
| **状态** | 完整支持，默认启用 | 实验性 POC，不在默认 composition |

---

## 十二、关键代码位置

| 文件 | 关键内容 |
|------|----------|
| `packages/e2b/e2b/src/index.ts` | `E2BRuntime` 服务 — SDK handle 生命周期、cwd/runtimeRoot 创建 |
| `packages/e2b/e2b/src/api-url.ts` | `e2bApiUrl()` — API URL 优先级派生（ENV→DEBUG→默认） |
| `packages/e2b/fs-e2b/src/index.ts` | `E2BFileSystem` — 完整 FileSystem 实现、原子写入、版本守卫 |
| `packages/e2b/subprocess-e2b/src/index.ts` | `E2BSubprocessRuntime` — spawn/spawnTerminal、输出模式、dispose |
| `packages/e2b/subprocess-e2b/src/process.ts` | `E2BSubprocessHandle` — bootstrap wrapper、输出编码、终止阶梯 |
| `packages/e2b/subprocess-e2b/src/terminal.ts` | `E2BTerminalHandle` — PTY 分配、会话管理、bootstrap 边界检测 |
| `packages/e2b/subprocess-e2b/src/environment.ts` | 环境探测、清洗、bootstrap 隔离、序列化 |
| `packages/e2b/subprocess-e2b/src/output.ts` | `E2BBase64Decoder`、`E2BOutputReader` — base64 传输和溢出管理 |
| `packages/e2b/subprocess-e2b/src/remote.ts` | `signalRemoteGroups`、`delay`、`commandOpts` — 共享控制辅助 |
| `packages/e2b/README.md` | E2B 包族映射、三包组合说明 |
| `packages/e2b/e2b/README.md` | E2BRuntime 文档 — POC 性质、临时沙箱、工作目录约定 |
| `packages/e2b/fs-e2b/README.md` | E2BFileSystem 文档 — 原子写入、版本守卫、已知限制 |
| `packages/e2b/subprocess-e2b/README.md` | E2BSubprocessRuntime 文档 — 环境隔离、终止阶梯、已知限制 |
| `.agents/notes/implemented/architecture/2026-07-28-portable-execution-world-consumers.md` | 架构决策 — 为何执行世界可以移动而不移动 harness |

---

## 十三、总结

E2B 远程沙箱实现了一套**完整的远程执行世界替换**，通过三个 Cordis 包的组合，将 agent 的文件操作和命令执行完全隔离到远程 Linux 沙箱中：

1. **`E2BRuntime`** — 管理共享 SDK handle 的单例所有者，延迟连接
2. **`E2BFileSystem`** — 实现原子写入、版本守卫、并发控制的远程文件系统
3. **`E2BSubprocessRuntime`** — 包含命令和终端的远程进程管理，具有完善的 bootstrap、输出传输和终止阶梯

其设计哲学体现了**深度防御**：环境完全显式、凭据绝对不泄露、进程组可证明终止、输出传输可验证完整性。但它目前仍是一个 POC——不支持重连、快照、Windows，也不在默认发布 composition 中。