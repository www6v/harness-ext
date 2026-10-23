# Docker 部署远程访问修复：HTTP 403 与 Settings 不可用

## 问题背景

将 DeepSeek Harness 通过 Docker 部署到远程服务器 `111.229.26.170` 后，通过公网 IP 访问 `http://111.229.26.170:3080` 时出现两个问题：

1. **API 端点返回 HTTP 403**：浏览器访问 `/api/llm/listProviders` 和 `/api/agentPresets/list` 等接口时被拒绝
2. **Settings 页面报错**："加载提供方目录失败: settings are unavailable in this browser"

## 根因分析

### 问题 1：HTTP 403 — Trust Fence 拒绝非 loopback Host

DeepSeek Harness 的 API 有一层 **DNS 重绑定防御（trust fence）**，在 `api-request-trust.ts` 中实现：

```typescript
// packages/client/connection/src/api-request-trust.ts
function isTrustedApiRequest(host: string, trustedHosts: Set<string>): boolean {
  if (isLoopbackHostname(host)) return true
  for (const trusted of trustedHosts) {
    if (isTrustedAuthority(host, trusted)) return true
  }
  return false
}
```

当浏览器从公网 IP 访问时，`Host` 头为 `111.229.26.170:3080`，既不是 loopback 也不在 `trustedHosts` 中 → `isTrustedApiRequest` 返回 `false` → 返回 HTTP 403。

`resolveLanTrust()` 从绑定地址 `0.0.0.0` 推导出容器 LAN IP（如 `172.19.0.2`），但**不包含公网 IP** `111.229.26.170`（因为公网 IP 是外部 NAT 映射，容器内部不可见）。

### 问题 2：Settings 不可用 — 客户端 `isLoopback` 为 false

即使 API 能正常通信，Settings 模块在客户端初始化时检查 `ctx.remote.$host.isLoopback`：

```typescript
// packages/client/ui-settings/src/client/index.ts
const persistence = ctx.remote.$host.isLoopback ? 'host' : 'memory'
```

当 `persistence === 'memory'` 时，`SettingsDescribeMirror` 的 status 为 `'unavailable'`，`ensure()` 直接返回而不发起 API 调用，导致 Settings 页面显示"settings are unavailable in this browser"。

`isLoopback` 的计算逻辑：

```typescript
// packages/client/connection/src/client/index.ts
isLoopback: transport?.ownsHost === true
  || pageLocation === undefined
  || isLoopbackHostname(pageLocation.hostname)  // 公网 IP 不是 loopback → false
```

## 解决方案

### 修复 1：服务端 — 通过 `--trusted-host` 声明公网 IP

在启动命令中添加 `--trusted-host 111.229.26.170`，让 trust fence 接受来自该 Host 的请求。

**修改文件：**

1. **`deploy/Dockerfile.optimized`** — 在 CMD 中添加 `--trusted-host`：

```dockerfile
CMD ["node", "apps/cli/lib/bin.js", "web", "--host", "0.0.0.0", "--port", "3080", \
     "--no-open", "--trusted-host", "111.229.26.170"]
```

2. **`deploy/docker-compose.yml`** — 添加 `command` 覆盖（无需重新构建镜像即可生效）：

```yaml
command: ["node", "apps/cli/lib/bin.js", "web", "--host", "0.0.0.0", "--port", "3080", \
          "--no-open", "--trusted-host", "111.229.26.170"]
```

### 修复 2：客户端 — 通过 HTML 注入声明服务端信任

服务端在 `DSH_ALLOW_WILDCARD_HOST=1` 环境下（Docker 容器的默认配置），通过 `tapIndex()` 向 `index.html` 注入全局标志 `__DSH_TRUSTED_REMOTE__`，客户端读取该标志后将 `isLoopback` 视为 `true`。

**修改文件：**

1. **`packages/bundle/web-app/src/index.ts`** — 添加 `tapIndex` 注入逻辑：

```typescript
// When DSH_ALLOW_WILDCARD_HOST=1, tell the client bundle that this server
// is intentionally exposed to the network (trusted container environment).
// The client uses this flag to enable full settings persistence even when
// the page URL is not loopback (e.g. http://public-ip:3080).
if (process.env.DSH_ALLOW_WILDCARD_HOST) {
  ctx.webServer.tapIndex((html) => {
    const script = '<script>globalThis.__DSH_TRUSTED_REMOTE__=true</script>'
    return html.replace('<head>', `<head>${script}`)
  })
}
```

2. **`packages/client/connection/src/client/index.ts`** — 在 `isLoopback` 计算中添加 `__DSH_TRUSTED_REMOTE__` 检查：

```typescript
isLoopback: transport?.ownsHost === true
  || pageLocation === undefined
  || isLoopbackHostname(pageLocation.hostname)
  || (globalThis as { __DSH_TRUSTED_REMOTE__?: boolean }).__DSH_TRUSTED_REMOTE__ === true,
```

### 修复 3：接口兼容性调整

为了支持 transport 直接提供 `rpc`（不通过 `fetch`），同时保持现有测试代码兼容：

**修改文件：**

`packages/client/connection/src/client/index.ts`

1. **`ClientTransportHooks` 接口** — 添加可选 `rpc` 字段：

```typescript
export interface ClientTransportHooks {
  /** Transport for generic unary RPC channels. Optional when rpc is provided directly. */
  fetch?: RpcFetch
  openStream?: RpcStreamOpen
  ownsHost?: boolean
  rpc?: ClientConnectionRpc  // 新增：允许 transport 直接提供 RPC 实现
}
```

2. **`fetch` 从必填改为可选**：

```typescript
// 之前：fetch: RpcFetch
// 之后：fetch?: RpcFetch
```

3. **RPC 创建逻辑更新**：

```typescript
const rpc = fixtureRpc ?? transport?.rpc ?? createWebConnectionRpc(transport?.fetch, transport?.openStream)
```

## 修改文件汇总

| 文件 | 修改内容 |
|------|---------|
| `deploy/Dockerfile.optimized` | CMD 添加 `--trusted-host 111.229.26.170` |
| `deploy/docker-compose.yml` | 添加 `command` 覆盖（含 `--trusted-host`） |
| `packages/bundle/web-app/src/index.ts` | 添加 `tapIndex` HTML 注入 `__DSH_TRUSTED_REMOTE__` |
| `packages/client/connection/src/client/index.ts` | `isLoopback` 添加 `__DSH_TRUSTED_REMOTE__` 检查；`ClientTransportHooks` 添加 `rpc?`、`fetch?` 改为可选 |

## 验证结果

### 1. API 端点（HTTP 403 → 200）

```bash
# 之前：返回 403 Forbidden
curl -H "Host: 111.229.26.170:3080" http://127.0.0.1:3080/api/llm/listProviders
# HTTP/1.1 403 Forbidden

# 之后：返回 200 OK
curl -H "Host: 111.229.26.170:3080" http://127.0.0.1:3080/api/llm/listProviders
# HTTP/1.1 200 OK
```

### 2. Settings API

```bash
# settings/describe 正常返回
curl -X POST -d '{"method":"settings/describe","payload":{"args":{}}}' \
  -H "Host: 111.229.26.170:3080" -H "Content-Type: application/json" \
  http://127.0.0.1:3080/api/settings/describe
# {"writable":true,"hasDocument":true,"namespaces":[...]}
```

### 3. HTML 注入

```bash
curl -b cookies.txt http://127.0.0.1:3080/ | grep "__DSH_TRUSTED_REMOTE__"
# <script>globalThis.__DSH_TRUSTED_REMOTE__=true</script>
```

### 4. Docker 构建与容器状态

```
Build exit code: 0
Container deepseek-harness: Up (healthy)
```

## 安全考虑

- `--trusted-host` 仅声明该 Host 头可信，不跳过认证（`isAuthenticated` 检查仍然生效）
- `__DSH_TRUSTED_REMOTE__` 仅在服务端显式设置 `DSH_ALLOW_WILDCARD_HOST=1` 时注入，非默认行为
- `DSH_ALLOW_WILDCARD_HOST` 本身是 Docker 容器环境的标志，表示运行在受信任的隔离环境中
- 认证 token 仍然通过 URL 参数传递，cookie 机制保持不变
