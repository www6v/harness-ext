# Skill 系统分析

## 一、Skill 是什么

Skill 是 deepseek-harness 中**可复用的任务指令集**（reusable task-specific instructions）。每个 skill 由一个 kebab-case 名称标识，包含 Markdown 格式的指令体（body），可以让模型在需要时按需加载并遵循。

Skill 名称格式：`^[a-z0-9]+(?:-[a-z0-9]+)*$`（纯 kebab-case）。

### Skill 文件格式

Skill 以 Markdown 文件存储，必须包含 YAML 前置元数据（frontmatter）：

```markdown
---
name: my-skill
description: A short description of what this skill does
whenToUse: Optional guidance on when to use this skill
disable-model-invocation: false   # 是否禁止模型调用（可选，默认 false）
user-invocable: true              # 是否用户可调用（可选，默认 true）
metadata:                         # 可选的元数据对象
  key: value
---
# Skill 指令内容 (Markdown)
具体的操作指令...
```

- **`name`**（必填）：kebab-case 名称
- **`description`**（必填）：简短路由描述
- **`whenToUse`**（可选）：额外的使用指导
- **`disable-model-invocation`**（可选）：设为 `true` 禁止模型调用
- **`user-invocable`**（可选）：设为 `false` 禁止用户通过 `/name` 调用
- **`metadata`**（可选）：任意键值对元数据

### Skill 文件存储方式

支持两种存储方式：

| 方式 | 路径格式 | 说明 |
|------|----------|------|
| 目录包 (Directory Bundle) | `<name>/SKILL.md` | 目录名即为 skill 名称，可附带资源文件 |
| 扁平文件 (Flat File) | `<name>.md` | 文件名（去掉 .md）即为 skill 名称 |

## 二、Skill 系统架构

Skill 系统由四个核心包组成：

| 包 | 角色 | 说明 |
|----|------|------|
| `packages/skill/skill` | **服务定义** (Service Definition) | 核心 `SkillRegistry`，定义所有接口和类型 |
| `packages/skill/skill-filesystem` | **服务提供者** (Service Provider) | 从本地文件系统发现和加载 skill |
| `packages/skill/skill-badge` | **可选 Provider** | 提供一个内置的 `dsh-badge` skill |
| `packages/skill/tool-skill` | **消费者** (Consumer) | 模型可见的 `skill` 工具，会话目录管理，用户 `/name` 调用 |

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      tool-skill (Consumer)                   │
│  ┌──────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │ skill({name})    │  │ 会话目录注入    │  │ /name 用户调用│ │
│  │ 模型调用工具      │  │ <available_    │  │ pre-step      │ │
│  │                  │  │  skills>        │  │ 注入          │ │
│  └────────┬─────────┘  └───────┬────────┘  └──────┬───────┘ │
└───────────┼────────────────────┼──────────────────┼─────────┘
            │                    │                  │
            ▼                    ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   SkillRegistry (ctx.skills)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ list()       │  │ get()        │  │ snapshot()       │  │
│  │ 列出所有 skill│  │ 加载完整定义  │  │ 带完整性标记的快照│  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │             │
│         ▼                 ▼                    ▼             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │               Layered Discovery (ScopedLayers)        │   │
│  │  Global Layer → Scope Chain (farthest → nearest)      │   │
│  │  同名 skill: 最近层胜出；同层内 rank 低者胜出           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│              SkillProvider (可扩展接口)                       │
│  ┌────────────────────┐  ┌──────────────────────────────┐   │
│  │ skill-filesystem   │  │ skill-badge (可选)            │   │
│  │ 本地文件系统扫描     │  │ 内置打包 skill                │   │
│  └────────────────────┘  └──────────────────────────────┘   │
│  ┌────────────────────┐  ┌──────────────────────────────┐   │
│  │ 自定义 Provider    │  │ runtime register()           │   │
│  │ 远程 Registry 等   │  │ 运行时动态注册                │   │
│  └────────────────────┘  └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 三、Skill 加载与注册流程

### 3.1 SkillProvider 接口

所有 skill 来源都通过 `SkillProvider` 接口接入：

```typescript
interface SkillProvider {
  readonly name: string  // 唯一 provider 名称

  // 列出可用 skill 候选
  readonly list: (options: SkillLookupOptions) =>
    Promise<readonly SkillCandidate[] | SkillProviderObservation>

  // 加载完整 skill 定义
  readonly get: (candidate: SkillCandidate, options: SkillLookupOptions) =>
    Promise<SkillDefinition | undefined>
}
```

- **`list()`**：发现阶段，返回 `SkillCandidate` 列表（摘要，不含 body）
- **`get()`**：加载阶段，返回包含 `content` 的完整 `SkillDefinition`
- `SkillProviderObservation` 支持不完整发现（`complete: false`），此时快照不会被缓存

### 3.2 Provider 注册

在 Cordis 插件 `apply()` 阶段同步注册：

```typescript
// 注册 provider
ctx.skills.registerProvider((control) => {
  return new MySkillProvider(control)
})

// 注册运行时 skill（动态注入）
ctx.skills.register({
  name: 'my-custom-skill',
  description: 'A dynamically injected skill',
  content: '# Instructions...',
  source: 'custom',
})
```

### 3.3 分层发现模型 (ScopedLayers)

Skill 注册遵循与 tools registry 相同的 **host+per-scope 分层模型**：

```
Global Layer (全局)
  └── Agent Preset Scope Layer (agent 预设层)
       └── Nested Scope Layer (嵌套层)
```

- 外层 skill 对读可见；**最近层（nearest layer）的同名 skill 胜出**
- 同一层内按 `rank` 排序（值越小优先级越高），rank 相同时按 provider 注册顺序
- `registerProvider()` 注册到**调用 context 的 scope 层**：
  - 非 scoped context → 全局层
  - agent preset 的 standing composition 中的 plugin → 该 preset 层
- `register()` 运行时注册同理，支持 scope 隔离

### 3.4 文件系统 Provider 发现优先级

`skill-filesystem` 作为默认 provider，按以下优先级扫描 skill 目录：

| Rank | Source | 根路径 | 说明 |
|------|--------|--------|------|
| 100 | `project-dsh` | `<projectRoot>/.dsh/skills` | 项目级 dsh 目录 |
| 200 | `project-agents` | `<projectRoot>/.agents/skills` | 项目级 agent 目录 |
| 300 | `custom` | `Config.customSkillDirs` | 自定义目录 |
| 400 | `user-dsh` | `<dshHome>/skills` | 用户级 dsh 目录 |
| 500 | `user-agents` | `<agentsHome>/skills` | 用户级 agent 目录 |
| 600 | `bundled` | `Config.bundledSkillDir` | 打包内置 skill |

- 项目根 (projectRoot)：最近包含 `.git` 的祖先目录
- `dshHome`：默认 `$DSH_HOME` 或 `~/.dsh`
- `agentsHome`：默认 `$DSH_AGENTS_HOME` 或 `~/.agents`
- 用户 dsh 根跳过 `.system` 子目录

### 3.5 文件变更监听

`skill-filesystem` 使用 **Chokidar** 监听 skill 目录变更：

- 监听事件：`add`、`addDir`、`change`、`unlink`、`unlinkDir`
- 支持稳定性阈值 (`watchStabilityThresholdMs`，默认 200ms)
- 支持轮询模式 (`watchUsePolling`)
- 支持符号链接跟随 (`watchFollowSymlinks`)
- 最大项目数限制 (`watchMaxProjects`，默认 128，LRU 驱逐)
- 缺失根目录逐级向上寻找最近存在的祖先目录进行监听
- 模型 `write`/`edit` 操作同步触发 provider 失效

### 3.6 发现缓存

- 缓存键由 `{ cwd, scopes[], revision }` 组成
- 可配置缓存条目数上限 (`collectCacheMaxEntries`，默认 128)
- 不完整快照从不缓存
- Provider 注册/注销、运行时注册/注销、文件变更均触发缓存失效
- 发现过程中 revision 变更会重试一次；二次变更返回不完整结果

## 四、Skill 调用方式

### 4.1 模型调用 — `skill` 工具

tool-skill 向模型注册一个 `skill` 工具：

```
工具名: skill
参数: { name: string }  — kebab-case skill 名称
```

**调用流程**：

1. 模型在 `<available_skills>` 目录中看到可用 skill 名称和描述
2. 模型调用 `skill({ name: "my-skill" })`
3. tool-skill 验证名称格式 → 查找 skill → 检查 `modelInvocable` 策略 → 加载完整定义
4. 返回 `<skill_content>` 包含 `<skill_resources>` 和 `<skill_instructions>`

**返回格式**：

```xml
<skill_content name="my-skill">
<skill_resources>
Base directory for this skill: /path/to/skill/dir
Resolve relative paths mentioned by this skill against the base directory before using them.
</skill_resources>

<skill_instructions>
# 实际 skill 指令内容
...
</skill_instructions>
</skill_content>
```

### 4.2 用户调用 — `/name` 语法

用户在对话中输入 `/<skill-name>` 触发直接调用：

- 扫描 `source.kind === 'user'` 的消息中的 `/name` 模式
- 正则：`/(^|\s)\/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)/g`
- 检查 `userInvocable` 策略
- 将 skill body 作为注入的 `instructions` 形式上下文追加到当前 step
- 注入源的 `kind` 为 `'skill-invocation'`，含 `name` 和 `form: 'instructions'`
- 模型收到 `<skill_content>` 块后**不应再调用 `skill` 工具**

**安全边界**：
- 只有 `source.kind === 'user'` 的消息被扫描
- `/usr/bin` 和 `5/8` 等路径/分数不会被误匹配
- 不存在的 skill 名称保持为普通文本

### 4.3 会话 Skill 目录

tool-skill 在每个 session 的第一步注入 `<system-reminder>` 包含可用 skill 列表：

```
<system-reminder>
A skill is a reusable set of task-specific instructions.
The following skills are available in this session:

<available_skills>
- `skill-a`: Description of skill A
- `skill-b`: Description of skill B
</available_skills>

If the user names a skill, or the task clearly matches a skill's description,
call the `skill` tool with the exact skill name before taking task actions.
...
</system-reminder>
```

- 仅列出 `modelInvocable: true` 的 skill
- 仅含 `name` 和截断的 `description`（默认最大 500 字符）
- Skill 变更时发出完整的替换目录消息
- 目录消息 source 为 `{ kind: 'skill-catalog', form: 'catalog', entries: [...] }`
- 目录比较基于 entry 摘要而非渲染文本

### 4.4 浏览器端 Skill 目录

`SessionSkillCatalog` 提供 `ctx.remote.skills` Remote 接口：

```typescript
@Remote async list(request: SkillListRequest, signal: AbortSignal): Promise<SkillListValue>
```

- 通过 sessionId 查询，无需激活 Agent
- 返回 `userInvocable: true` 的 skill 列表
- 包含 `name`、`description`、`whenToUse`、`modelInvocable` 字段
- 支持 Live Agent 的 scoped registry 和 Cold Session 的 preset standing scope

## 五、Skill 来源与目录约定

### 5.1 SkillSource 类型

```typescript
type SkillSource =
  | 'project-dsh'     // 项目 .dsh/skills/ 目录
  | 'project-agents'  // 项目 .agents/skills/ 目录
  | 'runtime'         // 运行时 ctx.skills.register()
  | 'user-dsh'        // 用户 ~/.dsh/skills/ 目录
  | 'user-agents'     // 用户 ~/.agents/skills/ 目录
  | 'custom'          // 自定义目录 (Config.customSkillDirs)
  | 'bundled'         // 打包内置 (Config.bundledSkillDir)
  | (string & {})     // 扩展预留
```

### 5.2 完整目录结构示例

```
项目根/
├── .dsh/
│   └── skills/
│       ├── my-project-skill.md          # 项目 skill (扁平文件)
│       └── code-review/                 # 项目 skill (目录包)
│           ├── SKILL.md
│           └── templates/
├── .agents/
│   └── skills/
│       └── custom-agent.md

用户目录/
├── ~/.dsh/
│   └── skills/
│       ├── my-personal-skill.md
│       └── .system/                     # 被跳过
└── ~/.agents/
    └── skills/
        └── shared-skill.md
```

## 六、仓库中的实际 Skill

deepseek-harness 仓库本身包含 **15+ 个实际 skill**，存放在 `.agents/skills/` 目录下：

- `dsh-code-review` — 代码审查
- `dsh-doc` — 文档编写
- `dsh-prose-standard` — 文案标准
- `dsh-ci-test-reliability` — CI 测试可靠性
- `dsh-find-simplifications` — 寻找简化
- `dsh-merging-stacked-prs` — 合并堆叠 PR
- `dsh-translate-docs` — 文档翻译
- `dsh-trim-cot-leakage` — 裁剪思维链泄露
- `dsh-speed-up-perf` — 性能加速
- `dsh-archive-agent-notes` — 归档 Agent 笔记
- `dsh-pre-push-checks` — 推送前检查
- `record-browser-gif` — 录制浏览器 GIF

### `.claude/skills` 符号链接

仓库中存在一个 symlink：

```
.claude/skills → ../.agents/skills
```

这使得 Claude Code 也能直接发现并使用本仓库的 skill，实现了两个 Agent 框架之间的 skill 共享。

### 跨产品 Skill 元数据对齐脚本

`scripts/verify-skill-invocation-metadata.ts` 用于交叉校验：

- 检查 `.agents/skills/` 中的 skill 在 Claude Code frontmatter 和 Codex `agents/openai.yaml` 之间是否有一致的调用策略
- Claude 的 `disable-model-invocation: true` ↔ Codex 的 `policy.allow_implicit_invocation: false`
- 确保人工专用 skill 保持 `user-invocable: true`

### 设计演进历史

Skill 系统经历了多次迭代，设计文档见 `.agents/notes/` 目录：

| 设计笔记 | 内容 |
|----------|------|
| `2026-07-05-skill-system.md` | 原始 skill 系统设计 |
| `2026-07-21-tui-skill-slash-command.md` | TUI 斜杠命令 |
| `2026-07-27-skill-catalog-hot-refresh.md` | 目录热刷新 |
| `2026-07-28-skill-invocation-policy.md` | 调用策略实现 |
| `2026-07-28-dsh-guided-skill-session-commands.md` | 引导式 skill 会话命令 |
| `2026-08-06-bundled-dsh-badge-skill.md` | 内置 badge skill |
| `2026-08-06-web-skill-tool-row.md` | Web UI skill 工具行 |
| `2026-08-08-user-explicit-skill-invocation.md` | 用户显式调用 |
| `2026-08-09-layered-skill-registry.md` | 分层注册表 ADR (架构决策记录) |

## 七、Skill 调用策略 (InvocationPolicy)

每个 skill 有两个独立的布尔控制：

```typescript
interface SkillInvocationPolicy {
  readonly modelInvocable: boolean  // 模型能否通过 skill 工具调用
  readonly userInvocable: boolean   // 用户能否通过 /name 调用
}
```

四种组合：

| modelInvocable | userInvocable | 效果 |
|:---:|:---:|------|
| ✅ | ✅ | 模型和用户均可调用（默认） |
| ✅ | ❌ | 仅模型可调用，用户 `/name` 无效 |
| ❌ | ✅ | 仅用户可通过 `/name` 调用，模型 `skill` 工具看不到 |
| ❌ | ❌ | 两者均不可调用（仅 `ctx.skills.get()` 内部使用） |

**前置元数据映射**：
- `disable-model-invocation: true` → `modelInvocable: false`
- `user-invocable: false` → `userInvocable: false`
- 省略时均为默认值 `true`

## 八、能否上传 Skill？

### 8.1 直接远程上传 API：❌ 不支持

deepseek-harness **没有提供远程 skill 文件上传的 HTTP API**。与文件上传（有 `POST /api/session/uploadFileBinary` 端点）不同，系统中不存在 `POST /api/skill/upload` 或类似的 skill 上传端点。

### 8.2 等效能力：✅ 三种替代方案

虽然没有直接的远程上传 API，但有以下等效方式实现 skill 下发：

#### 方案 A：自定义 SkillProvider（推荐，适合集中式 skill 管理）

实现一个从远程注册中心获取 skill 的 `SkillProvider`：

```typescript
class RemoteSkillProvider implements SkillProvider {
  readonly name = 'remote-registry'

  async list(options: SkillLookupOptions): Promise<SkillCandidate[]> {
    // 从远程 API 获取 skill 列表
    const response = await fetch('https://skill-registry.example.com/api/skills')
    return (await response.json()).map(skill => ({
      name: skill.name,
      description: skill.description,
      source: 'custom',
      provider: this.name,
      rank: 100,
      locator: skill.id,
      invocation: { modelInvocable: true, userInvocable: true },
    }))
  }

  async get(candidate: SkillCandidate): Promise<SkillDefinition | undefined> {
    const response = await fetch(
      `https://skill-registry.example.com/api/skills/${candidate.locator}`
    )
    const skill = await response.json()
    return {
      name: skill.name,
      description: skill.description,
      content: skill.markdownContent,
      source: 'custom',
      provider: this.name,
      invocation: { modelInvocable: true, userInvocable: true },
    }
  }
}

// 在 plugin apply() 中注册
ctx.skills.registerProvider((control) => new RemoteSkillProvider())
```

**优点**：完全控制 skill 发现和加载逻辑，支持远程 registry、数据库、API 等任何后端。

#### 方案 B：运行时注册（适合动态注入）

```typescript
ctx.skills.register({
  name: 'dynamic-skill',
  description: 'A dynamically injected skill from remote',
  content: '# Instructions\n...',  // 从远程获取的 Markdown 内容
  source: 'custom',
})
```

**优点**：轻量，无需实现完整 Provider 接口。  
**限制**：注册到调用 context 的 scope 层；同层同名 skill 先到先得。

#### 方案 C：文件系统写入 + 自动发现

将 skill 文件写入被 `skill-filesystem` 监听的目录：

```
项目 .dsh/skills/     → 项目级
用户 ~/.dsh/skills/   → 用户级
自定义目录             → 通过 Config.customSkillDirs 配置
```

文件系统 watcher 会自动检测新增/修改并触发 catalog 更新。

### 8.3 与 Claude Code 的对比

| 能力 | Claude Code | deepseek-harness |
|------|-------------|------------------|
| 远程文件上传 API | ✅ | ✅ |
| 远程 Skill 上传 API | ❌ | ❌ |
| Skill Provider 扩展机制 | ✅ (通过 hook/plugin) | ✅ (通过 SkillProvider 接口) |
| 运行时 Skill 注册 | ✅ | ✅ (ctx.skills.register) |
| 文件系统自动发现 | ✅ (.claude/skills/) | ✅ (.dsh/skills/, .agents/skills/) |
| 文件变更监听 | ✅ | ✅ (Chokidar) |
| 用户 `/name` 调用 | ✅ | ✅ |
| 模型 `skill` 工具 | ✅ | ✅ |
| 分层隔离 (scope) | ❌ | ✅ (ScopedLayers) |

## 九、关键文件索引

| 文件 | 说明 |
|------|------|
| `packages/skill/skill/src/index.ts` | SkillRegistry 核心实现 |
| `packages/skill/skill-filesystem/src/index.ts` | 本地文件系统 Provider |
| `packages/skill/skill-badge/src/index.ts` | 内置 dsh-badge skill Provider |
| `packages/skill/tool-skill/src/index.ts` | skill 工具 + 会话目录 + /name 调用 |
| `packages/api/session-controller/src/skill-catalog.ts` | 浏览器端 skill 目录 Remote 接口 |
| `packages/api/session-controller/src/types.ts` | SkillListRequest/Value 等类型定义 |
| `docs/subsystems/skills.md` | Skill 子系统官方文档 |
| `docs/config-catalog.md` | Config 参数说明 |

## 十、总结

deepseek-harness 的 Skill 系统是一个**成熟的、可扩展的指令管理框架**：

1. **Provider 模式**：通过 `SkillProvider` 接口实现可插拔的 skill 来源，默认本地文件系统 provider 扫描项目、用户和自定义目录
2. **分层隔离**：基于 ScopedLayers 实现 Agent/Agent Preset 级别的 skill 隔离和覆盖
3. **双通道调用**：模型通过 `skill` 工具按需加载，用户通过 `/name` 语法直接触发
4. **文件监听**：Chokidar 实时监听 skill 目录变更，自动更新目录
5. **灵活策略**：每个 skill 可独立控制模型调用和用户调用的开关
6. **可扩展上传**：虽然没有直接远程上传 API，但通过自定义 `SkillProvider` 或运行时注册可实现等效的远程 skill 分发