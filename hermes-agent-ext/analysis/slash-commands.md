# Hermes Agent 斜杠命令完整参考

> 数据来源：`hermes_cli/commands.py` 中的 `COMMAND_REGISTRY`
>
> Hermes 的所有斜杠命令（`/command`）都注册在统一的 `COMMAND_REGISTRY` 列表中。每个命令有一个规范名、描述、分类、可选的别名、参数提示、子命令列表，以及跨表面（CLI/Gateway/TUI/Desktop）的可用性标记。

---

## 命令分类总览

| 分类 | 命令数量 | 说明 |
|------|---------|------|
| **Session**（会话） | ~40 | 会话管理、消息控制、自动化 |
| **Configuration**（配置） | ~20 | 模型、显示、模式切换 |
| **Tools & Skills**（工具与技能） | ~20 | 工具管理、技能系统、定时任务 |
| **Info**（信息） | ~15 | 版本、用量、调试、剪贴板 |
| **Exit**（退出） | 1 | 退出 CLI |

---

## Session — 会话管理

### 基础会话

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/start` | — | 确认平台启动 ping，不回复 | Gateway |
| `/new` | `/reset` | 开启新会话（新 session ID + 清空历史） | 全表面 |
| `/clear` | — | 清屏并开启新会话 | CLI |
| `/redraw` | — | 强制完整 UI 重绘（恢复终端漂移） | CLI |
| `/history` | — | 显示对话历史 | CLI |
| `/title` | — | 设置当前会话标题 | 全表面 |
| `/resume` | — | 恢复之前的会话 | 全表面 |
| `/sessions` | — | 浏览并恢复历史会话 | 全表面 |
| `/topic` | — | 启用或查看 Telegram DM 话题会话 | Gateway |
| `/sethome` | `/set-home` | 设置当前聊天为主频道 | Gateway |

### 消息控制

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/retry` | — | 重试上一条消息（重新发送给 agent） | 全表面 |
| `/undo` | — | 回退 N 个用户回合并重新提示（默认 1） | 全表面 |
| `/save` | — | 导出当前对话（bare 显示用法） | 全表面 |
| `/prompt` | `/compose` | 在 `$EDITOR` 中编写下一条提示（markdown） | CLI |
| `/stop` | — | 终止所有运行中的后台进程 | 全表面 |
| `/pause` | — | 全局暂停新工作（紧急停止）；`/pause off` 恢复 | Gateway |
| `/approve` | — | 批准待处理的危险命令 | Gateway |
| `/deny` | — | 拒绝待处理的危险命令（可附原因） | Gateway |

### 后台与自动化

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/bg` | — | 在独立后台会话中运行提示 | 全表面 |
| `/btw` | — | 在不中断当前对话的情况下问一个旁支问题 | 全表面 |
| `/agents` | `/tasks` | 显示活跃的 agent 和运行中的任务 | 全表面 |
| `/queue` | `/q` | 为下一回合排队提示，或列出/编辑/删除/移动/清空已排队的提示 | 全表面 |
| `/steer` | — | 在下一个工具调用后注入消息（不中断） | 全表面 |
| `/goal` | — | 设置 Hermes 跨回合持续工作的目标 | 全表面 |
| `/subgoal` | — | 添加或管理活跃目标的额外条件 | 全表面 |
| `/heartbeat` | `/hb` | 设置空闲时重新进入此会话的循环提示 | 全表面 |
| `/loop` | `/proactive` | 在此会话中按间隔重复运行提示 | 全表面 |
| `/refine` | — | 回顾当前对话，将经验保存到记忆/技能 | 全表面 |
| `/review` | — | 启动独立子 agent 审查刚讨论的工作（PR、代码、文档） | 全表面 |
| `/moa` | — | 通过默认 Mixture of Agents 预设运行一次提示，然后恢复模型 | 全表面 |

### 会话分支与协作

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/branch` | `/fork` | 分支当前会话（Discord/Telegram/Slack/Matrix 新线程；`--here` 留在原地） | 全表面 |
| `/handoff` | — | 将当前会话移交给消息平台 | CLI |
| `/worktree` | — | 显示、列出、创建或清理隔离的 git worktree | CLI |

### 上下文与压缩

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/compress` | `/compact` | 压缩对话上下文（`here [N]` 保留最近 N 轮；`--preview` 预览效果） | 全表面 |
| `/context` | `/ctx` | 显示详细上下文窗口视图：使用率仪表、分类明细、压缩统计、吞吐量 | 全表面 |
| `/rollback` | — | 列出或恢复文件系统检查点（恢复保留手动编辑；`--all` 覆盖） | 全表面 |
| `/snapshot` | `/snap` | 创建或恢复 Hermes 配置/状态的状态快照 | CLI |

### 学习与可视化

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/journey` | `/learning`, `/memory-graph` | 打开学习旅程时间线 | CLI |
| `/plan` | — | 将 markdown 实现计划写入 `.hermes/plans/`（不执行） | 全表面 |

### 状态信息

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/status` | — | 显示会话、模型、token、上下文信息 | 全表面 |
| `/usage` | — | 显示 token 用量和速率限制；`reset` 兑换 Codex 限制重置 | 全表面 |
| `/egress` | — | 显示 Docker 出站代理状态 | 全表面 |
| `/profile` | — | 显示活跃 profile 名称和 home 目录 | 全表面 |
| `/whoami` | — | 显示你的斜杠命令访问权限（admin / user） | 全表面 |

### 其他

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/restart` | — | 在排空活跃运行后优雅重启 gateway | Gateway |
| `/export` | — | 将 profile（配置、技能、主题）导出为可分享归档 | CLI |
| `/import` | — | 导入共享的 profile 归档为新 profile | CLI |

---

## Configuration — 配置

### 模型与推理

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/model` | — | 切换模型（会话范围；`--global` 持久化） | 全表面 |
| `/codex-runtime` | `/codex_runtime` | 切换 OpenAI/Codex 模型的 codex app-server 运行时 | 全表面 |
| `/reasoning` | — | 管理推理努力和显示（级别/show/hide/full/clamp） | 全表面 |
| `/fast` | — | 快速模式 — OpenAI Priority Processing / Anthropic Fast Mode | 全表面 |

### 显示与界面

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/config` | — | 显示当前配置 | CLI |
| `/skin` | — | 显示或更换显示皮肤/主题 | CLI |
| `/indicator` | — | 选择 TUI 忙碌指示器样式 | CLI |
| `/statusbar` | `/sb` | 切换上下文/模型状态栏 | CLI |
| `/battery` | — | 切换状态栏中的彩色电池指示器 | CLI |
| `/timestamps` | `/ts` | 切换消息和 `/history` 上的 `[HH:MM]` 时间戳 | CLI |
| `/verbose` | — | 循环工具进度显示：off → new → all → verbose | CLI |
| `/focus` | — | 切换聚焦视图 — 仅显示你的提示和最终响应 | CLI |
| `/footer` | — | 切换最终回复上的 gateway 运行时元数据页脚 | 全表面 |

### 行为模式

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/yolo` | — | 切换 YOLO 模式（跳过所有危险命令审批） | 全表面 |
| `/approvals` | — | 显示或设置持久危险命令审批模式（manual/smart/off） | 全表面 |
| `/personality` | — | 设置预定义人格 | 全表面 |
| `/busy` | — | 控制 Hermes 工作时消息的行为方式（queue/steer/interrupt） | 全表面 |

### 语音与唤醒

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/voice` | — | 切换语音模式（on/off/tts） | 全表面 |
| `/wake` | — | 切换 "Hey Hermes" 唤醒词监听 | CLI |

---

## Tools & Skills — 工具与技能

### 工具管理

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/tools` | — | 管理工具：列出/禁用/启用 | CLI |
| `/toolsets` | — | 列出可用工具集 | CLI |
| `/browser` | — | 通过 CDP 连接浏览器工具到实时 Chromium 浏览器，或切换到 Browser Use 模式 | CLI |
| `/reload` | — | 将 `.env` 变量重新加载到运行中的会话 | CLI |
| `/reload-mcp` | `/reload_mcp` | 从配置重新加载 MCP 服务器 | 全表面 |
| `/reload-skills` | `/reload_skills` | 重新扫描 `~/.hermes/skills/` 以发现新安装或删除的技能 | 全表面 |
| `/plugins` | — | 列出已安装插件及其状态 | CLI |

### 技能系统

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/skills` | — | 搜索、安装、检查或管理技能 | CLI |
| `/memory` | — | 审查待处理的记忆写入 / 切换审批门控 | 全表面 |
| `/bundles` | — | 列出技能包（别名 `/<name>` 可同时加载多个技能） | 全表面 |
| `/learn` | — | 从你描述的任何内容（目录、URL、当前对话、笔记）学习可复用技能 | 全表面 |
| `/init` | — | 从仓库扫描生成或更新 AGENTS.md 项目指令 | 全表面 |
| `/curator` | — | 后台技能维护（status/run/pin/archive/list-archived） | 全表面 |

### 定时与自动化

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/cron` | — | 管理定时任务（list/add/create/edit/pause/resume/run/remove） | CLI |
| `/suggestions` | `/suggest` | 审查建议的自动化（accept/dismiss） | 全表面 |
| `/blueprint` | `/bp` | 从蓝图模板设置自动化 | 全表面 |

### 看板协作

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/kanban` | — | 多 profile 协作看板（任务、链接、评论）— 拥有大量子命令 | 全表面 |

### 宠物系统

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/pet` | — | 切换或领养 petdex 吉祥物 | CLI |
| `/hatch` | `/generate-pet` | 从描述生成新的 petdex 宠物 | CLI |

---

## Info — 信息

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/commands` | — | 浏览所有命令和技能（分页） | Gateway |
| `/help` | — | 显示可用命令（`/help skills` 列出技能命令；`/help <text>` 过滤） | 全表面 |
| `/palette` | — | 打开模糊命令面板（也可通过 Ctrl+P） | CLI |
| `/version` | `/v` | 显示 Hermes Agent 版本 | 全表面 |
| `/debug` | — | 上传调试报告（系统信息 + 日志）并获取可分享链接 | 全表面 |
| `/diff` | — | 显示工作目录中的 git 变更（staged/all/session） | 全表面 |
| `/copy` | — | 将最后一条助手回复复制到剪贴板 | CLI |
| `/paste` | — | 从剪贴板附加图片 | CLI |
| `/image` | — | 附加本地图片文件用于下一条提示 | CLI |
| `/update` | — | 将 Hermes Agent 更新到最新版本 | 全表面 |
| `/subscription` | `/upgrade` | 查看你的 Nous 计划并在浏览器中更改 | CLI |
| `/login` | — | 使用 Nous 账户登录（保留你的连接器） | 全表面 |
| `/topup` | — | 显示你的 Nous 余额并在门户上管理账单 | 全表面 |
| `/insights` | — | 显示用量洞察和分析 | 全表面 |
| `/platforms` | `/gateway` | 显示 gateway/消息平台状态 | CLI |
| `/platform` | — | 暂停、恢复或列出故障的 gateway 平台 | Gateway |

---

## Exit — 退出

| 命令 | 别名 | 作用 | 可用表面 |
|------|------|------|---------|
| `/quit` | `/exit` | 退出 CLI（使用 `--delete` 同时删除会话历史） | CLI |

---

## 关键概念

### Busy Policy（忙碌策略）

命令在 agent 运行时（忙碌中）的行为由 `busy_policy` 控制：

| 策略 | 含义 |
|------|------|
| `reject` | 拒绝执行（通用 "Agent is running" 消息） |
| `dispatch` | 在忙碌时仍然运行（正常处理器或 `busy_handler` 变体） |
| `interrupt_then_dispatch` | 先中断 agent（类似 `/stop`），然后执行 |

### CLI Only vs Gateway Only

| 标记 | 含义 |
|------|------|
| `cli_only=True` | 仅在 CLI 中可用 |
| `gateway_only=True` | 仅在 gateway/消息平台中可用 |
| `gateway_config_gate` | 当指定的 config.yaml 路径为真时，CLI-only 命令也可在 gateway 使用 |

### Desktop 可用性

| 值 | 含义 |
|----|------|
| `None` | 正常提供 |
| `"hidden"` | 可运行但不在弹出窗口中显示 |
| `"terminal"` | 仅通过嵌入终端使用 |
| `"messaging"` | 仅通过消息功能使用 |
| `"settings"` | 在设置面板中 |
| `"advanced"` | 在高级面板中 |
| 其他字符串 | 不可用的原因 |

---

## 命令数量统计

```
总计：约 90 个规范命令（不含别名）
别名：约 30+ 个别名
子命令：部分命令有丰富的子命令（如 /kanban 有 30+ 子命令）
```

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `hermes_cli/commands.py` | 命令注册表 `COMMAND_REGISTRY`，`resolve_command()`，帮助文本生成 |
| `hermes_cli/cli_commands_mixin.py` | CLI 表面的命令处理器实现 |
| `hermes_cli/commands_completion.py` | 命令补全和自动建议 |
| `hermes_cli/commands_platforms.py` | 平台特定命令列表（Telegram/Discord/Slack） |
| `tui_gateway/methods_tools.py` | TUI 表面的命令处理（`_cmd_*` 函数） |
| `tui_gateway/slash_worker.py` | TUI 斜杠命令工作进程 |
| `gateway/run_inbound.py` | Gateway 表面的命令处理 |
| `gateway/slash_commands_*.py` | Gateway 斜杠命令处理器 mixins |
