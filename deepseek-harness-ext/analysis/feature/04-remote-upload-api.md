# 远程上传接口分析 (Skill 和文件)

## 结论

| 上传类型 | 支持状态 | 方式 |
|----------|----------|------|
| 远程上传文件 | **✅ 完整支持** | HTTP API + Typert RPC |
| 远程上传 Skill | **⚠️ 部分支持** | 运行时注册 API (无直接远程文件上传 API) |

## 一、远程上传文件

### 1.1 HTTP 二进制上传

**端点**: `POST /api/session/uploadFileBinary`

```
POST /api/session/uploadFileBinary?sessionId=<session-id>&name=<filename>
Content-Type: application/octet-stream

<raw bytes>
```

**响应**:
```json
{
  "ok": true,
  "value": {
    "receiptId": "<file-upload-receipt-id>",
    "file": {
      "id": "<attachment-id>",
      "name": "example.pdf",
      "bytes": 12345,
      "mediaType": "application/pdf"
    }
  }
}
```

**关键文件**:
- `packages/client/file-upload/src/http-route.ts` — HTTP 路由处理
- `packages/client/file-upload/src/protocol.ts` — 路由常量
- `packages/client/file-upload/src/types.ts` — 请求/响应类型
- `packages/client/file-upload/src/index.ts` — FileUploads 服务

**实现特点**:
- 流式上传 — 不将完整文件加载到内存
- 认证 — 通过 Connection 的认证机制
- 背压控制 — `ReadableStream<Uint8Array>` 逐块读取
- 内容寻址存储 — 相同文件不重复存储

### 1.2 Typert RPC 上传 (Remote 接口)

FileUploads 服务同时暴露 Typert Remote 接口，支持通过 JSON-RPC over WebSocket 上传：

```typescript
// Base64 编码上传 (适用于小文件)
interface EncodedFileUploadRequest {
  readonly data: string   // base64 编码
  readonly name?: string
}
```

Attachment 服务暴露了 `@Remote('upload')` 方法：

```typescript
// 单次编码上传
@Remote('upload') upload(agent: Agent, request: EncodedFileUploadRequest, signal): Promise<FileUploadValue>

// 流式上传 (不聚合字节)
uploadStream({ sessionId, data: AsyncIterable<Uint8Array>, signal?, name? }): Promise<FileUploadValue>
```

这些 Remote 方法通过 Typert RPC gateway (`ctx.typertGateway`) 可达，支持浏览器客户端、SDK 客户端和 ACP 客户端。

### 1.3 工作区文件远程读取

通过 `WorkspaceFiles` Remote 服务，客户端可以远程读取工作区文件：

```typescript
// 远程文件读取
@Remote async read(scope, path, range, signal): Promise<WorkspaceFileText>
@Remote async readBytes(scope, path, range, signal): Promise<WorkspaceFileBytes>
@Remote async readAll(scope, path, signal): Promise<WorkspaceFileBytes>
@Remote async list(scope, path, signal): Promise<WorkspaceDirectoryListing>
```

### 1.4 SDK 上传接口

#### TypeScript SDK

```typescript
// packages/sdk/client/src/client.ts
// 通过 JSON-RPC 协议与 harness 通信
// 支持文件引用在 content_blocks 中传递
```

#### Python SDK

```python
# python/sdk/src/deepseek_harness/client.py
class HarnessClient:
    def session_prompt(self, session_id, content_blocks, ...):
        """content_blocks 可以包含文件附件"""
        payload = {"sessionId": session_id, "contentBlocks": content_blocks}
        return self.request("session/prompt", payload, ...)
```

## 二、远程上传 Skill

### 2.1 Skill 注册机制

deepseek-harness 的 Skill 系统采用 **Provider 注册模式**，不直接提供"上传一个 skill 文件"的远程 API。

#### SkillRegistry — 核心注册服务

```typescript
class SkillRegistry extends Service {
  // 注册 Provider
  registerProvider(create: (control: SkillProviderControl) => SkillProvider): () => void
  
  // 注册运行时 Skill
  register(skill: SkillRegistration): () => void
  
  // 查询
  async list(options?): Promise<SkillSummary[]>
  async get(name, options?): Promise<SkillDefinition | undefined>
  async snapshot(options?): Promise<SkillCatalogSnapshot>
}
```

#### SkillProvider 接口

```typescript
interface SkillProvider {
  readonly name: string
  
  // 列出可用 skill
  readonly list: (options: SkillLookupOptions) => 
    Promise<readonly SkillCandidate[] | SkillProviderObservation>
  
  // 加载 skill 内容
  readonly get: (candidate: SkillCandidate, options: SkillLookupOptions) => 
    Promise<SkillDefinition | undefined>
}
```

#### SkillRegistration — 运行时注册

```typescript
type SkillRegistration = Omit<SkillDefinition, 'invocation' | 'provider'> & {
  readonly invocation?: SkillInvocationPolicy
  readonly provider?: string
}

interface SkillDefinition {
  readonly name: string           // kebab-case 名称
  readonly description: string    // 简短描述
  readonly whenToUse?: string     // 使用时机
  readonly content: string        // Markdown 指令体
  readonly path?: string          // 磁盘路径 (可选)
  readonly metadata?: Readonly<Record<string, unknown>>  // 前置元数据
  readonly source: SkillSource    // 来源
  readonly invocation: SkillInvocationPolicy
}
```

### 2.2 Skill 来源 (SkillSource)

```typescript
type SkillSource = 
  | 'project-dsh'      // 项目 .dsh/ 目录
  | 'project-agents'   // 项目 AGENTS.md
  | 'runtime'          // 运行时注册
  | 'user-dsh'         // 用户 .dsh/ 目录
  | 'user-agents'      // 用户 AGENTS.md
  | 'custom'           // 自定义
  | 'bundled'          // 内置
  | (string & {})
```

### 2.3 如何实现远程 Skill 上传

虽然 deepseek-harness **没有内置的远程 skill 文件上传 API**，但可以通过以下方式实现：

#### 方案 A: 自定义 SkillProvider (推荐)

实现一个 `SkillProvider`，从远程源获取 skill：

```typescript
class RemoteSkillProvider implements SkillProvider {
  readonly name = 'remote-registry'
  
  async list(options): Promise<SkillCandidate[]> {
    // 从远程 API 获取 skill 列表
    const response = await fetch('https://skill-registry.example.com/api/skills')
    const skills = await response.json()
    return skills.map(skill => ({
      name: skill.name,
      description: skill.description,
      whenToUse: skill.whenToUse,
      source: 'custom',
      provider: this.name,
      rank: 100,
      locator: skill.id,
    }))
  }
  
  async get(candidate, options): Promise<SkillDefinition | undefined> {
    // 从远程 API 获取 skill 内容
    const response = await fetch(`https://skill-registry.example.com/api/skills/${candidate.locator}`)
    const skill = await response.json()
    return {
      name: skill.name,
      description: skill.description,
      content: skill.markdownContent,
      source: 'custom',
      provider: this.name,
      invocation: { modelInvocable: true, userInvocable: true },
    }
  }
}

// 注册
ctx.skills.registerProvider((control) => new RemoteSkillProvider(control))
```

#### 方案 B: 运行时注册 (适合动态注入)

通过 Cordis context 直接注册 skill：

```typescript
ctx.skills.register({
  name: 'my-custom-skill',
  description: 'A dynamically injected skill',
  content: '# Instructions\n...',
  source: 'custom',
})
```

#### 方案 C: 文件系统 + file-watch

将 skill 文件写入项目的 `.dsh/skills/` 目录，文件系统 provider 会自动发现。

### 2.4 Skill 层级与作用域

Skill 注册遵循 **ScopedLayers** 层级模型：

```
Global Layer (host-level)
  └── Scope Layer (per-agent/preset)
       └── Scope Layer (nested)
```

- 内层覆盖外层同名 skill
- 同层内按 `rank` 排序 (低者优先)
- `registerProvider()` 注册到调用 context 的 scope 层

## 三、Webhook 触发 — 间接远程输入

deepseek-harness 还支持通过 Webhook 触发新 Session，间接实现远程输入：

```typescript
interface WebhookSessionRequest {
  readonly workspacePath: string
  readonly title: string
  readonly prompt: string           // 初始 prompt
  readonly agentPreset: string
  readonly permissionPreset: string
  readonly model?: WebhookModelSelection
}
```

这允许外部系统 (GitHub, CI/CD 等) 通过 webhook 创建新的 agent session。

## 四、API 端点总结

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/api/session/uploadFileBinary` | POST | 二进制文件上传 | ✅ |
| `/api/present.open` | POST | 桌面打开文件 | ✅ |
| `/api/present.host` | GET | 获取 Host 信息 | ✅ |
| `/api` (JSON-RPC) | POST | Typert RPC 调用 | ✅ |
| WebSocket `/stream` | WS | 远程流式通信 | ✅ |

## 五、与 Claude Code 的对比

| 功能 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| HTTP 文件上传 | ✅ | ✅ |
| 流式上传 | ✅ | ✅ |
| 远程 Skill 上传 | ❌ (无直接 API) | ❌ (无直接 API, 但支持 Provider 模式) |
| Skill 运行时注册 | ✅ | ✅ |
| Webhook 触发 | ✅ | ✅ |
| 文件下载/读取 | ✅ | ✅ (WorkspaceFiles API) |
| 目录浏览 | ✅ | ✅ |
| 文件监听 | ✅ | ✅ (streaming) |
