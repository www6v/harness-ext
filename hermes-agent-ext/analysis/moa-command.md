# /moa 命令深度分析 — Mixture of Agents

## 概述

`/moa` 是 Hermes Agent 的 **Mixture of Agents（混合智能体）** 命令，允许用户将单个提示通过多个参考模型（advisor/reference）并行分析，然后由聚合模型（aggregator）综合所有建议后作为行动模型执行。执行完成后自动恢复到之前的模型。

> "Run one prompt through the default MoA preset, then restore your model"

这是一个**单次（one-shot）**命令——不同于通过模型选择器永久切换到 MoA 预设，`/moa` 仅对当前提示生效，执行后自动恢复原模型。

---

## 核心概念

### Mixture of Agents（MoA）架构

MoA 是一种多模型协作模式，核心思想是：

```
              用户提示
                 │
                 ▼
    ┌────────────────────────┐
    │   构建 Advisory View   │  ← 从对话历史提取纯文本视图
    │   (参考模型视图)        │    (去掉系统提示、折叠工具结果)
    └───────────┬────────────┘
                │
        ┌───────┼───────┐
        ▼       ▼       ▼       ← 并行 Fan-out
    ┌──────┐┌──────┐┌──────┐
    │ Ref 1││ Ref 2││ Ref 3│   ← 参考模型（advisor）
    │GPT-5 ││DS-v4 ││Gemini│      每个独立分析、给出建议
    └──┬───┘└──┬───┘└──┬───┘
       │       │       │
       └───────┼───────┘
               ▼
    ┌────────────────────────┐
    │     Aggregator 合成     │  ← 聚合模型综合所有建议
    │  Claude Opus 4.8       │      产出简洁可行的指导
    └───────────┬────────────┘
                │
                ▼
    ┌────────────────────────┐
    │   Acting Model 执行    │  ← 聚合模型同时也是行动模型
    │   (调用工具、回答问题)   │      使用参考建议作为私有指导
    └────────────────────────┘
```

### 关键设计

1. **参考模型是顾问，不是执行者**：参考模型不能调用工具、访问文件或执行命令——它们只分析和提建议
2. **聚合模型 = 行动模型**：aggregator 同时是最终执行任务的模型
3. **参考建议作为私有上下文**：不直接展示给用户，而是作为 agent 的内部指导
4. **自动模型恢复**：one-shot 完成后恢复之前的模型设置

---

## 架构设计

### 模块结构

```
hermes_cli/moa_config.py          ← 配置、预设、编解码
agent/moa_loop.py                 ← 核心运行时（fan-out、聚合、facade）
agent/moa_trace.py                ← 可选 trace 持久化
agent/moa_alternation.py          ← 严格交替兼容性（same-role merge）
```

### 调用链路

```
用户输入 /moa <prompt>
    │
    ├── CLI (cli_model_switch_mixin.py)
    │   └── _cmd_moa()
    │       ├── 快照当前模型设置 → _pending_moa_restore_model
    │       ├── 切换 agent 到 MoA 虚拟 provider
    │       ├── 设置 _pending_moa_disable_after_turn = True
    │       └── 将 prompt 作为 _pending_agent_seed 排队
    │
    ├── TUI (tui_gateway/methods_tools.py)
    │   └── _cmd_moa()
    │       ├── 保存 moa_one_shot_restore 到 session
    │       ├── 通过 _apply_model_switch 切换到 MoA
    │       └── 返回 {"type": "send", "message": prompt}
    │
    ├── Gateway (gateway/run_inbound.py)
    │   └── _hm_cmd_moa()
    │       ├── 声明 one-turn restore
    │       ├── 设置 model_override 为 MoA 预设
    │       └── 将 event.text 重写为 prompt
    │
    └── Agent Turn
        └── build_moa_facade() → MoAClient
            └── MoAChatCompletions.create()
                ├── _resolve_preset_cached() → 预设配置
                ├── _reference_messages() → 构建 advisory view
                ├── _fanout_cache_key() → 检查缓存
                ├── _run_fanout() → 并行运行参考模型
                │   └── _run_references_parallel()
                │       └── ThreadPoolExecutor → _run_reference() × N
                ├── _build_guidance() → 构建指导文本
                └── _call_prepared_aggregator() → 聚合模型执行
```

---

## 核心模块分析

### 1. `hermes_cli/moa_config.py` — 配置与预设

#### 默认预设

```python
DEFAULT_MOA_REFERENCE_MODELS = [
    {"provider": "openai-codex", "model": "gpt-5.5"},
    {"provider": "openrouter", "model": "deepseek/deepseek-v4-pro"},
]

DEFAULT_MOA_AGGREGATOR = {
    "provider": "openrouter", "model": "anthropic/claude-opus-4.8"
}
```

#### 预设配置结构

```yaml
moa:
  default_preset: default
  privacy_filter: ""        # "" | "display" | "full"
  save_traces: false        # 是否保存完整 trace
  presets:
    default:
      enabled: true
      reference_models:
        - provider: openai-codex
          model: gpt-5.5
          reasoning_effort: medium   # 可选
          enabled: true
        - provider: openrouter
          model: deepseek/deepseek-v4-pro
      aggregator:
        provider: openrouter
        model: anthropic/claude-opus-4.8
      reference_temperature: null     # null = provider default
      aggregator_temperature: null
      reference_timeout: null         # null = 继承 auxiliary.moa_reference.timeout
      degraded_reference_policy: loud # "loud" | "silent"
      fanout: user_turn              # "user_turn" | "per_iteration" | "every_n:<N>"
```

#### Fan-out 节奏（fanout）

| 模式 | 行为 | 成本 |
|------|------|------|
| `user_turn`（默认） | 每个用户回合只运行一次 advisor；后续工具迭代复用缓存建议 | 最低 |
| `per_iteration` | 每次工具迭代都重新运行 advisor | 最高（乘以工具循环深度） |
| `every_n:<N>` | 回合第一次迭代 + 之后每 N 次迭代运行 advisor | 中间地带 |

#### 隐私过滤器（privacy_filter）

| 模式 | 行为 |
|------|------|
| `""` (off) | 默认。aggregator 看到原始 advisor 文本 |
| `"display"` | 仅对用户可见表面（UI 参考块、trace 文件）进行脱敏 |
| `"full"` | 同时脱敏注入 aggregator 提示的 advisor 文本 |

脱敏内容：
- 密钥/凭证（通过 `agent.redact.redact_sensitive_text`）
- 邮箱地址（正则匹配）
- 格式化电话号码（需要明确的区号/分隔符，避免误匹配 IP、SHA、版本号）

#### One-Shot 编解码

TUI/Gateway 等只能发送文本的表面通过隐藏标记编码 MoA 配置：

```python
MOA_MARKER_PREFIX = "__HERMES_MOA_TURN_V1__"

# 编码：prompt + config → base64 编码 → 标记前缀
encoded = f"{MOA_MARKER_PREFIX}{base64(payload)}"

# 解码：检测标记 → 提取 prompt 和 config
prompt, config = decode_moa_turn(encoded_message)
```

### 2. `agent/moa_loop.py` — 核心运行时

#### 参考模型系统提示（`_REFERENCE_SYSTEM_PROMPT`）

关键约束：
- **你不是行动 agent**——你不能调用工具、运行命令、浏览或访问文件
- **永远不要声称执行了任何操作**（不说"我运行了 curl"，而说"根据错误模式，curl 请求可能返回 404"）
- **基于上下文推理**——假设引用的文件、URL 或系统存在，从上下文推理
- **直接给出建议**——不要前言、不要工具免责声明
- **不要发出工具调用**——你的响应是给聚合器的私有指导

#### Advisory View 构建（`_reference_messages`）

从对话历史构建参考模型看到的视图：

1. **丢弃系统提示**——参考模型有自己的系统提示
2. **纯文本回合**——只保留 user/assistant 文本
3. **工具调用内联**——`tool_calls` 渲染为 `[called tool: name(args)]`
4. **工具结果折叠**——折叠到前一个 assistant 回合，超长内容 head+tail 截断（4000 字符预算）
5. **确保以 user 结尾**——Anthropic 拒绝尾部 assistant prefill，追加合成请求
6. **图像占位**——图像回合替换为 `[user sent non-text content]`

#### 并行 Fan-out（`_run_references_parallel`）

```python
executor = ThreadPoolExecutor(max_workers=min(_MAX_REFERENCE_WORKERS, total))
# _MAX_REFERENCE_WORKERS = 8（防止病态大预设）

for idx, slot in enumerate(reference_models):
    if slot.get("provider") == "moa":
        # 递归守卫：MoA 预设不能引用其他 MoA
        results[idx] = _placeholder_output(slot, "[skipped: MoA presets cannot recursively reference MoA]")
        continue
    futures[executor.submit(
        propagate_context_to_thread(_run_reference),
        slot, ref_messages, ...
    )] = idx
```

关键特性：
- **中断支持**：每 5 秒轮询 `_interrupt_requested`，支持用户中断
- **延迟记账**：被中断但仍运行的请求通过 `late_accounting_sink` 记录费用
- **上下文长度裁剪**：自动裁剪到参考模型的上下文窗口
- **缓存控制**：支持 Anthropic prompt caching（迭代 N+1 可重用 N 的缓存前缀）
- **进度回调**：每个参考完成后触发 `progress_callback(done, total, label)`

#### 参考模型上下文裁剪（`_trim_messages_for_reference`）

参考模型可能有比聚合器更小的上下文窗口（如 262K vs 1M）：

```
budget = window × (1 - 0.10) - reserve_output_tokens
```

- 从最旧的消息开始丢弃
- 始终保留尾部 user 回合 + 至少一个前驱回合
- 保持 user-first 不变式

#### 缓存机制

**预设缓存**（`_resolve_preset_cached`）：
- 按配置文件签名缓存，避免每次 `create()` 重新验证
- 一个 config stamp 同时只保留一个条目

**运行时缓存**（`_slot_runtime`）：
- 按 `(profile_home, provider, model)` 缓存
- TTL 300 秒（平衡密钥轮换/配置编辑的及时性）
- 错误不缓存（避免暂时错误锁定空 kwargs）

**参考输出缓存**（`MoAChatCompletions._ref_cache_*`）：
- 按 fanout 模式决定缓存键
- `user_turn`：只哈希到最后一个 user 消息的前缀（工具迭代是 HIT）
- `per_iteration`：每次 advisory view 变化都 MISS
- `every_n:N`：回合第 1 次 + 每 N 次状态变化
- 中断的 fan-out 永不缓存

#### 聚合指导构建（`_build_guidance`）

```
[Mixture of Agents reference context]
Preset: default
Aggregator/acting model: openrouter:anthropic/claude-opus-4.8
References: openai-codex:gpt-5.5, openrouter:deepseek/deepseek-v4-pro

Use the reference responses below as private context. You are the
aggregator and acting model: answer the user directly or call tools
as needed.

[stale guidance note - 如果缓存命中且已有工具活动]

Reference 1 — openai-codex:gpt-5.5:
<advisor text>

Reference 2 — openrouter:deepseek/deepseek-v4-pro:
<advisor text>
```

**陈旧指导注释**（`_STALE_GUIDANCE_NOTE`）：
当缓存命中且自上次 user 回合以来已有工具活动时，添加警告：
> "This guidance was produced earlier in this turn, before the tool results below it. Check the transcript before acting on it: a step it suggests may already have run."

#### 严格交替兼容性（`moa_alternation.py`）

问题：aggregator 请求以 `user(task), user(guidance)` 结尾——一些严格交替的 chat 模板（llama.cpp/vLLM Jinja、Mistral、部分 OpenRouter 路由）会 400。

解决方案——**反应性、目标范围的合并**：
1. 400 被分类为 `FailoverReason.role_alternation` → 重试一次（合并相邻同角色消息）
2. 记住该目标（`base_url` + model），后续迭代预合并
3. 接受分离形状的目的地永不触碰——其前缀保持字节稳定

#### 费用记账

每个参考模型按**自己的费率**计价（不同 advisor 可能用不同模型）：

```python
def _sum_reference_accounting(outputs):
    usage = CanonicalUsage()
    cost = None
    for _lbl, _txt, acct in outputs:
        usage = usage + acct.usage      # token 求和
        if acct.cost_usd is not None:
            cost = (cost or 0) + acct.cost_usd  # 美元求和
    return usage, cost
```

通过 `consume_reference_usage()` 消费，避免流式重试重复计算。

### 3. `agent/moa_trace.py` — Trace 持久化

可选功能（`moa.save_traces: true`）：每个 cache-MISS 的 MoA 回合追加一条 JSONL 到 `<hermes_home>/moa-traces/<session_id>.jsonl`。

记录内容：
- 时间戳、session_id、preset 名称
- 每个参考模型：label、model、provider、temperature、**完整** input messages、output、usage、cost
- 聚合器：label、model、provider、temperature、input messages、output、streamed 标记

**注意**：trace 是旁路——永远不进入 `messages` 表、历史或重播（参考是 advisory 侧调用，其行会破坏角色交替）。

### 4. MoAChatCompletions — OpenAI 兼容 Facade

`MoAChatCompletions` 实现了 OpenAI chat completions 接口，使 MoA 对 agent 循环透明：

```python
class MoAChatCompletions:
    def create(self, **api_kwargs) -> Any:
        # 1. 解析预设（缓存）
        # 2. 构建 advisory view
        # 3. 检查参考缓存
        # 4. 运行 fan-out（或缓存命中）
        # 5. 构建指导
        # 6. 调用聚合器（带 cache_control 装饰）
        # 7. 返回响应（或流迭代器）
```

`MoAClient` 包装它，提供与 OpenAI client 相同的接口：
```python
client = MoAClient(preset_name, reference_callback, agent)
client.chat.completions.create(messages=..., tools=..., stream=True)
```

---

## 跨表面实现

### CLI 表面

```python
def _cmd_moa(self, cmd_original):
    payload = _slash_args(cmd_original)
    if not payload:
        _cprint(f"  {moa_usage()}")
        return True
    # 快照当前模型
    self._pending_moa_restore_model = {key: getattr(self, key) for key in (...)}
    # 切换到 MoA 虚拟 provider
    self.requested_provider = "moa"
    self.provider = "moa"
    self.model = preset
    self.api_key = "moa-virtual-provider"
    self.base_url = "moa://local"
    # 退役当前 agent，排队 prompt
    _retire_agent(self)
    self._pending_moa_disable_after_turn = True
    self._pending_agent_seed = payload
```

### TUI 表面

```python
def _cmd_moa(rid, params, session, name, arg):
    # 保存恢复信息
    session["moa_one_shot_restore"] = {
        "override": session.get("model_override"),
        "model": getattr(agent, "model"),
        "provider": getattr(agent, "provider"),
    }
    # 切换模型（persist_override=False：不写入 config.yaml）
    _apply_model_switch(sid, session, f"{preset} --provider moa", ...)
    # 返回发送指令
    return _ok(rid, {"type": "send", "message": arg})
```

回合完成后在 `prompt_turn.py` 中恢复：
```python
if "moa_one_shot_restore" in session:
    _restore = session.pop("moa_one_shot_restore")
    # 恢复之前的 model_override 和 agent 模型
```

### Gateway 表面

```python
async def _hm_cmd_moa(self, event, source, _quick_key):
    # 声明 one-turn restore
    self._claim_one_turn_restore(_quick_key)
    # 设置 model_override
    _moa_state.conversation.model_override = {
        "provider": "moa", "model": moa_cfg["default_preset"],
        "base_url": "moa://local", "api_key": "moa-virtual-provider",
        "api_mode": "chat_completions",
    }
    # 重写 event text
    event.text = moa_payload
```

### 虚拟 Provider

MoA 是一个**虚拟 provider**，不连接任何真实 API：

```python
agent.model = preset_name
agent.provider = "moa"
agent.api_mode = "chat_completions"
agent.api_key = "moa-virtual-provider"
agent.base_url = "moa://local"
agent.client = build_moa_facade(agent, agent.model)  # → MoAClient
```

`build_moa_facade()` 确保 `reference_callback` 中继到 agent 的 `tool_progress_callback`，使 UI 能显示进度。

---

## 进度与 UI 事件

MoA 通过 `reference_callback` 发射事件到 agent 的进度回调：

| 事件 | 含义 |
|------|------|
| `moa.progress` | 参考模型完成进度（refs_done, refs_total, label） |
| `moa.reference` | 单个参考模型结果（index, count, label, text） |
| `moa.phase` | 阶段转换（fan-out → aggregator） |
| `moa.aggregating` | 聚合器开始工作 |

---

## 降级与错误处理

| 场景 | 行为 |
|------|------|
| 参考模型超时/失败 | 变为 `[failed: <error>]` 标记，不中断整个流程 |
| 所有参考模型失败 | 跳过聚合器合成，aggregator 独立行动 |
| `degraded_reference_policy: loud` | 在指导中包含失败通知 |
| `degraded_reference_policy: silent` | 静默忽略失败 |
| 用户中断 fan-out | 取消未开始的 future；运行中的通过 late_accounting 记账 |
| 递归 MoA（provider="moa" 的 slot） | 跳过并标记 `[skipped: ...]` |
| 严格交替 400 | 反应性合并同角色消息，记住该目标 |

---

## 配置验证

`validate_moa_payload()` 在**写入时**验证（API 路径），`normalize_moa_config()` 在**读取时**宽容处理：

- 每个 slot 必须有 `provider` 和 `model`
- 预设至少需要一个完整的参考模型
- aggregator 必须是完整的 slot
- `provider: "moa"` 不能在预设内使用（防递归）

---

## 设计亮点

1. **透明 Facade 模式**：`MoAClient` 实现 OpenAI chat completions 接口，agent 循环完全不知道自己在运行 MoA——对工具调用、流式、重试都透明。

2. **精细的缓存层次**：预设缓存（配置签名）、运行时缓存（provider 解析 TTL）、参考输出缓存（fanout 节奏）——三层缓存独立优化不同开销。

3. **中断安全**：fan-out 可被用户中断，正在运行的请求通过延迟记账确保费用不丢失，中断的快照永不缓存。

4. **反应性兼容**：不主动为所有目的地合并同角色消息（会破坏缓存稳定性），只在收到 400 后反应性合并并记住该目的地。

5. **隐私纵深**：三级隐私过滤（off/display/full），PII 脱敏独立于全局日志脱敏，密钥形状委托给中央脱敏器，邮箱/电话使用安全的正则（不误匹配 SHA、IP、版本号）。

6. **成本透明**：每个参考模型按自己的费率计价（不同模型不同价），总费用以美元求和，通过 `consume_reference_usage()` 单一消费点避免重复计算。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `hermes_cli/moa_config.py` | 配置、预设、编解码、验证 |
| `agent/moa_loop.py` | 核心运行时：fan-out、聚合、MoAChatCompletions facade |
| `agent/moa_trace.py` | 可选 trace 持久化（JSONL） |
| `agent/moa_alternation.py` | 严格交替兼容性（same-role merge） |
| `hermes_cli/cli_model_switch_mixin.py` | CLI 表面 `/moa` 处理 |
| `tui_gateway/methods_tools.py` | TUI 表面 `/moa` RPC |
| `tui_gateway/prompt_turn.py` | TUI 回合后模型恢复 |
| `gateway/run_inbound.py` | Gateway 表面 `/moa` 处理 |
| `hermes_cli/commands.py` | 命令注册（busy_policy="reject", busy_handler="moa"） |
| `agent/auxiliary_client.py` | `call_llm()` — 参考/聚合模型的 LLM 调用 |
