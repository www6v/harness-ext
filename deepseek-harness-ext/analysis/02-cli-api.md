# CLI 命令行接口

## 入口

- **二进制命令**: `dsh`（通过 `npx @deepseek-ai/dsh` 或从源码 `pnpm dsh`）
- **源码位置**: `apps/cli/src/bin.ts`、`apps/cli/src/args.ts`

## 调用模式

| 模式 | 命令格式 | 说明 |
|------|---------|------|
| Profile 启动 | `dsh --profile <name> [args...]` | 启动指定 Profile |
| Web 别名 | `dsh web [args...]` | 等价于 `dsh --profile web` |
| 插件管理 | `dsh plugin --profile <name> <pnpm args...>` | 管理 Profile 插件依赖 |
| 配置导出 | `dsh --profile <name> --dump-config` | 导出组合后的配置树 |
| 默认配置导出 | `dsh --profile <name> --dump-default-config` | 导出无用户层的配置树 |

## 启动参数

### Launcher 参数（由 CLI 自身处理）

| 参数 | 说明 |
|------|------|
| `--profile <name>` | 选择要启动的 Profile（必填，`web` 子命令除外） |
| `--from-default-profile <name>` | 从发布的模板初始化新 Profile |
| `--patch <path>` | 额外的配置覆盖层（可重复） |
| `--dump-config` | 打印组合后的配置树并退出 |
| `--dump-default-config` | 打印无用户层的配置树并退出 |
| `-V, --version` | 打印版本号 |
| `-h, --help` | 打印帮助信息 |

### 内置 Profile

| Profile | 说明 |
|---------|------|
| `web` | Web UI（默认），启动 HTTP 服务器 + 浏览器前端 |
| `headless` | 无头模式，执行单次任务后退出 |
| `sdk` | SDK JSON-RPC 运行时 |
| `sdk-minimal` | 最小 SDK 运行时 |
| `acp` | Agent Client Protocol 运行时 |

## Web Profile 参数

`dsh web` 启动后，Web 应用自身的参数包括：

| 参数 | 说明 |
|------|------|
| `--no-open` | 启动服务器但不打开浏览器 |
| `--host <host>` | 绑定地址（`127.0.0.1` 或 `0.0.0.0`） |
| `--port <port>` | 绑定端口（默认 `3080`，0 表示 OS 分配） |

## Headless Profile 参数

`dsh --profile headless` 的参数传递给 headless 应用：

| 参数 | 说明 |
|------|------|
| `<prompt>` | 要执行的任务描述（位置参数） |
| `--resume <session>` | 恢复已有会话 |
| `--provider <name>` | 指定 LLM Provider |
| `--model <name>` | 指定 LLM 模型 |

## 使用示例

```bash
# 启动 Web UI
dsh web

# 启动 Web UI 但不打开浏览器
dsh web --no-open

# 执行单次任务
dsh --profile headless "帮我写一个 hello world"

# 恢复会话
dsh --profile headless --resume <session-id> "继续上次的工作"

# 管理插件
dsh plugin --profile web add @some/dsh-plugin

# 导出配置
dsh --profile web --dump-config

# 从模板创建自定义 Profile
dsh --profile my-profile --from-default-profile web
```
