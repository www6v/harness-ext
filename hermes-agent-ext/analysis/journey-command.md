# /journey 命令深度分析

## 概述

`/journey` 是 Hermes Agent 的学习可视化命令，以时间线的形式展示 agent 随时间积累的学习成果——已学习的技能（learned skills）和记忆片段（memories）。它是桌面端 Star Map / Memory Graph 的终端版本，提供时间线柱状图（按日期分行，技能/记忆条按类别着色）+ 累积轨迹火花线 + 可交互的节点管理（查看/编辑/删除）。

> "A terminal rendition of the desktop Star Map / Memory Graph: a timeline bar chart of learned skills and memories over time (oldest at top, newest at bottom) plus a playable constellation scrubber."

---

## 架构设计

### 数据流架构

```
┌─────────────────────────────────────────────────────────────┐
│                    数据来源                                   │
│                                                              │
│  ~/.hermes/skills/          ~/.hermes/memories/              │
│  (SKILL.md files)           (MEMORY.md, USER.md)             │
│  skills/.usage.json                                          │
└──────────┬───────────────────────┬──────────────────────────┘
           │                       │
           ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐
│  learning_graph.py   │  │  learning_mutations  │
│                      │  │                      │
│  build_skill_nodes() │  │  node_detail()       │
│  build_edges()       │  │  edit_node()         │
│  build_learning_     │  │  delete_node()       │
│    graph()           │  │                      │
└──────────┬───────────┘  └──────────────────────┘
           │
           ▼
┌──────────────────────────┐
│  learning_graph_render.py│
│                          │
│  render_graph()          │── 终端时间线渲染
│  render_frames()         │── 预渲染完整动画帧序列
│  derive_palette()        │── 色彩系统（桌面端移植）
│  compute_recency()       │── 时间轴 recency 计算
└──────────┬───────────────┘
           │
     ┌─────┼─────────────────────────────┐
     ▼     ▼                             ▼
  CLI     TUI RPC                    Dashboard API
  journey  learning.frames           /api/learning/*
  (Rich)  (methods_tools.py)        (web_routers/status.py)
                                        │
                                        ▼
                                   TUI Ink
                                   (journey.tsx)
```

### 核心设计原则

1. **纯函数渲染**：渲染层（`learning_graph_render.py`）是纯 stdlib 的——无外部依赖，输入 payload → 输出 grid（style runs），可在任何表面复用。
2. **桌面端移植**：色彩系统（`derive_palette`）、recency 计算（`compute_recency`）、age gradient 全部从桌面端 TypeScript 源码移植，保持视觉一致性。
3. **节点双类型**：技能（`●`）和记忆（`◆`）作为图的第一类节点，通过词法重叠自动建立 memory↔skill 边。

---

## 核心模块分析

### 1. `agent/learning_graph.py` — 学习图构建

#### 数据模型

```python
@dataclass
class SkillNode:
    name: str              # 技能名称
    category: str          # 类别（如 "research", "dev-tools"）
    source: str            # "base" 或 "profile"
    timestamp: Optional[int]  # 最后活动时间（epoch seconds）
    use_count: int         # 使用次数
    state: str             # "active", "archived", ...
    created_by: Optional[str]  # "agent", "learn", None
    pinned: bool           # 是否被用户固定
    related: list[str]     # 声明的相关技能列表
```

#### 节点构建（`build_skill_nodes`）

扫描两个技能根目录：
- `("base", <hermes-agent>/skills/)` — 内置技能
- `("profile", ~/.hermes/skills/)` — 用户学习的技能

对每个 `SKILL.md` 文件：
1. 读取前 4000 字符，解析 frontmatter（name, category, related_skills）
2. 从 `skills/.usage.json` 加载使用记录（last_activity_at, use_count, created_by, pinned）
3. 时间戳优先级：`last_activity_at` → `last_used_at` → `last_viewed_at` → `last_patched_at` → `created_at` → 文件 mtime

#### 学习信号过滤（`_has_learning_signal`）

只有满足以下条件的技能才进入学习图：
- `created_by == "agent"` — agent 自主创建
- `created_by == "learn"` — 用户通过 `/learn` 创建
- `use_count > 0` — 至少被使用过一次

内置技能（`source == "base"`）被排除——图只展示用户的学习轨迹。

#### 边的构建

两类边：

1. **skill↔skill 边**：来自 SKILL.md frontmatter 中声明的 `related_skills`，两端节点都必须存在（去重，首次出现顺序）

2. **memory↔skill 边**：基于词法重叠自动推导
   - 将 `MEMORY.md` / `USER.md` 按 `§` 分隔符切分为记忆卡片
   - 对每张卡片，计算与所有技能的 token 交集分数
   - 技能名称出现在记忆文本中权重为 6
   - 每张记忆卡片取 top-4 最高分技能建立边

#### 记忆卡片（`_memory_cards`）

```python
# MEMORY.md 和 USER.md 按 § 分隔符切分
for chunk_idx, chunk in enumerate(c.strip() for c in text.split("\n§\n")):
    cards.append({
        "source": source,        # "memory" 或 "profile"
        "timestamp": file_ts + chunk_idx,
        "title": first_line[:80],
        "body": chunk[:1200],
    })
```

#### 完整图负载（`build_learning_graph`）

返回一个完整的 dict，包含：
- `nodes`: 技能节点 + 记忆节点（统一格式）
- `edges`: skill 边 + memory-skill 边
- `clusters`: 按类别分组的计数
- `memory`: 记忆卡片列表
- `stats`: 图统计（节点数、边数、孤立节点比例、agent 创建数、使用数、top 类别等）

### 2. `agent/learning_graph_render.py` — 终端渲染器

这是一个完全移植自桌面端 TypeScript 的渲染引擎，纯 stdlib，无外部依赖。

#### 色彩系统

**调色板推导**（`derive_palette`）：从桌面端 `color.ts::computePalette` 移植

```python
def derive_palette(primary_hex: str, *, dark: bool = True) -> dict[str, str]:
    return {
        "primary": primary_hex,
        "memory": rgb_to_hex(mix_rgb(primary, base, 0.12)),    # 主色调混合 → 可点击色
        "skill": rgb_to_hex(mix_rgb(complement, bg, 0.45)),    # 互补色混合 → 柔和色
        "label": rgb_to_hex(mix_rgb(base, bg, 0.35)),
        "dim": rgb_to_hex(mix_rgb(base, bg, 0.7)),
        "bg": rgb_to_hex(bg),
    }
```

设计理念：记忆是可下钻的 → 使用主色调"可点击"色；技能是终端节点 → 使用柔和互补色。

**类别颜色映射**（`category_color_map`）：黄金角（137.508°）间隔的色相分布，确保相邻类别颜色不会碰撞。

**Age Gradient**（`recency_ink`）：从桌面端 `geometry.ts::recencyInk` 移植
- 旧节点：低亮度（0.42）
- 中间过渡：smoothstep 插值
- 新节点：高亮度（0.95）

#### Recency 计算（`compute_recency`）

从桌面端 `time-axis.ts::computeRecency` 移植：
- 有时间戳跨度时：按时间比例映射到 [0, 1]
- 无时间戳跨度时：回退到序号位置（每个节点仍有不同的 recency）
- 应用 `LEAD_IN`（0.06）偏移：最旧节点稍微偏离 recency 0

#### 时间线柱状图（`render_graph`）

渲染一帧时间线图：

1. **分桶**（`_build_chart_buckets`）：
   - 优先选最细日期粒度（day → month → year）适配行数限制
   - 短跨度保留逐日图（≤32 天不折叠）
   - 溢出时回退到均匀时间分桶

2. **柱状条**（`_bar_lengths`）：
   - 每个桶的条长度按总数/最大值比例缩放
   - 技能部分用 `━` 填充，颜色按桶的主导类别着色（学习热力图）
   - 记忆部分用 `◆...◆` 框包围
   - 标记 peak（最大值桶）和 now（最后桶）

3. **标签行**：每个桶最多标记 1 个最重要的节点（按 score 排序），编号 `1-9a-c`

4. **轨迹火花线**（`_trajectory_row`）：
   - 累积学习曲线，用 `·` 和 `✦` 绘制
   - 展示从旧到新的学习进度

#### Grid 格式

渲染输出是 style runs 的 grid：

```python
Row = list  # [text, style_key, alpha, hex_override?]
```

消费者将 `style` + `alpha` 映射到调色板颜色；`hex_override` 覆盖基础颜色（类别热力图）。这种抽象让渲染器完全主题无关。

#### 预渲染帧序列（`render_frames`）

```python
def render_frames(payload, *, cols=80, rows=16, frames=48) -> dict:
    # 预渲染 reveal 0→1 的完整帧序列
    # 附加：legend, categories, buckets (树形元数据), summary, axis
```

TUI 的 Ink 组件消费预渲染的帧序列，在本地实现可交互的时间线树浏览。

### 3. `agent/learning_mutations.py` — 节点变更

提供学习图节点的 CRUD 操作，被 CLI、TUI、Desktop 共享：

| 操作 | 技能行为 | 记忆行为 |
|------|---------|---------|
| **detail** | 读取 SKILL.md 全文 | 读取 § 分隔的 chunk |
| **edit** | 调用 `_edit_skill` 重写 SKILL.md | 替换对应 chunk 并重写文件 |
| **delete** | 归档（`archive_skill`），可通过 `hermes curator restore` 恢复 | 删除 chunk 并重写文件 |

**节点 ID 约定：**
- 技能：技能名称（如 `"search-arxiv"`）
- 记忆：`memory:<source>:<index>`（如 `memory:memory:0`, `memory:profile:2`）

**固定保护**：被 pin 的技能不可删除（先 unpin），自主维护（curator, background review）同样跳过 pinned 技能。

**原子写入**：记忆文件通过 `MemoryStore._write_file` 使用临时文件 + rename 实现原子写入，并发读取不会看到半写状态。

### 4. `hermes_cli/journey.py` — CLI 表面

使用 Rich 库渲染完整的终端界面：

#### 渲染层次

```
┌─ Title ─────────────────────────────────────────┐
│  ✦ Journey · learned skills & memories over time │
│                                                   │
│  Legend:  ● skills (N)   ◆ memories (N)          │
│  Categories: ● research (3)  ● dev-tools (2) ... │
│                                                   │
│  ┌─ Timeline Chart ──────────────────────────┐   │
│  │  Jan 2024 │━━━━━●━━━━━  3+1    ◀ now      │   │
│  │  Dec 2023 │━━━●━━━      2                 │   │
│  │  Nov 2023 │━━●━━         1                │   │
│  │             ·  ·  ✦  trajectory            │   │
│  └──────────────────────────────────────────┘   │
│  ◷ 15 Jan 2024   6/6 revealed · 100%           │
│                                                   │
│  charted signals                                  │
│  1 ● search-arxiv    research · 15 Jan · x3      │
│  2 ◆ Deploy config   profile memory · 12 Jan     │
│                                                   │
│  6 learned skills · 2 memories · 3 skill links   │
│  1 memory↔skill links · busiest day 15 Jan · 3   │
└───────────────────────────────────────────────────┘
```

#### 对比度保护（`_ensure_contrast`）

标记的节点标签必须保持 WCAG 对比度（≥4.5:1），如果 age tinting 使标签太暗，自动向可读极点（黑/白）方向调整。

#### 动画播放（`_play`）

```python
def _play(console, payload, *, cols, rows, color, fps):
    with Live(console=console, refresh_per_second=fps) as live:
        for i in range(42):
            reveal = i / 41
            live.update(_frame_renderable(payload, ..., reveal=reveal))
            time.sleep(1.0 / fps)
```

通过 Rich 的 `Live` 组件实现动画效果，reveal 从 0 到 1 逐步揭示时间线。

#### CLI 子命令

```bash
hermes journey                    # 显示时间线
hermes journey --play             # 动画播放
hermes journey --json             # 输出原始 JSON
hermes journey list               # 列出所有节点 ID
hermes journey delete <node_id>   # 删除/归档节点
hermes journey edit <node_id>     # 在 $EDITOR 中编辑节点
```

### 5. TUI 表面

#### RPC 方法（`tui_gateway/methods_tools.py`）

```python
# 预渲染帧序列供 Ink 组件消费
@_rpc("learning.frames", 5000, "learning.frames failed: ")
def _(rid, params):
    graph = build_learning_graph()
    return _ok(rid, render_frames(graph, cols, rows, frames))

# 节点变更
for _name, _fn, _keys in (
    ("detail", "node_detail", ("id",)),
    ("delete", "delete_node", ("id",)),
    ("edit", "edit_node", ("id", "content")),
):
    _rpc(f"learning.{_name}", ...)(_learning_mutation(_fn, _keys))
```

#### Ink 组件（`ui-tui/src/components/journey.tsx`）

TypeScript 实现的可交互时间线树：
- 消费 Python 后端预渲染的 frames + buckets
- 每个时间切片（slice）可展开查看其中的技能/记忆节点
- 支持节点编辑（调用 `openInEditor`）和删除
- 使用 `ScrollBox` 实现滚动，`useInput` 处理键盘交互
- 色彩系统通过 `deriveStarmapPalette` 从 Python 端移植的调色板驱动

### 6. Dashboard API（`hermes_cli/web_routers/status.py`）

```python
GET    /api/learning/graph    # 完整学习图负载
GET    /api/learning/node     # 节点详情（编辑预填）
DELETE /api/learning/node     # 删除/归档节点
PUT    /api/learning/node     # 编辑节点内容
```

所有 API 都在 profile scope 下运行（`scoped_to_thread`），确保多 profile 环境中的隔离。

---

## 节点 ID 系统

学习图的节点有两种 ID 格式：

| 类型 | ID 格式 | 示例 |
|------|---------|------|
| 技能 | 技能名称 | `search-arxiv` |
| 记忆 | `memory:<source>:<index>` | `memory:memory:0`, `memory:profile:2` |

记忆索引的含义：
- `source` 是 `memory`（MEMORY.md）或 `profile`（USER.md）
- `index` 是全局索引（MEMORY.md 卡片排在前面，USER.md 卡片紧随其后）
- 内部通过 `_locate_memory` 转换为文件内的局部索引

---

## 统计与可视化

### 图统计（`density_stats`）

| 指标 | 含义 |
|------|------|
| `nodes` | 已学习技能数 |
| `related_edges` | 技能间声明的关系数 |
| `edges_per_node` | 平均连边密度 |
| `isolated_pct` | 孤立节点百分比（无关系） |
| `agent_created` | agent 自主创建的技能数 |
| `used` | 至少使用过一次的技能数 |
| `top_categories` | 前 8 大类别 |
| `memory_nodes` | 记忆卡片数 |
| `memory_skill_edges` | 记忆↔技能自动关联数 |

### 可视化元素

| 元素 | 含义 | 来源 |
|------|------|------|
| `●` | 技能节点 | NODE_SHAPE（桌面端） |
| `◆` | 记忆节点 | NODE_SHAPE（桌面端） |
| `━` 条（技能色） | 该时段的技能数，颜色按主导类别 | 学习热力图 |
| `◆━◆` 条（记忆色） | 该时段的记忆数 | 记忆墨水 |
| `✦` 轨迹 | 累积学习进度 | trajectory sparkline |
| `☄ peak` | 学习最密集的时段 | 峰值标记 |
| `◀ now` | 当前时间 | 时间轴末端 |
| Age gradient | 旧→暗，新→亮 | `recencyInk` 移植 |

---

## 设计亮点

1. **桌面端→终端的高保真移植**：色彩系统、recency 计算、age gradient 全部从 TypeScript 源码精确移植，保持了跨表面的一致性。

2. **纯函数渲染管道**：`build_learning_graph()` → `render_frames()` 是完全无副作用的函数链，可测试、可复用、可跨表面共享。

3. **自动记忆-技能关联**：不需要用户手动建立连接，基于词法重叠自动推导 memory↔skill 边，name hit 权重 6 确保精确匹配优先。

4. **安全的节点变更**：技能删除是归档（可恢复）、记忆删除是原子文件重写、固定技能有保护——所有操作都通过 profile scope 隔离。

5. **渐进式时间粒度**：自动选择最细的日期粒度（day → month → year）适配显示行数，短跨度保留逐日细节。

6. **Style runs 抽象**：渲染器输出 `[text, style_key, alpha, hex?]` 元组，消费者自行映射到实际颜色——同一个 grid 数据结构驱动 Rich（CLI）、Ink（TUI）和桌面端。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `agent/learning_graph.py` | 学习图构建：节点、边、统计 |
| `agent/learning_graph_render.py` | 终端渲染器：时间线、色彩、recency |
| `agent/learning_mutations.py` | 节点 CRUD：detail / edit / delete |
| `hermes_cli/journey.py` | CLI 表面：Rich 渲染、动画、子命令 |
| `hermes_cli/subcommands/journey.py` | CLI 子命令注册 |
| `tui_gateway/methods_tools.py` | TUI RPC：`learning.frames` / `learning.*` |
| `tui_gateway/contracts/tools_mcp_plugins.py` | 渲染数据的 TypeScript 类型声明 |
| `ui-tui/src/components/journey.tsx` | TUI Ink 组件：可交互时间线树 |
| `hermes_cli/web_routers/status.py` | Dashboard API：`/api/learning/*` |
| `tools/skill_usage.py` | 技能使用记录（usage stats） |
| `tools/memory_tool_store.py` | 记忆存储（MemoryStore） |
| `tools/skill_manager_tool.py` | 技能管理（`_find_skill`, `_edit_skill`） |
