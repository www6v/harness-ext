# Typert RPC Payload 结构修复

## 问题背景

在 meta-harness 通过 Typert RPC 协议调用 deepseek-harness 的 `session.create`、`session.prompt` 和 `session/follow` 端点时，遇到一系列参数验证错误。

## 遇到的问题与解决方案

### Bug 1: `args` 字段缺失

**错误信息：**
```
gateway/arguments-invalid: typert gateway: session/create: args fields do not match the schema
```

**原因：**
Typert RPC 协议要求 payload 必须包含 `args` 字段作为参数容器。

**解决方案：**
```go
// 错误写法
Payload: map[string]any{
    "sessionId": sessionID,
}

// 正确写法
Payload: map[string]any{
    "args": map[string]any{
        // ... parameters
    },
}
```

---

### Bug 2: `request` 字段命名不匹配

**错误信息：**
```
gateway/arguments-invalid: typert gateway: session/create: args fields do not match the descriptor: missing "request"; unexpected "cwd", "sessionId"
```

**原因：**
Typert RPC 的 `@Remote` 装饰器定义了方法签名，如 `create(request: SessionCreateRequest)`。参数名必须匹配方法签名中的形参名 `request`。

**解决方案：**
```go
// 错误写法 - 直接放参数
Payload: map[string]any{
    "args": map[string]any{
        "sessionId": sessionID,
        "cwd":       cwd,
    },
}

// 正确写法 - 使用 request 包装
Payload: map[string]any{
    "args": map[string]any{
        "request": map[string]any{
            "sessionId": sessionID,
            "cwd":       cwd,
        },
    },
}
```

---

### Bug 3: `cwd` 必须是绝对路径

**错误信息：**
```
session header cwd must be an absolute path, got "."
```

**原因：**
deepseek-harness 出于安全和一致性考虑，要求工作目录必须是绝对路径。

**解决方案：**
```go
// 错误写法
cwd := "."

// 正确写法
cwd, _ := os.Getwd()
if cwd == "" {
    cwd = "."
}
```

---

### Bug 4: `session/follow` 需要 `address` 结构

**错误信息：**
```
gateway/arguments-invalid: typert gateway: session/follow: args fields do not match the descriptor: missing "address"; unexpected "sessionId"
gateway/input-invalid: typert gateway: session/follow: wire field "request" failed boundary validation
```

**原因：**
`session/follow` 端点期望 `SessionFollowRequest` 结构，其中 `address` 字段是一个 discriminated union：
```typescript
interface SessionFollowRequest {
  address: SessionAddress  // { kind: "session" | "subagent", ... }
  maxMessages?: number
  assistantStream?: boolean
}
```

**解决方案：**
```go
// 错误写法 - 直接放 sessionId
Payload: map[string]any{
    "args": map[string]any{
        "request": map[string]any{
            "sessionId": sessionID,
        },
    },
}

// 正确写法 - 使用 address 结构
Payload: map[string]any{
    "args": map[string]any{
        "request": map[string]any{
            "address": map[string]any{
                "kind":      "session",
                "sessionId": sessionID,
            },
        },
    },
}
```

---

## 完整的 Payload 结构

### 一元调用 (HTTP POST `/api/<method>`)

```json
{
  "type": "client-request",
  "rpcId": "uuid-string",
  "method": "namespace/methodName",
  "payload": {
    "args": {
      "request": {
        "sessionId": "sess-xxx",
        "cwd": "/absolute/path"
      }
    }
  }
}
```

### 流式调用 (WebSocket `/api/remote.mux`)

**Open 消息：**
```json
{
  "type": "open",
  "streamId": "uuid",
  "endpoint": "session/follow",
  "payload": {
    "args": {
      "request": {
        "address": {
          "kind": "session",
          "sessionId": "sess-xxx"
        }
      }
    }
  }
}
```

---

## 文件修改

- `internal/harness/deepseek_client.go` - 核心 RPC 客户端
  - `ensureSession()` - session.create 参数包装
  - `RunTurn()` - session.prompt 参数包装
  - `collectTurn()` / `RunTurnStream()` - session/follow 参数包装

- `internal/harness/deepseek_client_test.go` - 单元测试更新

- `internal/harness/deepseek_auth_integration_test.go` - 认证集成测试更新

---

## 验证

E2E 验证脚本 (`scripts/e2e/verify-deepseek-harness.mjs`) 可验证：
1. Platform 健康检查
2. DeepSeek gateway 可达性
3. Agent 创建 (harness=deepseek)
4. Session 创建
5. 消息发送
6. Turn 执行（需要有效的 DeepSeek API key）

---

## 参考资料

- `docs/deepseek-rpc-fix.md` - 详细的 Typert RPC 协议文档
- `deepseek-harness/packages/api/session-controller/src/types.ts` - SessionFollowRequest 定义
- `deepseek-harness/packages/typert/protocol/README.md` - Typert RPC 协议规范
