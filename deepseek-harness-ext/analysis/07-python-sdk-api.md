# Python SDK 接口

## 概述

DeepSeek Harness 提供了 Python SDK，允许 Python 程序通过子进程驱动 Agent。SDK 封装了 JSON-RPC stdio 协议，提供同步和异步两种调用模式。

- **包名**: `deepseek-harness-sdk`（PyPI）
- **源码位置**: `python/sdk/`
- **依赖**: 自动下载并管理 `dsh` 运行时二进制

## 安装

```bash
pip install deepseek-harness-sdk
```

## 高层 API: `DeepSeekHarness`

### 基本用法

```python
from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

# 使用默认配置
with DeepSeekHarness() as harness:
    result = harness.run("帮我分析这段代码")
    print(result.final_response)

# 使用自定义配置
config = DeepSeekHarnessConfig(
    provider="deepseek-official",
    model="deepseek-v4-flash",
    cwd="/path/to/project",
    max_tokens=4096,
)

with DeepSeekHarness(config) as harness:
    result = harness.run("写一个 hello world 程序")
    print(result.final_response)
    print(f"Finish reason: {result.finish_reason}")
    print(f"Events: {len(result.events)}")
```

### 配置参数

```python
@dataclass
class DeepSeekHarnessConfig:
    provider: str = "deepseek-official"     # LLM Provider
    model: str = "deepseek-v4-flash"        # 模型名称
    reasoning_effort: str | None = None     # 推理强度
    max_tokens: int | None = None           # 最大输出 token
    cwd: str | None = None                  # 工作目录（默认当前目录）
    runtime_cwd: str | None = None          # 运行时工作目录
    dsh_bin: str | None = None              # dsh 二进制路径（自动解析）
    profile: str = "sdk"                    # 使用的 Profile
    patches: tuple[str, ...] = ()           # 配置覆盖层
    dsh_home: str | None = None             # DSH_HOME 路径
    env: dict[str, str] = {}                # 额外环境变量
    initialize_timeout_seconds: float = 30.0 # 初始化超时
    request_timeout_seconds: float | None = None  # 请求超时
    shutdown_timeout_seconds: float | None = 1.0  # 关闭超时
    base_url: str | None = None             # API Base URL
    api_key: str | None = None              # API Key
```

### `RunResult` 结构

```python
@dataclass
class RunResult:
    session_id: str              # 会话 ID
    final_response: str          # 最终响应文本
    finish_reason: str | None    # 完成原因
    events: list[JsonObject]     # 所有会话事件
    notifications: list[Notification]  # 所有通知
```

### 多轮对话

```python
with DeepSeekHarness() as harness:
    # 第一轮
    result1 = harness.run("帮我创建一个 Python 项目")
    print(result1.final_response)

    # 第二轮（同一会话）
    result2 = harness.run("添加单元测试")
    print(result2.final_response)

    # 第三轮
    result3 = harness.run("添加 CI 配置")
    print(result3.final_response)
```

## 底层 API: `HarnessClient`

### 直接使用客户端

```python
from deepseek_harness.client import HarnessClient, HarnessConfig

config = HarnessConfig(
    dsh_bin="/usr/local/bin/dsh",
    profile="sdk",
)

client = HarnessClient(config)
client.start()

# 初始化
client.initialize(
    cwd="/project",
    provider="deepseek-official",
    model="deepseek-v4-flash",
)

# 发送提示
message_id = client.prompt("session-1", [
    {"type": "text", "text": "Hello"}
])

# 读取通知
for notification in client.notifications():
    print(notification)

client.close()
```

## 环境变量

SDK 继承调用方的环境变量，以下变量有特殊含义：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | DeepSeek API Base URL |
| `DSH_HOME` | DeepSeek Harness 主目录 |

可以通过 `DeepSeekHarnessConfig.env` 覆盖或注入：

```python
config = DeepSeekHarnessConfig(
    env={
        "DEEPSEEK_API_KEY": "sk-...",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }
)
```

或使用 `base_url` 和 `api_key` 快捷方式：

```python
config = DeepSeekHarnessConfig(
    base_url="https://api.deepseek.com",
    api_key="sk-...",
)
```

## 错误处理

```python
from deepseek_harness.errors import SdkProtocolError

try:
    result = harness.run("分析代码")
except SdkProtocolError as e:
    print(f"Protocol error: {e}")
except TimeoutError:
    print("Request timed out")
```

## 与 TypeScript SDK 的对比

| 特性 | Python SDK | TypeScript SDK |
|------|-----------|----------------|
| 语言 | Python | TypeScript |
| 同步/异步 | 同步为主 | 异步为主 |
| 子进程管理 | 自动 | 自动 |
| 运行时分发 | 通过 `deepseek-harness-runtime-bin` | 通过 `dsh` npm 包 |
| 高层 API | `DeepSeekHarness` | `DeepSeekHarness` |
| 底层 API | `HarnessClient` | `HarnessClient` |
| 通知订阅 | 迭代器 | AsyncIterable |

## 最低要求

- Python >= 3.10
- 支持的平台：Linux (x64/arm64), macOS (x64/arm64), Windows (x64)
