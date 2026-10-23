# MCP (Model Context Protocol) 分析

## 结论

**✅ 完整支持** — deepseek-harness 通过 `@deepseek-ai/dsh-mcp-client` 插件完整支持 MCP (Model Context Protocol)，提供 stdio 和 streamable-http 两种传输方式，具备自动重连、工具热同步、图片内容桥接等企业级特性。

## 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-mcp-client` | `packages/mcp/mcp-client/` | MCP 客户端桥接插件 — 配置、连接、工具同步、执行 |

## 架构设计

### 整体架构

```
MCP Server (外部)
  ↕ stdio / streamable-http
Connection Supervisor (connection.ts)
  ↕ @modelcontextprotocol/sdk Client
Tool Bridge (tools.ts)
  ↕ ToolRuntime.register()
模型工具列表 (mcp__<serverName>__<toolName>)
```

### 配置模型

每个 MCP server 对应一条插件配置：

```typescript
// Stdio 传输 (本地进程)
interface StdioConfig {
  transport: 'stdio'
  serverName: string              // [A-Za-z0-9_-]{1,32}，工具命名空间
  command: string                 // 可执行文件
  args?: string[]                 // 命令行参数
  env?: Record<string, string>    // 额外环境变量 (合并到 scrubbed env 上)
  cwd?: string                    // 工作目录
  toolCallTimeoutMs?: number      // 默认 60,000ms
  failOnStartupError?: boolean    // 默认 false
  reconnect?: ReconnectPolicy
}

// Streamable HTTP 传输 (远程服务)
interface StreamableHttpConfig {
  transport: 'streamable-http'
  serverName: string
  url: string                     // 端点 URL
  headers?: Record<string, string> // 额外请求头
  toolCallTimeoutMs?: number
  failOnStartupError?: boolean
  reconnect?: ReconnectPolicy
}
```

### 配置示例

```yaml
# Stdio — 本地 GitHub MCP server
- id: mcp-github
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: github
    transport: stdio
    command: npx
    args: ['-y', '@modelcontextprotocol/server-github']
    env:
      GITHUB_TOKEN: !!js process.env.GITHUB_TOKEN

# Streamable HTTP — 远程 MCP server
- id: mcp-web
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: web
    transport: streamable-http
    url: http://localhost:3000/mcp
    headers:
      Authorization: !!js '`Bearer ${process.env.MCP_TOKEN}`'
```

## 关键模块

### 1. 插件入口 (index.ts)

```typescript
// apply() 函数 — 插件激活
async function apply(ctx, config): Promise<void> {
  // 1. 解析 reconnect policy
  // 2. 在当前 scope 内保留 serverName 命名空间
  // 3. 启动连接 supervisor
  // 4. 等待初始连接 + 工具发现完成
  // 5. 如果 failOnStartupError: true，初始失败会阻止插件激活
}
```

**关键设计**:
- `serverName` 在同一注册 scope 内唯一 — 重复会报错
- 不同 Agent scope 可复用同一 serverName (工具/传输隔离)
- 支持 HMR — 修改配置后原地重载连接

### 2. 连接管理 (connection.ts)

```typescript
// 连接 supervisor — 管理客户端生命周期
class ConnectionSupervisor {
  // 重连策略
  readonly policy: ReconnectPolicy
  
  // 启动
  async start(): Promise<void>
  
  // 处理工具变更通知
  onToolsChanged(): void
  
  // 断开重连
  onDisconnect(): void
  
  // 释放
  async dispose(): Promise<void>
}

interface ReconnectPolicy {
  enabled: boolean           // 默认 true
  initialDelayMs: number     // 默认 500ms
  maxDelayMs: number         // 默认 30,000ms
  maxAttempts: number        // 默认 10
}
```

**重连机制**:
- **指数退避** — 延迟从 `initialDelayMs` 翻倍递增，上限 `maxDelayMs`
- **尝试预算** — 每次 outage 最多 `maxAttempts` 次连续失败
- **稳定性窗口** — 连接保持超过 `maxDelayMs` 后重置尝试预算
- **工具保留** — 断开期间最后已知的工具列表仍保留 (调用会失败直到恢复)
- **预算耗尽** — 达到上限后工具被注销，需手动重载配置或重启

**工具热同步**:
- 监听 `notifications/tools/list_changed` 通知
- 自动触发工具列表重新同步
- 同步采用 **原子代际切换** (two-phase sync) — 获取失败保留旧代，注册冲突回滚整个新代

### 3. 传输层 (transport.ts)

```typescript
// 传输工厂
function createTransport(config): Transport {
  switch (config.transport) {
    case 'stdio':
      return new StdioClientTransport({
        command: config.command,
        args: config.args,
        env: scrubbedParentEnv(config.env),  // 环境清洁
        cwd: config.cwd,
      })
    case 'streamable-http':
      return new StreamableHTTPClientTransport({
        url: config.url,
        headers: config.headers,
      })
  }
}
```

**环境清洁 (stdio)**:

```typescript
function scrubbedParentEnv(overrides?: Record<string, string>): Record<string, string> {
  // 1. 从父进程 env 开始
  // 2. 删除匹配 /KEY|PASSWORD|SECRET|TOKEN/i 的变量
  // 3. 删除所有 DSH_* 前缀变量
  // 4. 合并配置中的 overrides (显式覆盖优先)
  return { ...scrubbed, ...overrides }
}
```

这防止了 harness 自身的凭据泄漏到 MCP 子进程，同时允许配置显式注入所需的 token。

### 4. 工具桥接 (tools.ts)

```typescript
// 工具同步 — 原子代际切换
async function syncTools(client, registry, serverName): Promise<void> {
  // Phase 1: 获取 — 分页拉取 tools/list
  const tools = await fetchAllTools(client)
  
  // Phase 2: 切换 — 注册新代，注销旧代
  const generation = tools.map(tool => ({
    name: publicToolName(serverName, tool.name),
    description: tool.description,
    inputSchema: tool.inputSchema,
    executor: createExecutor(client, tool.name),
  }))
  
  registry.swapGeneration(serverName, generation)
}

// 工具命名 — 确定性映射
function publicToolName(serverName: string, rawName: string): string {
  // 1. 规范化: mcp__<serverName>__<rawName>
  // 2. 字符过滤: 只保留 [A-Za-z0-9_-]
  // 3. 长度限制: 最大 64 字符
  // 4. 如果规范化丢失信息 → 追加 SHA-256 hash (12 hex chars)
  // 5. 保证: 不同的 (serverName, rawName) → 不同的 public name
  return normalized
}

// 工具执行 — MCP tools/call
function createExecutor(client, rawToolName) {
  return async (args, signal) => {
    // 调用 MCP server (注意: raw name 发送给 server，public name 不发送)
    const result: McpResult = await client.callTool({
      name: rawToolName,
      arguments: args,
      signal,
      timeout: config.toolCallTimeoutMs,
    })
    
    // 内容投影 — 将 MCP content blocks 转为 Native 格式
    return projectContent(result.content, capabilities)
  }
}
```

**McpResult 类型**:

```typescript
interface McpResult {
  content: JsonValue[]                // MCP 标准内容块
  structuredContent?: Structured      // 可选结构化内容 (outputSchema)
}
```

**内容投影**:

| MCP Content Type | 投影结果 |
|------------------|----------|
| `text` | 直接文本 |
| `image` (PNG/JPEG/WebP/GIF) | 图片附件 (需模型支持 + attachment 功能开启) |
| `resource_link` | 文本: `[name](uri)` |
| `audio` | 诊断文本 (暂不支持) |
| `resource` (嵌入) | 诊断文本 (暂不支持) |

**图片处理流程**:

```
MCP image content block
  → base64 解码
  → 媒体类型验证
  → 字节大小验证
  → 批量验证 (所有图片一起验证)
  → AttachmentStore 持久化
  → 在对话中以附件引用展示
```

如果图片被拒绝 (不支持格式、大小超限、模型不支持图片)，投影为诊断文本而非静默丢弃。

## 工具命名规则

### 确定性命名合约

```
mcp__<serverName>__<rawName>
```

- `serverName`: 配置指定的命名空间 `[A-Za-z0-9_-]{1,32}`
- `rawName`: MCP server 提供的原始工具名
- 总长度限制: ≤ 64 字符
- 字符集: `[A-Za-z0-9_-]`
- 如果规范化有损 (如 rawName 含特殊字符)，追加 12 位 SHA-256 hash 确保唯一性

### 命名不变量

1. **Raw name 是唯一 wire name** — `tools/call` 始终发送 rawName，永不发送 publicName
2. **PublicName 是纯函数** — `f(serverName, rawName)` 确定性生成
3. **代际稳定** — 重连后相同工具集产生相同 publicName，session 历史和权限规则不受影响
4. **冲突检测** — 两个 server 同名工具共存 (`mcp__github__search` vs `mcp__web__search`)；同一 server 内重复工具名会拒绝整个工具列表

## 事件与监控

```typescript
interface Events {
  'mcp/server-connecting'(serverName: string): void
  'mcp/server-connected'(serverName: string): void
  'mcp/server-disconnected'(serverName: string, reason: string): void
  'mcp/server-reconnecting'(serverName: string, attempt: number): void
  'mcp/tools-changed'(serverName: string, toolCount: number): void
  'mcp/server-error'(serverName: string, error: Error): void
}
```

## 已知限制

| 限制 | 说明 |
|------|------|
| 仅桥接工具 | MCP Resources 和 Prompts 不支持 (无 harness consumer) |
| 启动/发现超时继承 SDK | 无法配置连接超时，继承 MCP SDK 的 60 秒默认 |
| HTTP 重连由 SDK 驱动 | Streamable HTTP 的传输级重连是 SDK 行为，非 supervisor 管理 |
| 仅图片支持持久化 | Audio 和嵌入 Resource 仅保留诊断文本 |
| outputSchema 子集 | 不支持的 schema 词汇回退到无约束 JsonValue |
| task-required 工具不桥接 | 需要 task-based 执行扩展的工具抛出异常 |

## MCP 远程上传与注册能力分析

### 结论

| 方式 | 支持状态 | 说明 |
|------|----------|------|
| 远程 HTTP API 上传 MCP 配置 | **❌ 不支持** | 没有 `POST /api/mcp/servers` 这类端点 |
| 远程 HTTP API 注册 MCP 服务器 | **❌ 不支持** | 没有专门的 MCP 配置管理 API |
| 通过 Settings Remote API 管理 | **❌ 不支持** | Settings 系统管理键值命名空间，不管理插件组合 |
| 编辑组合文件注册 MCP | **✅ 支持** | 模型通过文件工具编辑 `cordis.yml` 或 `agent.cordis.yml` |
| Profile 补丁添加插件 | **✅ 支持** | 用户级 `~/.dsh/` 补丁可覆盖/追加插件行 |
| Dynamic Cordis Plugin 运行时扩展 | **⚠️ 间接** | 可定义运行时插件但不直接支持 MCP 配置 |
| Agent Preset 复制/编辑 | **✅ 支持** | `ctx.agentPresets.copy()` + 编辑组合文件 |

### 一、MCP 服务器的配置方式

MCP 服务器**不是通过远程 API 动态注册**的，而是作为 Cordis 插件行静态配置在组合文件中。

#### 1.1 组合文件 (cordis.yml)

MCP 服务器作为 `@deepseek-ai/dsh-mcp-client` 的实例配置在 `cordis.yml` 中：

```yaml
# 项目级 cordis.yml 或用户级 ~/.dsh/cordis.yml
- id: mcp-github
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: github
    transport: stdio
    command: npx
    args: ['-y', '@modelcontextprotocol/server-github']
    env:
      GITHUB_TOKEN: !!js process.env.GITHUB_TOKEN

- id: mcp-remote
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: remote-api
    transport: streamable-http
    url: https://api.example.com/mcp
    headers:
      Authorization: !!js '`Bearer ${process.env.API_TOKEN}`'
```

#### 1.2 Agent Preset 组合文件 (agent.cordis.yml)

MCP 配置可以放在 Agent Preset 的组合中：

```yaml
# agent preset 的 agent.cordis.yml
- id: mcp-filesystem
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: fs
    transport: stdio
    command: npx
    args: ['-y', '@anthropic-ai/mcp-server-filesystem']
```

MCP 插件注册到调用 context 的 scope 层（见 `packages/mcp/mcp-client/src/index.ts:154-168`），因此：
- 放在 **host 组合**中 → 全局可见
- 放在 **agent preset** 中 → 仅该 preset 的 session 可见，需关注 isolate realm 规则

### 二、远程注册 MCP 的等效方式

#### 2.1 模型通过文件工具编辑组合文件（最直接）

模型可以使用 `write`/`edit` 工具直接修改组合文件来添加 MCP 服务器配置：

- **项目级**：编辑 `cordis.yml`
- **用户级**：编辑 `~/.dsh/cordis.yml` 或 Profile 补丁
- **Preset 级**：复制 shipped preset → 编辑 `agent.cordis.yml`

这需要文件沙箱权限（如果目标在 workspace 之外），但本质上是远程编辑操作。

#### 2.2 Agent Preset 复制与定制

`ctx.agentPresets` 服务提供编程式 preset 管理：

```typescript
// 通过 cordis_mount 动态插件调用（模型可用）
ctx.agentPresets.copy(from: 'standard', id: 'my-mcp-preset', name?: 'My Preset')
ctx.agentPresets.read(id)       // 读取组合文件文本
ctx.agentPresets.list()          // 列出所有 preset
ctx.agentPresets.standingKeyFor(id)  // 挂载验证
```

模型可以：
1. 复制一个现有 preset（如 `standard`）
2. 编辑复制出的 `agent.cordis.yml`，添加 MCP 行
3. 运行 `standingKeyFor()` 验证组合正确性
4. 新 preset 即可在 session 创建时选用

这通过 `tool-cordis` 的 `cordis_mount` 机制实现，且修改持久化到磁盘。

#### 2.3 Profile 补丁系统

`app-boot` 支持用户级补丁层（`~/.dsh/` 下的 `cordis.patch.yml`），可以：

- 向现有组合**追加**插件行（如 MCP server）
- 覆盖 (override)、前置 (prepend)、后置 (append) 现有配置
- 模型可通过文件工具编辑这些补丁文件

#### 2.4 Dynamic Cordis Plugin（运行时，不持久化）

`tool-cordis` 提供的 `cordis_define`/`cordis_run` 工具允许模型在运行时定义和执行动态插件：

```javascript
// 模型通过 cordis_define 提交的代码
return {
  name: 'my-runtime-plugin',
  inject: ['tools'],
  apply(ctx) {
    // 注册自定义工具或服务
    ctx.tools.register(someTool)
  },
}
```

**限制**：
- Dynamic Plugin 定义的是 JavaScript 代码，不是 MCP 服务器配置
- 无法直接通过 Dynamic Plugin 注册一个 MCP 客户端实例
- 所有 Dynamic Plugin 仅在当前进程中存活，重启后消失
- 可以间接实现类似效果（在 apply 中手动创建 MCP 连接），但不推荐

#### 2.5 CLI 插件管理命令

```bash
# 安装/卸载 Profile Bundle（如 subagent providers）
dsh plugin --profile <name> add @deepseek-ai/dsh-subagent-codex
dsh plugin --profile <name> remove @deepseek-ai/dsh-subagent-codex
```

这对 subagent provider bundle 有效，但**不适用于 MCP 服务器**的添加（MCP 配置仍需编辑组合文件）。

### 三、为什么没有远程 MCP 上传 API

1. **架构设计**：MCP 服务器是 Cordis 组合的一部分，组合文件是静态声明式的。整个系统的配置管理哲学是"组合文件即配置"，而非"远程 API 动态注册"。

2. **安全边界**：Stdio 传输的 MCP 服务器需要指定可执行文件路径和命令，允许远程 API 直接添加会引入严重的安全风险。

3. **持久化需求**：MCP 配置需要在进程重启后仍然存在，因此必须写入文件系统。

4. **替代方案充足**：通过文件编辑、preset 复制、profile 补丁等方式可以完全覆盖远程注册的需求。

### 四、与 Claude Code 的对比更新

| 特性 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| MCP 远程上传 API | ❌ | ❌ |
| MCP 配置管理方式 | 编辑 `.claude/mcp.json` / settings | 编辑 `cordis.yml` / `agent.cordis.yml` |
| 模型可编辑 MCP 配置 | ✅ (通过文件工具) | ✅ (通过文件工具) |
| 用户级 MCP 配置 | ✅ (`~/.claude/mcp.json`) | ✅ (`~/.dsh/cordis.yml` 补丁) |
| 项目级 MCP 配置 | ✅ (`.claude/mcp.json`) | ✅ (`cordis.yml` 行) |
| Agent 级 MCP 隔离 | ✅ (project-scoped) | ✅ (agent preset scope 隔离) |
| MCP 配置热重载 | 部分 | ✅ (HMR 原地重载) |
| Dynamic Plugin 运行时扩展 | ✅ (Codex plugins) | ✅ (Dynamic Cordis Plugin) |

## 与 Claude Code 的对比

| 特性 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| MCP 支持 | ✅ | ✅ |
| Stdio 传输 | ✅ | ✅ |
| HTTP/SSE 传输 | ✅ | ✅ (Streamable HTTP) |
| 自动重连 | ✅ | ✅ (指数退避 + 尝试预算) |
| 工具热同步 | ✅ | ✅ (原子代际切换) |
| 图片内容 | ✅ | ✅ (通过 AttachmentStore) |
| Resources/Prompts | ❌ | ❌ |
| 工具命名 | `mcp__<server>__<tool>` | `mcp__<server>__<tool>` (相同模式) |
| 凭据清洁 | 部分 | ✅ (scrubbedParentEnv) |
| 配置热重载 | 部分 | ✅ (HMR 原地重载) |
| MCP 远程上传 API | ❌ | ❌ |
| MCP 远程注册 API | ❌ | ❌ |
| 模型可编辑 MCP 配置 | ✅ (编辑 settings/mcp.json) | ✅ (编辑 cordis.yml) |
| 用户级 MCP 配置文件 | ✅ (`~/.claude/mcp.json`) | ✅ (`~/.dsh/cordis.yml` 补丁) |
| 项目级 MCP 配置文件 | ✅ (`.claude/mcp.json`) | ✅ (`cordis.yml`) |
| Agent 级 MCP 作用域隔离 | ✅ | ✅ (agent preset scope) |

## 关键代码位置

| 文件 | 说明 |
|------|------|
| `packages/mcp/mcp-client/src/index.ts` | 插件入口 — Config schema, serverName 保留, scope 层注册, 激活等待 |
| `packages/mcp/mcp-client/src/connection.ts` | 连接 supervisor — 客户端代际, 重连策略, 尝试预算 |
| `packages/mcp/mcp-client/src/tools.ts` | 工具桥接 — 发现, 命名, 代际切换, 执行, 图片投影 |
| `packages/mcp/mcp-client/src/transport.ts` | 传输工厂 — stdio 清洁环境, Streamable HTTP |
| `packages/mcp/mcp-client/README.md` | 完整用户文档 + 实现设计说明 |
| `packages/extensions/tool-cordis/src/prompt.ts` | Dynamic Cordis Plugin 模型指导 + cordis_define/run 工具说明 |
| `packages/extensions/cordis-host-runner/src/index.ts` | Dynamic Plugin 生命周期管理 (define/run/stop/undefine) |
| `packages/boot/app-boot/src/index.ts` | 组合引导 — cordis.yml 加载, Profile 补丁, user patches |
| `packages/preset/agent-presets/src/index.ts` | Agent Preset 服务 — copy/read/list/standingKeyFor |
| `packages/preset/agent-presets/presets/cordis/skills/editing-cordis-compositions/SKILL.md` | 组合编辑 skill — 完整指导 |
