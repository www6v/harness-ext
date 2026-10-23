# 文件输入/输出分析

## 结论

**✅ 支持** — deepseek-harness 同时支持对话中文件输入（上传）和文件输出（返回/展示）。

## 一、文件输入 (File Input)

### 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-attachment` | `packages/attachment/attachment/` | Service Definition — 附件存储接缝 |
| `@deepseek-ai/dsh-attachment-local` | `packages/attachment/attachment-local/` | Service Provider — 本地文件存储 |
| `@deepseek-ai/dsh-file-upload` | `packages/client/file-upload/` | HTTP 文件上传服务 |
| `@deepseek-ai/dsh-ui-attachment` | `packages/client/ui-attachment/` | UI 附件展示 |
| `@deepseek-ai/dsh-ui-input-trigger` | `packages/client/ui-input-trigger/` | UI 输入触发器 |

### 文件上传机制

#### 1. HTTP 二进制上传 (Raw-byte)

**端点**: `POST /api/session/uploadFileBinary?sessionId=<id>&name=<name>`

```typescript
// packages/client/file-upload/src/http-route.ts
export async function handleFileUploadHttp(service: FileUploads, request: Request): Promise<Response>
```

- Content-Type: `application/octet-stream`
- 请求体: 原始字节流 (streaming)
- 返回: JSON `FileUploadValue { receiptId, file }`
- 支持大文件流式上传 (backpressure-aware)

#### 2. Base64 编码上传 (Remote fallback)

```typescript
interface EncodedFileUploadRequest {
  readonly data: string   // canonical base64 编码
  readonly name?: string  // 可选显示名
}
```

#### 3. 图片上传

```typescript
interface SaveImageAttachment {
  data: Uint8Array
  mediaType: string
  name?: string
}
```

图片上传会经过：
- 媒体类型验证
- 字节大小限制 (`maxImagesPerMessage`, `maxMessageImageBytes`)
- 规范化 (方向修正、尺寸限制)
- 内容寻址存储

### AttachmentStore — 附件服务

```typescript
abstract class AttachmentStore extends Service {
  abstract readonly imageLimits: ImageAttachmentLimits
  
  // 图片
  abstract validateImage(input: SaveImageAttachment): Promise<void>
  async saveImages(inputs): Promise<readonly ImageAttachmentRef[]>
  abstract saveImage(input): Promise<ImageAttachmentRef>
  abstract readImage(ref, signal?): Promise<StoredImageAttachment>
  
  // 文件
  admitEncodedFile(input: EncodedFileAttachment): Promise<FileAttachmentRef>
  saveFile(input: SaveFileAttachment): Promise<FileAttachmentRef>
  saveFileStream(input: SaveFileStreamAttachment): Promise<FileAttachmentRef>
  async *readFileStream(ref, signal?): AsyncIterable<Uint8Array>
  
  // Prompt 内容准入
  async admitPromptContent(content): Promise<AdmittedPromptContentPart[]>
  
  // 主机路径 (用于文件访问)
  imageHostPath(ref): string | undefined
  fileHostPath(ref): string | undefined
  
  // 模型请求投影
  readImageRequest(ref, policy, signal?): Promise<RequestImageAttachment>
}
```

### Prompt 内容类型

对话中的 prompt 可以包含多种内容部分：

```typescript
type AttachmentAdmissionPart =
  | { type: 'text'; text: string }           // 文本
  | { type: 'image'; ... }                   // 图片 (编码)
  | { type: 'file'; attachment: FileAttachmentRef }  // 文件引用

type AdmittedPromptContentPart =
  | { type: 'text'; text: string }
  | { type: 'image'; attachment: ImageAttachmentRef }  // 持久化引用
  | { type: 'file'; attachment: FileAttachmentRef }
```

### 上传流程

```
用户选择文件
  → FileUploadFetch (HTTP POST /api/session/uploadFileBinary)
  → FileUploads.uploadStream()
  → AttachmentStore.saveFileStream()
  → 返回 FileUploadValue { receiptId, file: FileAttachmentRef }
  → receiptId 绑定到 prompt 内容
  → admitPromptContent() 替换为持久化引用
  → 写入 Session 日志
```

## 二、文件输出 (File Output)

### 核心包

| 包名 | 路径 | 职责 |
|------|------|------|
| `@deepseek-ai/dsh-ui-deliverables` | `packages/client/ui-deliverables/` | 产出文件展示 |
| `@deepseek-ai/dsh-tool-present` | `packages/tool/present/` | 文件展示工具 |
| `@deepseek-ai/dsh-api-workspace-files` | `packages/api/workspace-files/` | 工作区文件远程读取 |

### Present 工具 — 显式文件交付

除了自动追踪文件变更外，模型可以使用 `present` 工具显式声明交付文件：

```typescript
// packages/fs/tool-present/
// 模型调用: present({ files: [{ path: "out/report.html", description: "最终报告" }] })
```

- `write`/`edit` 等工具自动填充 "Files changed" 行
- `present` 工具用于显式声明最终文件（包括通过 Bash 创建的文件）
- 显示运行中/已交付/失败/中断状态

### 内联代码引用

模型输出的 prose 中的内联代码引用（如 `out/report.html`）会自动变为可点击链接，在 Sidebar 预览中打开文件。

### Deliverables — 产出文件

当 agent 创建或修改文件时，通过 `presented` 事件声明：

```typescript
// packages/client/ui-deliverables/src/presented.ts
interface PresentedFile {
  path: string
  description?: string
}

interface PresentedData {
  turn: number
  callId: ToolCallId
  files: PresentedFile[]
}
```

#### 文件操作

```typescript
type PresentedAction = 'open' | 'reveal'
```

- **open** — 在 Host 桌面打开文件 (`/api/present.open`)
- **reveal** — 在文件管理器中显示文件

#### URL 构建

```typescript
function presentedFileUrl(sessionId, seq, index): string
// → /api/present.open?sessionId=...&seq=...&index=...
```

### Workspace Files API — 远程文件读取

```typescript
class WorkspaceFiles extends TypertRemoteService {
  // 文本分页读取
  @Remote async read(scope, path, range, signal): Promise<WorkspaceFileText>
  
  // 二进制字节读取
  @Remote async readBytes(scope, path, range, signal): Promise<WorkspaceFileBytes>
  
  // 完整文件读取
  @Remote async readAll(scope, path, signal): Promise<WorkspaceFileBytes>
  
  // 相关文件读取
  @Remote async readRelated(scope, path, relativePath, signal): Promise<WorkspaceFileBytes>
  
  // 文件状态
  @Remote async stat(scope, path, signal): Promise<WorkspaceFileStat>
  
  // 目录列表
  @Remote async list(scope, path, signal): Promise<WorkspaceDirectoryListing>
  
  // 文件变更监听
  @Remote({ mode: 'stream' }) changes(scope, signal): AsyncIterable<WorkspaceFileWatchFrame>
}
```

### 配置限制

```typescript
interface Config {
  readonly maxBytes: number       // 单页/窗口字节上限 (默认 2MB)
  readonly maxFileBytes: number   // 完整文件上限 (默认 32MB)
  readonly maxLines: number       // 单页行数上限 (默认 5000)
  readonly maxEntries: number     // 目录条目上限 (默认 2000)
}
```

## 三、Python SDK 中的文件交互

Python SDK (`python/sdk/src/deepseek_harness/client.py`) 通过 JSON-RPC 与 harness 交互：

```python
def session_prompt(self, session_id, content_blocks, ...):
    """发送 prompt，content_blocks 可以包含文件附件引用"""
```

## 总结

| 能力 | 支持方式 | 关键 API |
|------|----------|----------|
| 文件上传 (文本) | HTTP POST octet-stream | `/api/session/uploadFileBinary` |
| 文件上传 (图片) | Base64 编码 | `AttachmentStore.saveImages()` |
| 文件上传 (大文件) | 流式上传 | `AttachmentStore.saveFileStream()` |
| 文件下载 (文本) | 远程分页读取 | `WorkspaceFiles.read()` |
| 文件下载 (二进制) | 远程字节读取 | `WorkspaceFiles.readBytes()` / `readAll()` |
| 文件展示 | presented 事件 | `/api/present.open` |
| 目录浏览 | 远程目录列表 | `WorkspaceFiles.list()` |
| 文件监听 | WebSocket stream | `WorkspaceFiles.changes()` |
