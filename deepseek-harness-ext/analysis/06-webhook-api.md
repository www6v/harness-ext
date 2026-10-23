# Webhook 接口

## 概述

DeepSeek Harness 支持通过 HTTP Webhook 接收外部事件（如 GitHub 事件），并根据配置的规则自动触发 Agent 会话。

- **协议**: HTTP POST
- **认证**: HMAC-SHA256 签名验证
- **源码位置**: `packages/webhook/`
- **包名**:
  - `@deepseek-ai/dsh-webhook` — Webhook 运行时框架
  - `@deepseek-ai/dsh-webhook-github` — GitHub Webhook 适配器

## 架构

```
外部系统 (GitHub)
  → HTTP POST（签名验证）
  → WebhookRuntime（规则匹配）
  → 创建/触发 Agent 会话（fire-and-forget）
```

## GitHub Webhook 端点

### 配置

在 `cordis.yml` 中配置 Webhook 端点：

```yaml
webhook-github:
  source: github              # 来源标识
  path: /webhooks/github      # HTTP 路径（可自定义）
  secretEnv: GITHUB_WEBHOOK_SECRET  # 凭据引用
  maxBodyBytes: 10485760      # 最大请求体大小（10MB）
```

### 请求格式

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **Content-Type** | `application/json`（UTF-8） |
| **路径** | 配置中指定的 `path` |

### 必需请求头

| 头名称 | 说明 |
|--------|------|
| `X-Hub-Signature-256` | HMAC-SHA256 签名（`sha256=<hex>`） |
| `X-GitHub-Delivery` | 投递 UUID |
| `X-GitHub-Event` | 事件类型（如 `push`、`pull_request`） |
| `Content-Type` | 必须为 `application/json` |

### 签名验证

```
signature = HMAC-SHA256(secret, request_body)
expected = "sha256=" + hex(signature)
```

签名使用配置的 `secretEnv` 凭据引用解析的共享密钥计算。

### 响应码

| 状态码 | 说明 |
|--------|------|
| `202 Accepted` | 成功接收并分发 |
| `400 Bad Request` | 缺少必需头、无效 JSON、请求体过大 |
| `401 Unauthorized` | 签名验证失败 |
| `405 Method Not Allowed` | 非 POST 方法 |
| `415 Unsupported Media Type` | Content-Type 不正确 |
| `503 Service Unavailable` | Webhook 运行时未就绪 |

### 请求体

标准 GitHub Webhook payload，例如 `push` 事件：

```json
{
  "ref": "refs/heads/main",
  "repository": {
    "full_name": "owner/repo",
    "clone_url": "https://github.com/owner/repo.git"
  },
  "commits": [...],
  "pusher": { "name": "username" }
}
```

## Webhook 规则

### 规则注册

插件通过 `ctx.webhookRuntime.register()` 注册规则：

```typescript
interface WebhookRule<K> {
  id: string                    // 规则唯一标识
  kind: string                  // 事件类型匹配
  run(delivery: VerifiedWebhookDelivery<K>, signal: AbortSignal):
    WebhookSessionRequest | null  // 返回 null 表示不处理
}

interface VerifiedWebhookDelivery<K> {
  kind: string                  // 事件类型
  source: string                // 来源标识
  deliveryId: string            // 投递 UUID
  event: K                      // 解析后的事件 payload
  receivedAt: number            // 接收时间戳
}

interface WebhookSessionRequest {
  workspacePath: string         // 工作区路径
  title: string                 // 会话标题
  prompt: string                // Agent 提示
  agentPreset?: string          // Agent 预设
  permissionPreset?: string     // 权限预设
  model?: ModelSelection        // 模型选择
}
```

### Fire-and-Forget

Webhook 分发是 fire-and-forget 的：
- 成功验证后立即返回 202
- 规则匹配和会话创建在后台异步执行
- 会话创建失败不影响 HTTP 响应

## 其他 Webhook 来源

Webhook 框架是来源无关的，可以扩展支持其他来源：

- **GitHub**: 已实现（`webhook-github`）
- **自定义来源**: 通过实现新的适配器插件

## 安全建议

1. **使用强随机密钥**:  webhook secret 应为至少 32 字节的随机字符串
2. **HTTPS**: 生产环境必须使用 HTTPS
3. **IP 白名单**: 可选地限制来源 IP（GitHub webhook 来源 IP 范围可查）
4. **超时**: 合理设置 `maxBodyBytes` 防止内存耗尽
