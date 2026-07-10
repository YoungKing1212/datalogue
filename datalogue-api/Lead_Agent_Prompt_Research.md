# Lead Agent 提示词设计深度调研报告

**调研范围**: DeerFlow、Pi Agent、OpenClaw、Hermes Agent
**调研日期**: 2026-07-10

---

## 一、核心结论：为什么他们的 Agent "聪明"，你的"笨"

这不是模型的问题，是**提示词工程体系**的差距。优秀框架的 Lead Agent 聪明，是因为它们做对了以下关键设计：

| 设计要素 | 你的 Agent（常见错误） | 优秀框架的做法 |
|---------|---------------------|--------------|
| **思考引导** | 没有，Agent 直接开干 | 显式定义 `<thinking_style>`，要求先分析再行动 |
| **任务分解** | 靠模型自己悟 | 硬编码分解检查 + 批次规划 + 并发限制 |
| **澄清机制** | Agent 猜测用户意图 | 强制"先澄清→再计划→再执行" workflow |
| **技能加载** | 全部塞进 prompt | 渐进式加载，只在需要时加载对应 skill |
| **提示词分层** | 所有指令混在一起 | 分层架构：系统级 → 项目级 → 任务级 → 个性级 |
| **Few-shot 示例** | 只有抽象描述 | 提供具体输入/输出示例校准行为 |
| **工具管控** | 越多越好 | 每个 Agent 最多 5 个工具，消除语义重叠 |
| **记忆注入** | 向量检索一堆无关内容 | 结构化置信度评分 + 分类保证 |

---

## 二、四大框架 Lead Agent 提示词架构拆解

### 2.1 DeerFlow — 最完善的编排级提示词体系

#### 2.1.1 系统提示词模板结构

DeerFlow 的 `SYSTEM_PROMPT_TEMPLATE` 是一个精心设计的分层模板，按以下顺序组装：

```
<role>                     → 基础身份定义
<system-reminder>          → 动态注入的记忆和日期
<thinking_style>           → ★ 思考方式引导（关键！）
<clarification_system>     → ★ 澄清优先 workflow（关键！）
<skill_system>             → 渐进式技能加载
<subagent_system>          → 子 Agent 编排规则
<working_directory>        → 工作环境说明
<response_style>           → 输出风格要求
<citations>                → 引用规范
<critical_reminders>       → ★ 关键规则强化（关键！）
```

#### 2.1.2 思考风格引导（`<thinking_style>`）

这是 DeerFlow 最聪明的设计之一。它在系统提示词中显式要求模型**按特定方式思考**：

```markdown
<thinking_style>
- Think concisely and strategically about the user's request BEFORE taking action
- Break down the task: What is clear? What is ambiguous? What is missing?
- **PRIORITY CHECK: If anything is unclear, missing, or has multiple interpretations, 
  you MUST ask for clarification FIRST - do NOT proceed with work**
- **DECOMPOSITION CHECK: Can this task be broken into 2+ parallel sub-tasks? 
  If YES, COUNT them.**
- Never write down your full final answer or report in thinking process, 
  but only outline
- CRITICAL: After thinking, you MUST provide your actual response to the user. 
  Thinking is for planning, the response is for delivery.
</thinking_style>
```

**核心洞察**：DeerFlow 不是在告诉 Agent "做什么"，而是在告诉 Agent **"怎么想"**。它要求模型在每一步都进行：
1. **优先级检查** — 先确认需求是否清晰
2. **分解检查** — 任务能否并行化
3. **计数检查** — 显式计数子任务数量

#### 2.1.3 澄清优先系统（`<clarification_system>`）

DeerFlow 的澄清系统是 Agent "不笨" 的关键防线：

```markdown
**WORKFLOW PRIORITY: CLARIFY → PLAN → ACT**

1. FIRST: Analyze the request - identify what's unclear, missing, or ambiguous
2. SECOND: If clarification is needed, call ask_clarification tool IMMEDIATELY
3. THIRD: Only after all clarifications are resolved, proceed

**MANDATORY Clarification Scenarios:**
1. Missing Information → 必须澄清
2. Ambiguous Requirements → 必须澄清  
3. Approach Choices → 必须澄清
4. Risky Operations → 必须确认
5. Suggestions → 必须确认
```

**关键设计**：它用 **STRICT ENFORCEMENT** 规则列表强化：
- ❌ DO NOT start working and then ask for clarification mid-execution
- ❌ DO NOT skip clarification for "efficiency"
- ❌ DO NOT make assumptions when information is missing
- ✅ If you identify the need for clarification in your thinking, 
  you MUST call the tool IMMEDIATELY

#### 2.1.4 子 Agent 编排系统（`<subagent_system>`）

DeerFlow 的子 Agent 编排提示词是业界最详细的：

```markdown
**🚀 SUBAGENT MODE ACTIVE - DECOMPOSE, DELEGATE, SYNTHESIZE**

**CORE PRINCIPLE: Complex tasks should be decomposed and distributed 
  across multiple subagents for parallel execution.**

**⛔ HARD CONCURRENCY LIMIT: MAXIMUM {n} `task` CALLS PER RESPONSE.**
```

**编排策略包含**：
1. ✅ **DECOMPOSE + PARALLEL EXECUTION** — 复杂查询分解并行
2. ❌ **DO NOT use subagents** — 简单任务直接执行
3. **CRITICAL WORKFLOW** — 严格执行：计数 → 计划批次 → 执行 → 重复 → 综合

**每个示例都包含**：
- 输入示例（用户说什么）
- 思考过程（Agent 怎么想）
- 执行模式（单批次/多批次/直接执行）
- 代码示例（具体 tool call）

#### 2.1.5 关键规则强化（`<critical_reminders>`）

DeerFlow 在提示词末尾重复关键规则，形成"首尾呼应"：

```markdown
<critical_reminders>
- **Clarification First**: ALWAYS clarify unclear requirements BEFORE starting work
- **Orchestrator Mode**: You are a task orchestrator - decompose complex tasks
  **HARD LIMIT: max {n} `task` calls per response.**
- Skill First: Always load the relevant skill before starting complex tasks
- File Editing Workflow: prefer str_replace over write_file
</critical_reminders>
```

#### 2.1.6 动态组装机制

```python
def apply_prompt_template(subagent_enabled, max_concurrent_subagents, ...):
    # 1. 记忆上下文（从磁盘读取最新状态）
    memory_context = _get_memory_context(agent_name)
    
    # 2. 子 Agent 章节（仅在启用时生成）
    subagent_section = _build_subagent_section(n) if subagent_enabled else ""
    
    # 3. 关键提醒注入（编排者角色 + 批次限制）
    subagent_reminder = "- **Orchestrator Mode**: ..." if subagent_enabled else ""
    
    # 4. 思考引导注入（分解检查）
    subagent_thinking = "- **DECOMPOSITION CHECK**: ..." if subagent_enabled else ""
    
    # 5. 技能列表（从文件系统实时扫描）
    skills_section = get_skills_prompt_section(available_skills)
    
    # 6. 填入主模板
    prompt = SYSTEM_PROMPT_TEMPLATE.format(...)
    
    # 7. 追加当前日期（防止过期日期认知）
    return prompt + f"\n<current_date>{datetime.now().strftime('%Y-%m-%d, %A')}</current_date>"
```

**设计要点**：
- 记忆和日期是**每轮动态注入**（保持前缀缓存复用）
- 技能列表是**实时扫描**（反映最新安装状态）
- 子 Agent 规则是**条件注入**（仅在启用时出现）

---

### 2.2 OpenClaw — 最优雅的分层提示词架构

#### 2.2.1 四级提示词分层

OpenClaw 的核心创新是**提示词分层**，每层职责单一：

| 层级 | 文件 | 职责 | 加载时机 | 每次注入 |
|------|------|------|---------|---------|
| 系统提示词 | 内置 | 核心行为、安全、工具定义 | 每次会话 | 是 |
| AGENTS.md | 项目级 | 项目特定行为 | 每会话 | 是 |
| SKILL.md | 任务级 | 任务特定工作流 | Skill 触发时 | 按需 |
| SOUL.md | 个性级 | 个性和沟通风格 | 每会话 | 是 |

**总字符上限**：150,000 字符（约 8 个 bootstrap 文件 × 20K）

#### 2.2.2 AGENTS.md 设计哲学

AGENTS.md 是 OpenClaw 最高杠杆的文件，设计原则是：

> "像给新承包商的操作手册，不是产品描述"

**最佳实践**：
- **保持 < 500 字** — 避免信号稀释
- 包含角色定义、任务分解模式、显式输出格式、失败处理
- 使用 **CRAFT 框架**：Context → Role → Action → Format → Tone
- 使用 **Few-shot 示例**：2-3 个具体输入/输出示例比段落更有效

**示例**：
```markdown
# AGENTS

## Workflow
1. Pull: Scrape by source and keyword.
2. Filter: Deduplicate, filter by excluded words, layer by credibility.
3. Structure: Title, time, entity, event type, affected parties, original link.
4. Summary: Summarize in 3 sentences + "Why it's relevant to you".
5. Alerting: Highlight when thresholds hit.

## Output template
- Today's Must-Reads (<=5)
- Industry News (<=8)
- One-sentence verdict
```

#### 2.2.3 系统提示词核心结构

```
Base Identity → "You are a personal assistant running inside OpenClaw"
Tooling → 工具可用性列表（带权限过滤）
Tool Call Style → "Default: do not narrate routine tool calls"
CLI Quick Reference → OpenClaw 子命令速查
Skills → 扫描可用 skills，选择最匹配的读取
Memory Recall → "回答前先搜索 memory"
Self-Update → 仅用户明确要求时才允许
Workspace → 工作目录信息
Documentation → 本地文档优先
User Identity → 用户身份信息
Current Date & Time → 时区信息
Reply Tags → 消息回复标签
Messaging → 消息路由规则
Silent Replies → "HEARTBEAT_OK" 机制
Heartbeats → 主动检查机制
Runtime → 运行时元数据（模型、通道、能力）
Project Context → SOUL.md, IDENTITY.md, USER.md, AGENTS.md, TOOLS.md
```

#### 2.2.4 记忆系统设计

OpenClaw 的记忆系统极简但有效：

```
~/.openclaw/
├── memory/
│   ├── YYYY-MM-DD.md      # 每日记忆
│   └── ...
├── MEMORY.md              # 长期记忆（主要 session）
├── SOUL.md                # 个性定义
├── IDENTITY.md            # 身份定义
└── USER.md                # 用户信息
```

**设计原则**：
- 记忆就是文件 — 没有向量数据库，没有嵌入
- Agent 读取 `memory/YYYY-MM-DD.md` 获取近期上下文
- Agent 读取 `MEMORY.md` 获取长期记忆
- Agent 主动更新这些文件积累知识

#### 2.2.5 Heartbeat 机制

这是 OpenClaw 的"主动性"来源：

```
每 30 分钟（可配置）:
1. Gateway 注入心跳消息
2. Agent 读取 HEARTBEAT.md
3. Agent 检查：邮件？日历？天气？提及？
4. 无事 → 回复 HEARTBEAT_OK（被抑制，用户看不到）
5. 有事 → 主动发送提醒给用户
```

**关键**：`HEARTBEAT_OK` 必须是**整条的、唯一的**消息，不能附加其他内容。

---

### 2.3 Pi Agent — 极简主义的胜利

#### 2.3.1 核心设计哲学

Pi Agent 走了完全相反的路线 — **极简**：

| 特性 | Claude Code | Pi Agent |
|------|------------|----------|
| 系统提示词 | ~24,000 tokens | < 1,000 tokens |
| 内置工具 | 18+ | 4 (read, write, edit, bash) |
| 理念 | 详细提示词覆盖边界情况 | 现代模型已被 RL 训练得很强 |

Mario Zechner（Pi 作者）的观点：
> "现代编码模型已经在 Agent 任务上经过了如此多的 RL 训练，庞大的系统提示词主要只是增加了 token 开销。"

#### 2.3.2 提示词层级

```
~/.pi/agent/
├── SYSTEM.md              # 覆盖全局系统提示词
├── APPEND_SYSTEM.md       # 追加到系统提示词
├── AGENTS.md              # 全局指令
├── prompts/               # 提示词模板
│   └── *.md               # /name 触发
└── extensions/            # 扩展
```

**项目级 AGENTS.md** 从以下位置加载：
1. `~/.pi/agent/AGENTS.md`（全局）
2. 父目录（从 cwd 向上遍历）
3. 当前目录

#### 2.3.3 上下文工程（Context Engineering）

Pi 强调"上下文工程"而非"提示词工程"：

- **Compaction**：接近上下文限制时自动总结旧消息
- **Skills**：能力包，按需加载（Progressive disclosure）
- **Prompt Templates**：可复用的 Markdown 提示词，/name 触发
- **Dynamic Context**：扩展可在每轮前注入消息

#### 2.3.4 Skill 设计模式

Pi 的 Skill 加载策略是**渐进披露**（Progressive Disclosure）：

```
1. 仅在需要时加载相关 skill
2. 不破坏 prompt cache
3. 首次启动时选择相关 skills（后续可编辑）
4. 只将相关 skills 保留在 prompt 中
```

---

### 2.4 Hermes Agent — 最规范化的编排手册

#### 2.4.1 Kanban Orchestrator 分解手册

Hermes 的编排器有一个详细的**反诱惑规则集**（anti-temptation rules）：

```markdown
## Decomposition Playbook

### Step 1 — Understand the goal
Ask clarifying questions if the goal is ambiguous. 
Cheap to ask; expensive to spawn the wrong fleet.

### Step 2 — Sketch the task graph
BEFORE creating anything, draft the graph out loud.

1. Extract the lanes from the request
2. Map each lane to a profile
3. Decide whether each lane is independent or gated
4. Create independent lanes as parallel cards
5. Create synthesis/review cards with parent links
```

#### 2.4.2 "分解，不执行"原则

这是 Hermes 编排器的核心纪律：

> "Your whole job is routing. Decompose, don't execute."

编排器只做三件事：
1. 理解目标
2. 草拟任务图
3. 分配给合适的 worker

**绝不亲自执行任务**。

#### 2.4.3 依赖关系管理

Hermes 对任务依赖有精细的定义：

```markdown
Words like "also," "finally," or "and" do NOT automatically imply 
a dependency. They often mean "make sure this is covered before 
reporting back." Only link tasks when one card cannot start until 
another card's output exists.
```

**示例**：
- "Build an app" → 设计卡片 + 工程卡片 + 后续审查卡片
- "Fix blockers and check model variants" → 实现卡片 + 研究卡片 + 审查卡片
- "Research docs and implement" → 研究可与发现并行，实现等待研究结果

#### 2.4.4 Agent Team Orchestrator

Hermes 有一个专门的 **agent-team-orchestrator** 项目，定义了完整的 AI 团队结构：

```
决策/协调通道：
  - Orchestrator（编排者）
  - Product Owner（产品负责人）
  - System Architect（系统架构师）
  - Reviewer / Senior Engineer（审查者）

执行通道：
  - Frontend Engineer（前端工程师）
  - Backend Engineer（后端工程师）
  - AI Engineer（AI 工程师）
  - QA Engineer（QA 工程师）
  - DevOps / Platform（运维）
```

**交接契约**（Handoff Contracts）：
- 明确的角色边界
- 单一事实来源文档
- 标准化的交接协议
- 变更请求流程
- 审查和集成关卡

---

## 三、关键设计模式总结：让 Agent "聪明" 的 10 个秘诀

### 秘诀 1：定义思考方式，不只是任务

❌ **错误做法**：
```markdown
You are a helpful assistant. Help users with their tasks.
```

✅ **正确做法**（DeerFlow 风格）：
```markdown
<thinking_style>
- Break down the task: What is clear? What is ambiguous? What is missing?
- **PRIORITY CHECK: If anything is unclear, MUST ask for clarification FIRST**
- **DECOMPOSITION CHECK: Can this task be broken into 2+ parallel sub-tasks?**
- After thinking, you MUST provide your actual response. 
  Thinking is for planning, the response is for delivery.
</thinking_style>
```

### 秘诀 2：强制"先澄清，再执行"

❌ **错误做法**：Agent 猜测用户意图，做错了再改

✅ **正确做法**（DeerFlow 风格）：
```markdown
**WORKFLOW PRIORITY: CLARIFY → PLAN → ACT**

**STRICT ENFORCEMENT:**
- ❌ DO NOT start working and then ask for clarification mid-execution
- ❌ DO NOT skip clarification for "efficiency" - accuracy matters more than speed
- ❌ DO NOT make assumptions when information is missing - ALWAYS ask first
- ✅ Analyze → Identify unclear aspects → Ask BEFORE any action
```

### 秘诀 3：每个 Agent 最多 5 个工具

> "如果任何 Agent 有超过 5 个工具，拆分它。这比任何提示词工程技术都有效。"

来自生产环境调优经验：
- 减少工具数量 consistently 产生比任何提示词工程更大的准确率提升
- 运行工具描述的相似度评分
- 如果有两个工具描述重叠，重命名以提高区分度，或将一个移到不同 Agent

### 秘诀 4：渐进式技能加载

❌ **错误做法**：启动时加载所有 skills，挤爆上下文

✅ **正确做法**：
```markdown
**Progressive Loading Pattern:**
1. When a user query matches a skill's use case, immediately call read_file 
   on the skill's main file
2. Read and understand the skill's workflow and instructions
3. Load referenced resources ONLY when needed during execution
4. Follow the skill's instructions precisely
```

### 秘诀 5：分层提示词架构

OpenClaw 的四层架构是最佳实践：

```
系统提示词（框架定义）
    ↓
AGENTS.md（项目行为，< 500 字）
    ↓
SKILL.md（任务工作流，按需加载）
    ↓
SOUL.md（个性风格，可选）
```

**每层职责单一，不重复**。

### 秘诀 6：Few-shot 示例 > 抽象描述

❌ **错误做法**：
```markdown
For complex tasks, break them down into smaller sub-tasks.
```

✅ **正确做法**（DeerFlow 风格）：
```markdown
**Example 1: "Why is Tencent's stock price declining?" (3 sub-tasks)**
→ Turn 1: Launch 3 subagents in parallel:
  - Subagent 1: Recent financial reports, earnings data, revenue trends
  - Subagent 2: Negative news, controversies, regulatory issues
  - Subagent 3: Industry trends, competitor performance, market sentiment
→ Turn 2: Synthesize results
```

### 秘诀 7：硬编码限制，不依赖模型自律

DeerFlow 的 `SubagentLimitMiddleware` 是典范：

```python
# 不是让模型自律，而是用代码硬执行
middlewares.append(SubagentLimitMiddleware(max_concurrent=3))
```

**在提示词中也要重复**：
```markdown
**⛔ HARD CONCURRENCY LIMIT: MAXIMUM 3 `task` CALLS PER RESPONSE.**
- Each response, you may include at most 3 task tool calls
- Any excess calls are SILENTLY DISCARDED by the system
```

### 秘诀 8：首尾呼应的关键规则

在系统提示词**开头和结尾**都注入关键规则：

```markdown
# 开头（在 thinking_style 中）
- **DECOMPOSITION CHECK: Can this task be broken into 2+ parallel sub-tasks?**

# 结尾（在 critical_reminders 中）
- **Orchestrator Mode**: decompose complex tasks into parallel sub-tasks
  **HARD LIMIT: max 3 `task` calls per response**
```

**原理**：模型对提示词的开头和结尾注意力最高，中间容易"lost in the middle"。

### 秘诀 9：编排者只做编排，不做执行

Hermes 的 "decompose, don't execute" 原则：

```markdown
You are an orchestrator profile whose whole job is routing.
- Understand the goal
- Sketch the task graph
- Route to appropriate workers
- NEVER do the work yourself
```

### 秘诀 10：主动性设计（Heartbeat）

OpenClaw 的 Heartbeat 机制让 Agent 从被动变主动：

```
每 30 分钟:
1. Agent 检查 HEARTBEAT.md
2. 检查待办事项、日历、提醒
3. 无事 → HEARTBEAT_OK（静默）
4. 有事 → 主动提醒用户
```

---

## 四、四框架对比矩阵

| 维度 | DeerFlow | OpenClaw | Pi Agent | Hermes |
|------|----------|----------|----------|--------|
| **定位** | 超级 Agent 编排框架 | 个人 AI 助手网关 | 极简编码 Agent | 自进化 Agent 引擎 |
| **多 Agent** | ✅ 动态子 Agent | ✅ 子 Agent 会话 | ❌ 单 Agent | ✅ Kanban worker |
| **编排模式** | Lead Agent + 并行 Sub-agent | 顺序阶段 + Skill 路由 | 单 Agent 循环 | 编排器 + Worker |
| **提示词长度** | 长（完整模板） | 中（分层加载） | 极短（<1K tokens） | 中（Skill 手册） |
| **技能系统** | 渐进式 Markdown Skill | ClawHub 社区 Skill | 渐进式 Skill 包 | 118 内置 Skill |
| **记忆系统** | 结构化 memory.json | 文件-based Memory | 会话搜索 | 3 层持久记忆 |
| **学习进化** | ❌ | ❌ | ❌ | ✅ 自我生成 Skill |
| **思考引导** | ✅ `<thinking_style>` | ❌ 隐性 | ❌ 极简 | ✅ 分解手册 |
| **澄清机制** | ✅ 强制 clarify-first | ⚠️ 依赖 AGENTS.md | ❌ | ⚠️ 第一步建议 |
| **沙箱** | ✅ Docker 隔离 | 直接宿主机 | 宿主机 | 硬件沙箱 |
| **适合场景** | 复杂长时任务 | 个人日常自动化 | 编码辅助 | 团队协作+自学习 |

---

## 五、实用建议：如何改进你的 Agent

### 立即可以做的 5 件事

1. **添加 `<thinking_style>` 到你的系统提示词**
   - 要求模型在行动前分析：什么清晰？什么模糊？缺什么？

2. **实施"先澄清再执行"**
   - 定义 5 种必须澄清的场景
   - 在提示词中强制执行 CLARIFY → PLAN → ACT

3. **限制每个 Agent 的工具数量到 5 个**
   - 检查工具描述是否有语义重叠
   - 重叠的拆分到不同 Agent

4. **添加 Few-shot 示例**
   - 为你最常见的 3-5 种任务模式添加具体示例
   - 包含输入、思考过程、输出

5. **实施硬限制而非依赖模型自律**
   - 用代码截断超过限制的 tool call
   - 在提示词中声明限制并警告后果

### 中期改进（1-2 周）

6. **建立分层提示词架构**
   - 分离系统级、项目级、任务级指令
   - 每层 < 500 字

7. **实施渐进式技能加载**
   - Skill 只在触发时加载
   - 使用 `/skill-name` 显式激活

8. **添加编排级分解检查**
   - 在关键位置注入 DECOMPOSITION CHECK
   - 要求模型显式计数子任务

9. **建立记忆注入系统**
   - 结构化记忆（带置信度评分）
   - 分类保证（保证关键类别始终注入）

10. **添加 Heartbeat/主动检查机制**
    - 定期让 Agent 检查待办和提醒
    - 从被动响应进化到主动提醒

---

## 六、参考资源

| 资源 | 链接 |
|------|------|
| DeerFlow GitHub | https://github.com/bytedance/deer-flow |
| DeerFlow 系统提示词源码 | backend/packages/harness/deerflow/agents/lead_agent/prompt.py |
| OpenClaw 文档 | https://docs.openclaw.ai |
| Pi Agent GitHub | https://github.com/earendil-works/pi |
| Hermes Agent 文档 | https://hermes-agent.ai |
| OpenClaw System Prompt 研究 | https://github.com/seedprod/openclaw-prompts-and-skills |
| Agent Team Orchestrator | https://github.com/danilo1003/agent-team-orchestrator |
| DeerFlow vs OpenClaw 讨论 | https://github.com/bytedance/deer-flow/discussions/3139 |

---

*报告完*
