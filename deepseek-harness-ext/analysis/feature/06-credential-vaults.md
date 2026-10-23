# Credential Vaults 分析

## 结论

**✅ 支持 (通用凭据管理系统)** — deepseek-harness **没有** 专门的 "MCP Credential Vault" 功能，但拥有完整的通用凭据管理缝线 (Credential Seam)，通过 `CredentialProvider` + `AuthorizationService` 提供类似 vault 的能力。MCP 通过配置中的 `!!js` 表达式和环境变量清洁机制与该缝线协作。

## 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-credentials` | `packages/credentials/credentials/` | Service Definition — 凭据提供接缝 |
| `@deepseek-ai/dsh-credentials-local` | `packages/credentials/credentials-local/` | Service Provider — 本地 YAML 文件存储实现 |
| `@deepseek-ai/dsh-authorization` | `packages/credentials/authorization/` | Service Definition — 授权流程管理 |
| `@deepseek-ai/dsh-authorization-ui` | `packages/credentials/authorization-ui/` | Consumer — UI 授权交互 |
| `@deepseek-ai/dsh-acp` | `packages/acp/acp/src/mcp.ts` | ACP → DSH MCP server 声明翻译 |

## 架构设计

### Credential Seam — 能力接缝模式

```
CredentialProvider (Service Definition)
  ├── CredentialRef — 环境变量式引用 (env-var pattern)
  ├── CredentialKey — 插件拥有的记录键 (<scope>/<id>)
  ├── ApiKeyRecord — API 密钥类型
  ├── GrantRecord — OAuth/Grant 类型 (opaque payload)
  └── Events — credentials/reference-updated, credentials/record-updated

AuthorizationService (Service Definition)
  ├── AuthorizationFlow — 注册如何获取凭据
  ├── AuthorizationSession — 交互式授权会话
  └── Methods — registerFlow, list, describe, cancel, begin
```

## CredentialProvider — 核心凭据服务

### 双键空间设计

deepseek-harness 的凭据系统使用**两个独立的键空间**：

```typescript
abstract class CredentialProvider extends Service {
  // ═══════════════════════════════════════════════
  // 键空间 1: CredentialRef — 环境变量式引用
  // ═══════════════════════════════════════════════
  // 模式: /^[A-Za-z_][A-Za-z0-9_]*$/
  // 用途: 配置中引用凭据，像环境变量一样
  // 示例: "OPENAI_API_KEY", "GITHUB_TOKEN"
  
  abstract resolve(ref: CredentialRef, signal?): Promise<string | undefined>
  abstract describe(ref: CredentialRef): Promise<CredentialInfo>
  abstract set(ref: CredentialRef, value: string): Promise<void>
  abstract unset(ref: CredentialRef): Promise<void>
  
  // ═══════════════════════════════════════════════
  // 键空间 2: CredentialKey — 插件记录键
  // ═══════════════════════════════════════════════
  // 模式: <scope>/<id>，如 "llm-pi-ai/openai-codex"
  // 用途: 插件拥有的结构化凭据记录
  // 示例: OAuth grant, 多字段 API 配置
  
  abstract readRecord(key: CredentialKey, signal?): Promise<CredentialRecord | undefined>
  abstract describeRecord(key: CredentialKey): Promise<CredentialInfo>
  abstract listRecords(scope: string): Promise<readonly CredentialKey[]>
  abstract modifyRecord(key: CredentialKey, mutate): Promise<void>
}
```

### CredentialRef — 环境变量式引用

```typescript
// 命名规则: POSIX 环境变量模式
type CredentialRef = string  // /^[A-Za-z_][A-Za-z0-9_]*$/

// 使用示例
// 在 YAML 配置中:
env:
  OPENAI_API_KEY: !!js ctx.credentials.resolve('OPENAI_API_KEY')
```

特点：
- 纯字符串凭据 (API keys, tokens)
- 名称遵循环境变量命名规则
- 通过 `ctx.credentials.resolve()` 读取
- UI 安全展示: `CredentialInfo { configured, source?, writable }` — 永不携带实际值

### CredentialKey — 插件记录键

```typescript
// 格式: <scope>/<id>
type CredentialKey = string  // e.g. "llm-pi-ai/openai-codex"

// 记录类型
type CredentialRecord = ApiKeyRecord | GrantRecord

// API Key 记录
interface ApiKeyRecord {
  kind: 'api-key'
  key?: string                          // 可选的 API key
  env?: Record<string, string>          // 相关环境变量
}

// Grant 记录 (opaque to seam)
interface GrantRecord {
  kind: 'grant'
  payload: unknown                      // 由具体 provider 解释
}
```

特点：
- 结构化凭据记录
- 按 scope 分组 (如 `llm-pi-ai/`, `mcp-github/`)
- 支持多种记录类型 (API key, OAuth grant)
- Grant payload 对 seam 不透明 — 由具体 provider 解释

### 安全特性

```typescript
// CredentialInfo — 安全的 UI 展示 (永不携带实际值)
interface CredentialInfo {
  configured: boolean     // 是否已配置
  source?: string         // 来源描述
  writable: boolean       // 是否可写
}
```

### 事件系统

```typescript
interface Events {
  // CredentialRef 更新 — 消费者应重新 resolve
  'credentials/reference-updated'(ref: CredentialRef): void
  
  // CredentialKey 记录更新 — commit 验证通过
  'credentials/record-updated'(key: CredentialKey): void
}
```

## Local Credential Store — credentials-local

### 存储实现

```typescript
// packages/credentials/credentials-local/src/index.ts
// 文件: $DSH_HOME/.credentials.yaml
// 权限: owner-only (chmod 600 on POSIX)
// 热重载: chokidar watcher
```

### 解析优先级 (高到低)

| 优先级 | 来源 | 可写 |
|--------|------|------|
| 1 | 启动环境 (`DEEPSEEK_API_KEY=… dsh`) | ❌ |
| 2 | 存储文件 (`$DSH_HOME/.credentials.yaml`) | ✅ |
| 3 | 项目 `.env` | ❌ |
| 4 | 用户 home `.env` | ❌ |

### 关键特性

- **Per-operation resolution** — 每次 `resolve()` 重新读取，不缓存 → 凭据轮换自动生效
- **跨进程写锁** — 序列化的 read-modify-write，防止并发写入冲突
- **Hot-reload** — chokidar 监听文件变更，自动刷新
- **安全权限** — POSIX 系统强制执行 chmod 600

## AuthorizationService — 授权流程管理

### 核心概念

AuthorizationService 管理**如何获取凭据**的交互式流程，类似 OAuth 但泛化为任意授权方法。

```typescript
abstract class AuthorizationService extends Service {
  // 注册授权流程
  abstract registerFlow(flow: AuthorizationFlow): () => void
  
  // 列出可用授权条目
  abstract list(): Promise<readonly AuthorizationEntry[]>
  
  // 描述特定条目
  abstract describe(key: CredentialKey): Promise<AuthorizationEntry | undefined>
  
  // 开始授权流程
  abstract begin(key: CredentialKey, methodId: string): Promise<AuthorizationSession>
  
  // 取消进行中的流程
  abstract cancel(key: CredentialKey): void
}
```

### AuthorizationFlow — 授权流程定义

```typescript
interface AuthorizationFlow {
  key: CredentialKey              // 关联的凭据键
  label: string                   // 人类可读标签
  methods: readonly AuthorizationMethod[]  // 可用的授权方法
  run(session: AuthorizationSession): Promise<void>  // 执行流程
}

interface AuthorizationMethod {
  id: string        // 方法标识
  label: string     // 人类可读名称 (如 "OAuth", "API Key", "Device Code")
}
```

### AuthorizationSession — 交互式会话

```typescript
interface AuthorizationSession {
  method: AuthorizationMethod     // 选中的授权方法
  signal: AbortSignal             // 取消信号
  
  // 通知 UI 状态变更
  notify(update: AuthorizationNotification): void
  
  // 向用户请求输入
  prompt(request: AuthorizationPromptRequest): Promise<string>
}

// 提示类型
type AuthorizationPrompt =
  | { type: 'text'; message: string }           // 文本输入
  | { type: 'secret'; message: string }         // 密码/密钥输入
  | { type: 'select'; message: string; options: readonly { label: string; value: string }[] }  // 选择

// 状态
type AuthorizationStatus = 'authorized' | 'cancelled'
```

### 授权流程生命周期

```
用户/系统触发授权
  → AuthorizationService.begin(key, methodId)
  → AuthorizationFlow.run(session)
    → session.prompt() — 请求用户输入 (token, 确认 URL 等)
    → session.notify() — 更新 UI 状态
    → 验证凭据
    → ctx.credentials.modifyRecord(key, ...) — 提交凭据
  → 'credentials/record-updated' 事件触发
  → AuthorizationService 验证 commit 完成
  → 返回 AuthorizationStatus
```

### 互斥约束

- **同一 key 同时只允许一个 attempt** — 重复 begin 会失败
- **Commit 验证** — 只有 `credentials/record-updated` 事件能验证授权成功
- **取消支持** — 通过 AbortSignal 传播

## MCP 与 Credential 的协作

### 1. 环境清洁 (stdio 传输)

```typescript
// packages/mcp/mcp-client/src/transport.ts
function scrubbedParentEnv(overrides?: Record<string, string>): Record<string, string> {
  const env = { ...process.env }
  
  // 清洁规则:
  // 1. 删除匹配 /KEY|PASSWORD|SECRET|TOKEN/i 的变量
  // 2. 删除所有 DSH_* 前缀变量
  // 3. 合并配置中的显式 overrides
  
  return { ...scrubbed, ...overrides }
}
```

这确保：
- Harness 自身的凭据不会泄漏到 MCP 子进程
- MCP server 需要的 token 必须通过配置显式注入

### 2. `!!js` 配置表达式

```yaml
# 从环境变量动态获取
env:
  GITHUB_TOKEN: !!js process.env.GITHUB_TOKEN

# 构造 Authorization header
headers:
  Authorization: !!js '`Bearer ${process.env.MCP_TOKEN}`'
```

`!!js` 是 YAML 自定义标签，在配置加载时执行 JS 表达式。这允许：
- 从环境变量动态注入凭据
- 构造复杂的 Authorization header
- 与外部 secret manager 集成

### 3. CredentialProvider 集成路径

虽然 MCP 配置不直接通过 `ctx.credentials.resolve()`，但可以通过以下方式集成：

```yaml
# 方案 A: 通过环境变量桥接
env:
  OPENAI_API_KEY: !!js process.env.OPENAI_API_KEY
  # OPENAI_API_KEY 可以在启动前通过 CredentialProvider.set() 设置

# 方案 B: 通过 !!js 表达式直接调用 (需要 host 支持)
headers:
  Authorization: !!js '`Bearer ${await ctx.credentials.resolve("MCP_TOKEN")}`'
```

### 4. 实际推荐模式

```
┌─────────────────────────────────────────────────────────┐
│  启动时:                                                  │
│  CredentialProvider.set("MCP_GITHUB_TOKEN", "...")       │
│                                                          │
│  配置中:                                                  │
│  env:                                                    │
│    GITHUB_TOKEN: !!js process.env.MCP_GITHUB_TOKEN       │
│                                                          │
│  或者:                                                    │
│  env:                                                    │
│    GITHUB_TOKEN: !!js ctx.credentials.resolve("...")     │
│                                                          │
│  MCP stdio 子进程:                                        │
│  scrubbedParentEnv() → 删除所有 KEY/TOKEN →               │
│  合并配置的 env → 子进程只看到显式注入的 token              │
└─────────────────────────────────────────────────────────┘
```

## AuthorizationService 的 UI 集成

```typescript
// packages/credentials/authorization-ui/
// 提供 UI 面的授权交互

// AuthorizationInteraction — UI 面接口
interface AuthorizationInteraction {
  // 通知 UI 更新
  notify(update: AuthorizationNotification): void
  
  // 向用户显示提示
  prompt(request: AuthorizationPromptRequest): Promise<string>
}

// UI 展示的授权条目
interface AuthorizationEntry {
  key: CredentialKey
  label: string
  methods: readonly AuthorizationMethod[]
  inFlight: boolean               // 是否有进行中的授权
}
```

## 与 Claude Code 的对比

| 特性 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| 凭据存储 | 环境变量 | CredentialProvider (双键空间) |
| OAuth 流程 | 部分 (内置 provider) | ✅ (AuthorizationService 泛化框架) |
| Secret 清洁 | 部分 | ✅ (scrubbedParentEnv) |
| 凭据 UI | 内置设置页 | ✅ (AuthorizationInteraction) |
| MCP 凭据传递 | env var | `!!js` 表达式 + env |
| 记录类型 | 简单 key-value | ✅ (ApiKeyRecord + GrantRecord) |
| 事件通知 | 无 | ✅ (reference-updated, record-updated) |
| 流程互斥 | 无 | ✅ (同一 key 一个 attempt) |

## 是否有专门的 "MCP Credential Vault"

**否** — deepseek-harness **没有** 专门针对 MCP 的 Credential Vault 功能。但是：

1. **CredentialProvider** 提供了通用的凭据 vault 能力：
   - 安全存储 (API key, OAuth grant)
   - 双键空间 (env-var style + plugin-scoped)
   - UI 安全展示 (CredentialInfo 不携带值)
   - 事件驱动更新

2. **AuthorizationService** 提供了交互式授权流程：
   - 多方法支持 (OAuth, API key, device code, etc.)
   - 会话管理 (prompt, notify, cancel)
   - 与 CredentialProvider 协作完成 commit

3. **MCP 集成** 通过间接方式：
   - `!!js` 配置表达式
   - 环境变量桥接
   - scrubbedParentEnv 防止泄漏

## 关键代码位置

| 文件 | 说明 |
|------|------|
| `packages/credentials/credentials/src/index.ts` | CredentialProvider 核心服务 |
| `packages/credentials/credentials/src/types.ts` | ApiKeyRecord, GrantRecord, CredentialRef, CredentialKey |
| `packages/credentials/authorization/src/index.ts` | AuthorizationService 核心服务 |
| `packages/credentials/authorization/src/types.ts` | AuthorizationFlow, AuthorizationSession |
| `packages/mcp/mcp-client/src/transport.ts` | scrubbedParentEnv 环境清洁 |
| `packages/mcp/mcp-client/README.md` | `!!js` 配置示例 |
