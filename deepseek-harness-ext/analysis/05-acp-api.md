# ACP (Agent Client Protocol) 接口

## 概述

**Agent Client Protocol (ACP)** 是一个面向自动化的 JSON-RPC stdio 协议，将 DeepSeek Harness 的持久会话能力暴露给可信的程序化客户端（如 VS Code、CI 系统）。

- **协议**: ACP（基于 `@agentclientprotocol/sdk`）
- **传输**: 换行分隔的 JSON-RPC over stdio
- **源码位置**: `packages/acp/acp/`
- **包名**: `@deepseek-ai/dsh-acp`
- **Profile**: `dsh --profile acp`

## 与 SDK 的区别

| 特性 | SDK | ACP |
|------|-----|-----|
| 会话模型 | 简单的 sessionId → prompt | 完整的会话生命周期管理 |
| 会话恢复 | 不支持 | 支持 resume |
| 会话列表 | 不支持 | 支持 list（分页） |
| 配置选项 | 初始化时固定 | 运行时可修改 |
| MCP 集成 | 不支持 | 支持 MCP 服务器挂载 |
| 权限请求 | 不支持 | 支持 requestPermission |
| 目标场景 | 简单脚本 | IDE 集成、复杂自动化 |

## 请求方法（Client → Server）

### 1. `initialize` — 握手

**参数**: `InitializeRequest`（空或最小）

**结果**:
```typescript
interface InitializeResponse {
  protocolVersion: string
  agentInfo: { name: string, version: string }
  agentCapabilities: {
    mcpCapabilities: { http: true }
    promptCapabilities: {
      image: boolean        // 是否支持图片提示
      audio: false
      embeddedContext: false
    }
    sessionCapabilities: {
      close: {}             // 支持关闭会话
      list: {}              // 支持列出会话
      resume: {}            // 支持恢复会话
    }
  }
  authMethods: []           // 当前无认证方法
}
```

### 2. `authenticate` — 认证

**参数**: `AuthenticateRequest`

**结果**: `void`（当前为 no-op）

### 3. `session/new` — 创建新会话

**参数**:
```typescript
interface NewSessionRequest {
  cwd: string                    // 工作目录
  mcpServers?: McpServerConfig[] // MCP 服务器配置（可选）
}
```

**结果**:
```typescript
interface NewSessionResponse {
  sessionId: string              // 新会话 ID
  configOptions: ConfigOption[]  // 可配置选项（如模型选择）
}
```

### 4. `session/resume` — 恢复会话

**参数**:
```typescript
interface ResumeSessionRequest {
  sessionId: string    // 要恢复的会话 ID
}
```

**结果**:
```typescript
interface ResumeSessionResponse {
  sessionId: string
  configOptions: ConfigOption[]
}
```

### 5. `session/list` — 列出会话

**参数**:
```typescript
interface ListSessionsRequest {
  cursor?: string    // 分页游标（可选）
}
```

**结果**:
```typescript
interface ListSessionsResponse {
  sessions: SessionSummary[]    // 会话摘要列表
  nextCursor?: string           // 下一页游标
}
```

### 6. `session/close` — 关闭会话

**参数**:
```typescript
interface CloseSessionRequest {
  sessionId: string
}
```

**结果**:
```typescript
interface CloseSessionResponse {
  // 确认关闭
}
```

### 7. `session/setConfigOption` — 设置配置选项

**参数**:
```typescript
interface SetSessionConfigOptionRequest {
  sessionId: string
  optionId: string    // 配置选项 ID
  value: string       // 选项值
}
```

**结果**:
```typescript
interface SetSessionConfigOptionResponse {
  // 确认设置
}
```

### 8. `session/prompt` — 发送提示

**参数**:
```typescript
interface PromptRequest {
  sessionId: string
  content: PromptContent[]    // 提示内容
}
```

**结果**:
```typescript
interface PromptResponse {
  stopReason: string    // 停止原因
}
```

## 通知方法

### Client → Server

| 方法 | 说明 |
|------|------|
| `session/cancel` | 取消当前活跃的提示 |

### Server → Client

| 方法 | 说明 |
|------|------|
| `session/update` | 会话状态更新（轮次进度、工具调用等） |
| `session/requestPermission` | 请求一次性权限决策 |

## 配置

启动 ACP Profile 时的配置参数：

```typescript
interface AcpConfig {
  provider?: string          // 默认 Provider
  model?: string             // 默认模型
  sessionListPageSize?: number // 会话列表分页大小（默认 100）
}
```

## 使用示例

```bash
# 启动 ACP 运行时
dsh --profile acp
```

客户端通过 stdio 与进程通信：

```json
// Client → Server: 初始化
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}

// Server → Client: 初始化结果
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"...","agentInfo":{...},...}}

// Client → Server: 创建会话
{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/project"}}

// Server → Client: 会话创建结果
{"jsonrpc":"2.0","id":2,"result":{"sessionId":"abc-123","configOptions":[...]}}

// Client → Server: 发送提示
{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"abc-123","content":[{"type":"text","text":"分析代码"}]}}

// Server → Client: 会话更新通知
{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"abc-123",...}}

// Server → Client: 提示完成
{"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}
```
