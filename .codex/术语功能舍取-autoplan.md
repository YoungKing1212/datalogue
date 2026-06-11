<!-- /autoplan restore point: 新建计划文件，无历史内容可恢复 -->

# /autoplan 计划：专业术语功能舍取与边界评审

Captured: 2026-06-11 | Branch: main | Commit: 822cabe

## Original Plan State

用户问题：

> 确定术语功能舍取，是否与分析蓝图、指标、维度、知识库等功能有冲突，是否有存在的必要性

## 目标

判断 Datalogue 当前“专业术语 / 业务术语”能力是否应该继续作为独立功能存在，或应降级为支撑分析蓝图、指标、维度、字段和知识库的底层语义能力。

## 当前已知现状

- 数据集能力页中，“业务术语”和“分析蓝图”都作为能力 Tab 展示。
- 业务术语当前支持 CRUD、AI 发现、冲突检测、同义词、禁用词、示例问法和关联资产。
- 分析蓝图当前支持从 SQL、存储过程或手工业务步骤生成蓝图，审核参数和输出列，测试后发布到问数链路。
- 问数运行时已存在术语归一化节点，用于同义词命中、冲突澄清和向下游 DSL/SQL 注入术语结果。
- 问数入口分类中，已发布分析蓝图优先于知识解释类业务术语命中。

## 待评审问题

1. 业务术语与分析蓝图是否职责重叠？
2. 业务术语与指标、维度是否重复维护口径？
3. 业务术语与知识库问答是否重复？
4. 如果保留业务术语，应保留哪些能力？
5. 如果弱化业务术语，应如何调整页面信息架构？
6. 是否需要迁移已有术语数据或改变后端模型？

## 初始假设

- 分析蓝图是用户可感知的分析能力，应作为一级核心功能保留。
- 指标和维度是可执行 SQL 语义口径，应继续作为结构化语义资产保留。
- 业务术语不应承担完整分析流程，也不应成为主要用户工作台。
- 业务术语仍可能在别名归一、口径澄清、知识解释和资产关联中有基础设施价值。

## 候选方案

### 方案 A：完整保留业务术语一级入口

继续保留现有业务术语 Tab、CRUD、AI 发现、冲突检测和关联资产工作台。

### 方案 B：保留模型和运行时，弱化一级入口

业务术语降级为“语义词典 / 别名与口径”，隐藏或弱化独立工作台；保留术语归一化、冲突检测、知识解释和关联资产能力；在蓝图、指标、维度、字段配置中内嵌术语维护。

### 方案 C：删除业务术语功能

删除业务术语管理入口和运行时归一化，把相关能力合并到分析蓝图、指标、维度、知识库中。

## Phase 1 / CEO Review：前提挑战

### 0A. Premise Challenge

| 前提 | 判断 | 证据 | 风险 |
|---|---|---|---|
| “已经有分析蓝图，所以术语可能没必要” | 部分成立 | 分析蓝图已经覆盖触发问法、业务场景、参数、输出列、业务逻辑、测试发布和运行时命中 | 如果直接删术语，会丢失别名归一、同名冲突澄清和知识解释 |
| “业务术语是一个独立用户功能” | 不成立 | 当前术语真正有价值的位置在 QueryGraph、语义资产解析、解释包和澄清卡片，而不是独立工作台 | 继续作为一级 Tab 会让用户误以为要重复维护蓝图、指标、维度口径 |
| “术语和指标/维度是重复的” | 部分成立 | AI 发现术语直接从 metric、dimension、column 生成候选；指标和维度自身也有 synonyms/description | 如果保留完整术语 CRUD，会形成重复口径入口 |
| “术语和知识库是重复的” | 当前不完全重复 | 知识解释路径现在主要依赖业务术语定义直答，尚未成为完整知识库检索 | 若后续引入真正知识库，术语应成为结构化词条，不应替代知识库 |

### 0B. Existing Code Leverage

| 子问题 | 已有代码 | 结论 |
|---|---|---|
| 术语模型和资产关联 | `BusinessTerm`、`BusinessTermAssetLink`、`BusinessTermRelation`、`BusinessTermChangeLog` | 保留模型，避免破坏历史数据和运行时链路 |
| 术语管理 API | `/api/dataset/{ds_id}/terms...` | 可保留 API，但前端入口降级 |
| 候选术语发现 | `discover_terms` 从指标、维度、字段生成候选 | 改为蓝图/指标/维度编辑过程中的辅助建议，而不是主按钮 |
| 蓝图执行 | `entry_intent_classification_node` 先命中 active 蓝图，`analysis_blueprint_execute_node` 执行或转语义计划 | 蓝图应继续是用户主路径 |
| 术语归一化 | `term_normalize_node` 做确定性匹配、冲突澄清、注入 `entities.terms` | 保留运行时节点 |
| 知识解释 | `_match_business_term` 基于术语定义直答 | 短期保留，长期作为知识库结构化词条来源 |
| 语义资产解析 | `semantic_asset_resolution_node` 统一解析 terms/metrics/dimensions/fields/blueprints | 保留术语作为一种底层资产类型 |

### 0C. Dream State Mapping

```text
CURRENT STATE
业务术语、指标、维度、分析蓝图并列展示；术语既像知识库，又像指标别名，又像蓝图辅助资产。

THIS PLAN
术语从一级业务功能降级为“语义词典 / 别名与口径”；用户主要创建分析蓝图、指标、维度，系统顺手沉淀术语。

12-MONTH IDEAL
用户看见的是“可问什么、可分析什么、口径是否可信”；术语在后台支撑召回、澄清、解释和审计，不要求普通用户主动维护。
```

### 0C-bis. Implementation Alternatives

#### Approach A：完整保留业务术语工作台

- Effort: S
- Risk: Medium
- Completeness: 6/10
- Pros:
  - 最少改动，现有页面、API、模型和测试基本不动。
  - 对数据治理人员仍然有完整维护入口。
- Cons:
  - 继续与分析蓝图、指标、维度形成产品感知重叠。
  - 用户会继续困惑“我到底应该维护术语还是蓝图”。
  - AI 发现术语会重复从已有指标/维度/字段再造一层资产。
- Reuses:
  - 复用当前 `renderTermsPanel`、terms API、`term_normalize_node`。

#### Approach B：保留模型和运行时，弱化一级入口（推荐）

- Effort: M
- Risk: Low-Medium
- Completeness: 9/10
- Pros:
  - 保留术语在别名归一、冲突澄清、知识解释、资产关联中的真实价值。
  - 避免和分析蓝图抢主路径，让蓝图成为用户可感知的分析能力。
  - 不需要删库、不破坏已有 API，可分阶段上线和回滚。
- Cons:
  - 需要调整前端信息架构和文案。
  - 需要把“AI 发现术语”改造成蓝图/指标/维度编辑中的辅助动作。
  - 需要补充测试防止隐藏入口后运行时链路退化。
- Reuses:
  - 复用 `BusinessTerm` 数据模型、terms API、QueryGraph 术语归一化、术语澄清卡片。

#### Approach C：删除业务术语功能

- Effort: L
- Risk: High
- Completeness: 4/10
- Pros:
  - 页面最简洁，少一个治理入口。
  - 短期减少用户认知负担。
- Cons:
  - 会破坏 `term_normalize_node`、知识解释、语义资产解析、语义验证报告和术语澄清。
  - 需要迁移或废弃历史术语数据，风险远高于收益。
  - 指标/维度/蓝图无法完全替代“跨资产别名”和“同词多义澄清”。
- Reuses:
  - 仅复用指标、维度、蓝图自身 synonyms/trigger words，丢弃术语模型。

**Recommendation:** 选择 Approach B。它把业务术语保留为底层语义基础设施，同时降低用户主路径噪音；这是当前代码和产品方向下收益/风险比最高的方案。

## 评审输出要求

- 明确最终推荐方案。
- 列出应保留、应合并、应移除或隐藏的功能。
- 给出与分析蓝图、指标、维度、知识库的边界表。
- 给出前端和后端改造任务。
- 给出验证方式和残留风险。

## 用户确认

2026-06-11：用户确认选择 Approach B：保留模型和运行时，弱化一级入口。

## Plan Design Review：Step 0 设计范围审计

### Pre-review Findings

- UI scope: 有明确 UI 范围，涉及数据集能力页、业务术语工作台、分析蓝图向导、语义验证报告和聊天术语澄清卡片。
- `DESIGN.md`: 未发现项目级 `DESIGN.md`，本次评审按现有前端组件模式和通用可用性原则校准。
- Design tooling: 当前环境未发现 gstack designer binary，因此暂不生成视觉 mockup；后续若工具可用，应补 3 个信息架构变体。
- Existing patterns: 复用 `capabilityTabs`、`semantic-tab-panel`、`blueprint-wizard`、`GuidedEmpty`、`StatCard`、`btn`、`BlueprintWizardStepper` 等现有组件模式。
- Retrospective signal: 近期提交包含语义验证、术语澄清和术语归一化链路，说明本计划不能只做页面隐藏，必须保留运行时可解释性和澄清闭环。
- Prior design reviews: 未发现本项目 gstack `reviews.jsonl` 记录。

### 0A. Initial Design Rating

当前设计完整度：7/10。

计划已经说明了“术语降级为语义基础设施”的产品判断，也列出了要调整的入口、文案和验证点；但还缺少更具体的信息架构落位、空状态、错误状态、移动端/窄屏行为、候选术语交互细节，以及高级治理入口如何被发现。

达到 10/10 需要补齐：

- 数据集能力 Tab 的最终分组方案：哪些是主路径，哪些进入高级治理。
- “语义词典 / 别名与口径”入口的具体位置、名称和权限可见性。
- 蓝图向导中“建议别名与口径”的出现时机、默认展开状态、接受/忽略/冲突状态。
- 术语为空、候选重复、冲突检测失败、terms API 409、蓝图保存失败等状态。
- 语义验证报告和聊天澄清卡片保留后的视觉层级，避免再次把术语变成主噪音。

### 0B. DESIGN.md Status

No design system found。建议后续单独沉淀 `DESIGN.md` 或产品设计规则；本轮先按现有 Datalogue 前端模式推进，不引入新的视觉语言。

### 0C. Existing Design Leverage

- 数据集能力页已经有 `capabilityTabs` 和 `capability-route`，适合改造成“主路径 + 高级治理”的信息架构，不需要新建独立导航。
- 业务术语面板已经有冲突检测、AI 发现、搜索过滤、详情和空状态，适合整体迁入高级治理，而不是拆散重写。
- 分析蓝图向导已有 4 步结构，最适合在第 2 步“确认 AI 生成的蓝图草稿”加入候选别名与口径，而不是在第 1 步增加输入负担。
- 语义验证报告已经展示术语命中和蓝图命中，适合保留为调试/验收证据，而不是在主操作页强调。
- 聊天侧已有术语澄清卡片，必须作为运行时用户补救路径保留。

### 0D. Focus Gate

下一步需要选择设计评审重点。推荐先评审全部 7 个维度，但重点压在信息架构、用户旅程、交互状态覆盖三个维度。

## CEO Review：最终产品判断

### 核心结论

专业术语功能有存在必要，但不应继续作为和分析蓝图并列的一级业务能力展示。

它的正确定位是“语义词典 / 别名与口径基础设施”，支撑以下能力：

- 普通问数中的别名归一。
- 同名或同义词冲突时的口径澄清。
- 命中术语后扩展关联指标、维度、字段和蓝图。
- 知识解释类问题的结构化词条来源。
- 语义验证报告中的术语命中和冲突风险展示。

它不应该承担以下职责：

- 不承担完整分析流程。
- 不替代分析蓝图。
- 不替代指标表达式和维度枚举。
- 不替代完整知识库检索。
- 不要求普通用户像维护主业务对象一样单独维护术语库。

### 与现有能力的边界表

| 能力 | 用户问题 | 系统职责 | 是否与术语冲突 | 术语应扮演的角色 |
|---|---|---|---|---|
| 分析蓝图 | “运行毛利归因分析”“为什么本月毛利下降” | 固化复杂分析路径、参数、输出列、业务逻辑、测试发布和运行时执行 | 有产品感知冲突，但工程职责不同 | 提供蓝图触发词、参数别名、输出列口径的辅助词典，不作为主入口 |
| 指标 | “销售额是多少”“GMV 趋势” | 定义可编译 SQL 的聚合表达式、过滤条件、时间字段和展示格式 | 与 metric_concept 类术语高度重叠 | 指标是执行口径；术语只提供别名、解释和跨资产关联 |
| 维度 | “按区域/门店/部门拆分” | 定义可 group/filter 的维度字段、枚举和值域解释 | 与 business_object / dimension_enum 类术语部分重叠 | 维度是可查询字段；术语只提供自然语言别名和枚举解释 |
| 字段标注 | “人员名称”“合同金额” | 标注物理字段语义、角色、样例和值域 | 与术语候选来源重叠 | 字段是数据资产；术语是字段被用户叫法的别名层 |
| 知识库问答 | “什么是有效客户”“GMV 是什么口径” | 回答定义、制度、业务背景和解释材料 | 当前短期依赖术语定义，有重叠 | 术语作为结构化词条，长期应接入完整知识库材料 |
| 语义验证 | “这条问法会命中什么资产” | 验证路由、术语命中、蓝图命中、SQL 和失败原因 | 不冲突 | 术语命中是验证报告的关键观测项 |

### NOT in scope

- 不删除 `BusinessTerm`、`BusinessTermAssetLink`、`BusinessTermRelation`、`BusinessTermChangeLog` 表。
- 不移除 `/api/dataset/{ds_id}/terms...` API。
- 不删除 `term_normalize_node`、术语冲突澄清、知识解释命中和语义资产解析中的 `terms`。
- 不把所有术语迁移成指标/维度 synonyms；那会丢失定义、禁用词、跨资产关联和冲突语义。
- 不在本阶段实现完整知识库检索；只保留术语定义直答作为过渡。

### Scope Decisions

| # | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|
| 1 | 选择 Approach B：保留模型和运行时，弱化一级入口 | User confirmed | Explicit over clever | 既解决产品混乱，又避免破坏 QueryGraph 运行时链路 | A 继续重叠；C 风险过高 |
| 2 | 将“业务术语”产品命名降级为“语义词典 / 别名与口径” | Auto | DRY | 避免与蓝图、指标、维度重复表达“业务能力” | 保持“业务术语”一级命名 |
| 3 | 保留冲突检测，但从主工作台动作转为治理/高级能力 | Auto | Completeness | 冲突检测是术语不可替代价值，不应删除 | 删除冲突检测 |
| 4 | 蓝图创建流程吸收候选术语确认 | Auto | Bias toward action | 用户创建蓝图时顺手确认别名，比单独维护术语库更自然 | 继续要求单独进入术语 Tab |

## Design Review：信息架构方案

### App UI 分类

这是数据集治理与智能问数后台，属于 APP UI，不是营销页。设计目标是降低认知负担，让用户第一眼知道“主要该配置什么能力”。

### 信息架构评分

| Pass | 当前评分 | 目标评分 | 主要问题 | 修正 |
|---|---:|---:|---|---|
| 信息架构 | 5/10 | 9/10 | 业务术语、分析蓝图、指标、维度同级，用户难以判断主路径 | 蓝图、指标、维度保留主路径；术语并入语义治理/高级设置 |
| 交互状态 | 6/10 | 8/10 | 当前术语工作台空态鼓励“AI 发现术语”，会强化独立维护心智 | 空态改为“从蓝图/指标/维度中沉淀别名”，主 CTA 指向配置来源 |
| 用户旅程 | 5/10 | 9/10 | 用户从“我要沉淀分析能力”被分流到“先建术语” | 创建蓝图时顺手确认别名和口径；术语不再打断主流程 |
| AI Slop 风险 | 7/10 | 9/10 | 有多个类似工作台和统计卡，像“功能堆叠” | 把术语统计降级为治理状态，不做主舞台 |
| 设计系统一致性 | 7/10 | 8/10 | 现有组件可复用，但入口层级要改 | 复用现有列表、详情、候选和冲突组件 |
| 响应式与可访问性 | 6/10 | 8/10 | 术语工作台三栏在小屏会更重 | 降级后减少小屏主路径压力 |
| 未决设计决策 | 4/10 | 8/10 | “术语在哪里编辑”还不明确 | 设定为治理/高级抽屉，来源页面内嵌轻量编辑 |

### 推荐导航结构

```text
数据集治理
├── 数据表
├── 字段标注
├── 指标
│   └── 别名与口径（内嵌）
├── 维度
│   └── 枚举解释 / 别名（内嵌）
├── 分析蓝图
│   └── 触发词 / 参数别名 / 输出口径（内嵌）
├── 语义验证
└── 高级治理
    ├── 语义词典（原业务术语）
    ├── 冲突检测
    ├── 权限
    └── 版本历史
```

### 用户流

```text
用户要沉淀复杂分析
  └─ 进入分析蓝图
      └─ 填蓝图名称、问法、业务场景、输出、口径约束
          └─ AI 生成蓝图草稿
              └─ 同屏提示候选别名/术语冲突
                  ├─ 确认别名：写入语义词典
                  ├─ 忽略候选：不影响蓝图保存
                  └─ 冲突：提示选择口径
                      └─ 发布蓝图
```

### 页面舍取

| 当前 UI | 处理 | 原因 |
|---|---|---|
| 能力 Tab：业务术语 | 移出一级 Tab，放入高级治理或语义治理分组 | 减少和分析蓝图/指标/维度并列造成的认知冲突 |
| 术语总数、已启用、有同义词、有关联资产统计 | 降级展示或仅在高级治理展示 | 这些是治理指标，不是业务主路径指标 |
| “AI 发现术语”主按钮 | 改为蓝图/指标/维度编辑中的“建议别名” | 候选来源本来就是这些资产 |
| “新建术语”主按钮 | 降级为高级动作 | 只给数据治理人员直接维护 |
| 冲突检测 | 保留，放到语义验证或高级治理 | 这是术语保留的核心价值 |
| 语义验证报告里的术语命中 | 保留 | 用于解释问数链路是否走对口径 |
| 聊天里的术语澄清卡片 | 保留 | 这是运行时用户价值，不是后台管理噪音 |

## Plan Design Review：完整 7 维评审

### Review Classifier

本次计划属于 APP UI：数据集治理、语义资产维护、蓝图配置和问数验收的工作台型界面。评审采用 App UI 规则：安静、可扫描、低装饰、主工作区清晰、导航能说明当前位置和下一步。

### Pass 1：Information Architecture

评分：5/10 -> 9/10。

问题：当前 `capabilityTabs` 把 `业务术语` 与 `分析蓝图`、`指标`、`维度` 同级展示，会让用户误判术语也是主分析能力。一个 10/10 的方案必须明确“主路径”和“治理支撑”的层级。

修正方案：

```text
数据集治理
├── 主路径
│   ├── 数据表
│   ├── 字段标注
│   ├── 指标
│   ├── 维度
│   ├── 分析蓝图
│   └── 语义验证
└── 高级治理
    ├── 语义词典（原业务术语）
    ├── 冲突检测
    ├── 权限
    └── 版本历史
```

实现要求：

- `capabilityTabs` 默认只展示主路径，`terms` 不再作为普通一级 Tab。
- 在能力页右上或尾部增加低噪音的 `高级治理` 入口，进入后可访问 `语义词典`。
- `语义词典` 页面文案从“沉淀业务词表、别名和口径解释”收敛为“治理跨资产别名、冲突和解释口径”。
- `数据集能力路线` 中不要把“知识”作为和“路径”并列的阶段；术语是支撑层，不是路线终点。

### Pass 2：Interaction State Coverage

评分：6/10 -> 9/10。

问题：计划已经提到候选术语、冲突检测和运行时澄清，但缺少用户在每种状态下“看到什么”的规格。一个 10/10 方案要覆盖空、加载、成功、失败、部分成功和重复冲突。

| Feature | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| 高级治理入口 | 按钮禁用并显示轻量 loading | 仍显示入口，但语义词典内解释“当前无词条，不影响问数” | toast 提示“治理信息加载失败，可重试” | 进入语义词典列表 | 词典加载成功但冲突检测失败时保留列表 |
| 语义词典列表 | 列表骨架屏，不阻塞主路径 | 显示“暂无词条；可从蓝图、指标、维度中沉淀别名”，主 CTA 不再是“AI 发现术语” | 显示重试按钮和错误原因 | 显示搜索、筛选、详情 | 部分词条关联资产加载失败时标注“关联信息暂不可用” |
| 蓝图向导候选别名 | 在第 2 步 AI 草稿后显示“正在检查别名和口径” | 显示“未发现需要沉淀的别名”，不制造任务 | 候选失败时显示“暂未生成建议，不影响蓝图保存” | 候选以可接受/忽略的行项展示 | 部分候选 409 重复时提示“已存在，建议复用” |
| 候选术语接受 | 行内 spinner | 不适用 | 409 时转为“复用已有词条”操作 | 行状态变为“已沉淀” | 多选接受时失败项留在列表 |
| 冲突检测 | 按钮 loading，不允许重复点击 | 无冲突时显示“当前未发现冲突” | 显示失败原因和重试 | 显示冲突组、影响资产和处理建议 | 部分术语无法检测时显示被跳过条目 |
| 语义验证报告 | 保持现有测试 loading | 无术语命中时显示“本问法未依赖语义词典” | 测试失败仍展示 route、失败原因 | 显示术语命中、蓝图命中、SQL、回答 | 生成 SQL 成功但解释失败时仍展示命中资产 |
| 聊天术语澄清卡片 | 发送后保留用户问题和等待状态 | 不适用 | 澄清提交失败可重试 | 选中术语后继续原问题 | 候选过多时折叠并提供搜索 |

### Pass 3：User Journey & Emotional Arc

评分：5/10 -> 9/10。

问题：用户的目标是“让系统能回答/分析”，不是“维护术语表”。如果页面继续把术语摆在主路径，会制造“还要先建词典”的心理成本。

| Step | User does | User feels | Plan specifies |
|---|---|---|---|
| 1 | 进入数据集治理页 | 想快速知道下一步该配置什么 | 默认看到数据表、字段、指标、维度、蓝图、验证这些主路径 |
| 2 | 创建分析蓝图 | 期待把复杂分析沉淀成可用能力 | 4 步向导保持，术语不提前打断 |
| 3 | 确认 AI 草稿 | 需要校准触发问法和口径 | 同屏显示“建议别名与口径”，可接受或忽略 |
| 4 | 发现同词多义 | 担心问数走错口径 | 用冲突提示解释影响，并提供复用/新建/忽略 |
| 5 | 发布蓝图并验证 | 希望确认链路真的可用 | 语义验证展示蓝图命中和术语命中作为证据 |
| 6 | 普通问数中遇到歧义 | 需要快速恢复，而不是回后台配置 | 聊天澄清卡片继续作为运行时补救 |
| 7 | 数据治理人员定期检查 | 需要集中治理冲突 | 高级治理保留完整语义词典和冲突检测 |

时间尺度：

- 5 秒：用户第一眼看到“分析蓝图/指标/维度/语义验证”才是主工作，而不是被术语分散。
- 5 分钟：用户能完成一个蓝图草稿，并顺手处理候选别名。
- 5 年：语义词典作为审计和解释资产保留，不因页面降级丢掉历史治理价值。

### Pass 4：AI Slop Risk

评分：7/10 -> 9/10。

问题：现有页面容易滑向“每个能力都有 hero、统计卡、AI 按钮、列表详情”的功能堆叠。对于工作台型 UI，这会增加噪音。

具体约束：

- 不新增新的 hero 或宣传式卡片；术语降级只调整层级，不制造新的展示区。
- 不把“建议别名与口径”做成大卡片网格；它应是蓝图草稿审核里的紧凑行项。
- 不使用“AI 发现术语”作为主视觉 CTA；改为上下文动作“建议别名”。
- 统计卡只保留在高级治理，不进入主路径首屏。
- 文案使用工具语言：`建议别名`、`复用已有词条`、`忽略`、`冲突检测`、`已沉淀`，避免“智能沉淀语义资产”这类泛化表达。

AI slop litmus：

| Check | Result | Requirement |
|---|---|---|
| 产品第一屏是否清楚 | Yes after IA change | 主路径展示分析能力和验收 |
| 是否有一个强视觉锚点 | Yes | 数据集能力路线 + 当前 Tab 状态 |
| 仅扫标题能否理解 | Partial | Tab 文案必须从“业务术语”改为“高级治理/语义词典” |
| 每个区域是否只有一个任务 | Partial | 蓝图候选别名区域只做建议确认，不做词典管理 |
| 卡片是否必要 | Partial | 术语统计卡降级 |
| 动效是否必要 | No | 不新增动效 |
| 去掉装饰阴影后是否仍高级 | Yes if hierarchy clear | 依靠信息层级，不靠装饰 |

### Pass 5：Design System Alignment

评分：7/10 -> 8/10。

问题：没有项目级 `DESIGN.md`，但代码里已有稳定组件和页面模式。本计划应复用这些模式，避免引入新的视觉体系。

What already exists：

- `capabilityTabs`：可改造成主路径 Tab。
- `semantic-tab-panel`：可承载高级治理里的语义词典。
- `term-workbench`：保留为高级治理详情区。
- `GuidedEmpty`：复用空状态，但修改 CTA 和说明。
- `StatCard`：保留在高级治理，不用于主路径。
- `BlueprintWizardStepper`：蓝图向导继续使用，不改变步骤结构。
- `blueprint-review-grid`：第 2 步新增候选别名区域应复用该双栏审核模式。
- `TermClarificationCard`：聊天侧保留，不重新设计。

待补设计系统债务：

- 后续应新增 `DESIGN.md`，沉淀 Datalogue 的工作台信息架构、按钮层级、表单密度、空状态和移动端规则。

### Pass 6：Responsive & Accessibility

评分：6/10 -> 8/10。

问题：当前术语工作台是列表 + 详情的较重布局，放在一级 Tab 会加重窄屏负担。降级后仍需定义高级治理和蓝图候选区域的响应式行为。

响应式要求：

| Viewport | Data governance page | Semantic dictionary | Blueprint candidate aliases |
|---|---|---|---|
| Desktop >= 1200px | 主路径 Tab 横向展示，高级治理作为次级入口 | 左列表右详情 | 第 2 步审核区内右侧或下方紧凑列表 |
| Tablet 768-1199px | Tab 可横向滚动，高级治理保持可见 | 列表在上，详情在下 | 候选区域折叠为可展开面板 |
| Mobile < 768px | 主路径使用可滚动分段控件，避免 10 个 Tab 全铺 | 先显示搜索和列表，点词条进入详情抽屉 | 默认折叠，只显示候选数量和冲突红点 |

可访问性要求：

- 所有“接受 / 忽略 / 复用已有词条”操作必须是 `<button>`，支持键盘聚焦。
- 触摸目标不小于 44px；候选行的按钮不能只靠图标表达。
- 冲突和失败状态不能只用颜色表示，必须有文本标签。
- 语义词典搜索框保留可见 label 或 `aria-label`，不能只靠 placeholder。
- 聊天澄清卡片候选项应支持方向键或 Tab 顺序选择。
- 弹窗和抽屉关闭后焦点回到触发按钮。

### Pass 7：Unresolved Design Decisions

评分：4/10 -> 8/10。

本轮选择 Approach B 后，以下设计决策已落地到计划：

| Decision | Resolution | If deferred |
|---|---|---|
| 术语是否保留一级 Tab | 不保留；迁入高级治理/语义治理 | 用户继续误以为术语和蓝图并列 |
| 原“业务术语”命名 | 改为“语义词典 / 别名与口径” | 页面仍像独立业务功能 |
| 蓝图候选别名出现在哪一步 | 第 2 步 AI 草稿审核后 | 第 1 步输入负担过重，第 4 步太晚 |
| 候选术语是否阻塞保存 | 不阻塞；可接受、忽略、复用 | 用户会把术语当必填治理任务 |
| 冲突检测位置 | 高级治理或语义验证，不放主路径首屏 | 主页面继续被治理任务污染 |
| 空词典状态 | 说明“不影响问数”，引导从蓝图/指标/维度沉淀 | 空态会诱导用户先造词表 |

仍延后到后续的设计决策：

- 是否要把 `权限`、`版本历史` 与 `语义词典` 合并为一个“高级治理” Tab，还是保留为次级菜单。
- 是否为 Datalogue 新增项目级 `DESIGN.md`。
- 是否需要用 `/design-shotgun` 生成三个信息架构视觉变体供用户比较。

### Design Review Implementation Tasks

Synthesized from this review's findings. Each task derives from a specific finding above. Run with Claude Code or Codex; checkbox as you ship.

- [ ] **T1 (P1, human: ~2h / CC: ~15min)** — `datasets.jsx` — 将业务术语从普通一级能力 Tab 迁入高级治理入口
  - Surfaced by: Pass 1 — `terms` 与 `blueprints` 同级造成主路径混乱
  - Files: `datalogue-web/src/components/datasets.jsx`
  - Verify: 进入数据集能力页，默认主路径不再突出“业务术语”，高级治理仍可打开语义词典
- [ ] **T2 (P1, human: ~2h / CC: ~20min)** — `analysis-blueprints.jsx` — 在蓝图向导第 2 步加入建议别名与口径确认区
  - Surfaced by: Pass 3 — 用户创建蓝图时应顺手处理别名，不应先维护术语库
  - Files: `datalogue-web/src/components/analysis-blueprints.jsx`, `datalogue-web/src/api/client.js`
  - Verify: 蓝图 AI 草稿后可看到候选别名，可接受、忽略，且不阻塞保存
- [ ] **T3 (P1, human: ~1.5h / CC: ~15min)** — `datasets.jsx` — 补齐语义词典和候选别名的空、错、部分成功状态
  - Surfaced by: Pass 2 — 计划需要说明用户在 loading/empty/error/success/partial 时看到什么
  - Files: `datalogue-web/src/components/datasets.jsx`, `datalogue-web/src/components/analysis-blueprints.jsx`
  - Verify: terms API 失败、409 重复、无候选、部分候选失败时都有明确 UI
- [ ] **T4 (P2, human: ~1h / CC: ~10min)** — `datasets.jsx` — 调整语义验证报告中术语命中的视觉层级
  - Surfaced by: Pass 4 — 保留术语观测价值，但避免它重新变成主噪音
  - Files: `datalogue-web/src/components/datasets.jsx`
  - Verify: 语义验证仍展示术语命中、蓝图命中、路径和失败原因
- [ ] **T5 (P2, human: ~1h / CC: ~10min)** — frontend a11y — 为候选别名、语义词典和澄清卡片补键盘与可访问性约束
  - Surfaced by: Pass 6 — 降级入口后仍需保证高级治理和澄清操作可访问
  - Files: `datalogue-web/src/components/datasets.jsx`, `datalogue-web/src/components/analysis-blueprints.jsx`, `datalogue-web/src/assistant/MyMessage.jsx`
  - Verify: Tab 键可完成候选接受/忽略，冲突不只靠颜色表达，移动端按钮触达尺寸足够
- [ ] **T6 (P3, human: ~1h / CC: ~10min)** — docs — 新增 Datalogue 工作台设计规则文档
  - Surfaced by: Pass 5 — 项目缺少 `DESIGN.md`
  - Files: `DESIGN.md`
  - Verify: 文档包含信息架构、按钮层级、空状态、响应式和 a11y 基线

### Design Review Completion Summary

```text
+====================================================================+
|         DESIGN PLAN REVIEW — COMPLETION SUMMARY                    |
+====================================================================+
| System Audit         | No DESIGN.md, UI scope confirmed             |
| Step 0               | 7/10, focus all 7 dimensions                 |
| Pass 1  (Info Arch)  | 5/10 -> 9/10 after fixes                     |
| Pass 2  (States)     | 6/10 -> 9/10 after fixes                     |
| Pass 3  (Journey)    | 5/10 -> 9/10 after fixes                     |
| Pass 4  (AI Slop)    | 7/10 -> 9/10 after fixes                     |
| Pass 5  (Design Sys) | 7/10 -> 8/10 after fixes                     |
| Pass 6  (Responsive) | 6/10 -> 8/10 after fixes                     |
| Pass 7  (Decisions)  | 6 resolved, 3 deferred                       |
+--------------------------------------------------------------------+
| NOT in scope         | written                                      |
| What already exists  | written                                      |
| TODOS.md updates     | 0 written; 1 optional DESIGN.md task listed  |
| Approved Mockups     | 0 generated; designer binary unavailable     |
| Decisions made       | 6 added to plan                              |
| Decisions deferred   | 3 listed                                     |
| Overall design score | 7/10 -> 9/10                                 |
+====================================================================+
```

## Engineering Review：架构与数据流

### 架构图

```text
                 ┌──────────────────────┐
                 │ 数据集治理 UI         │
                 │ 指标/维度/字段/蓝图    │
                 └──────────┬───────────┘
                            │ 内嵌别名与口径确认
                            ▼
                 ┌──────────────────────┐
                 │ Terms API             │
                 │ /dataset/{id}/terms   │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ BusinessTerm Model    │
                 │ aliases/definition    │
                 │ forbidden/asset_links │
                 └──────────┬───────────┘
                            │
            ┌───────────────┴────────────────┐
            ▼                                ▼
┌──────────────────────┐        ┌────────────────────────┐
│ Dataset Context       │        │ Knowledge QA            │
│ schema_structured     │        │ _match_business_term    │
│ terms + blueprints    │        │ definition answer       │
└──────────┬───────────┘        └────────────────────────┘
           │
           ▼
┌──────────────────────┐
│ QueryGraph            │
│ schema_recall         │
│ -> term_normalize     │
│ -> semantic_asset     │
│ -> dsl_generate       │
└──────────┬───────────┘
           │
           ├─ 冲突：term_conflict_clarification -> PendingClarification -> 澄清卡片
           └─ 无冲突：术语命中注入 entities.terms，扩展关联资产
```

### 保留的后端能力

| 能力 | 保留原因 | 代码抓手 |
|---|---|---|
| `BusinessTerm` 模型 | 存定义、别名、禁用词、状态、来源和负责人 | `datalogue-api/app/models/dataset.py` |
| `BusinessTermAssetLink` | 表达术语与指标/维度/字段/蓝图的跨资产关系 | `datalogue-api/app/models/dataset.py` |
| terms CRUD API | 支撑高级治理和内嵌编辑 | `datalogue-api/app/api/dataset.py` |
| `discover_terms` | 保留为候选生成能力，但入口改为内嵌 | `datalogue-api/app/api/dataset.py` |
| `check_term_conflicts` | 术语不可替代能力 | `datalogue-api/app/api/dataset.py` |
| `_match_business_term` | 知识解释过渡能力 | `datalogue-api/app/graph/nodes.py` |
| `term_normalize_node` | 运行时别名归一和冲突澄清 | `datalogue-api/app/graph/nodes.py` |
| `semantic_asset_resolution_node` 的 terms | 资产统一解析和关联资产扩展 | `datalogue-api/app/graph/nodes.py` |

### 应避免的工程改法

- 不要把术语表直接删掉再把字段塞进指标/维度 synonyms；这会丢失 `definition`、`forbidden_aliases`、`asset_links`、`change_logs`。
- 不要让蓝图复制一份独立 term 数据；蓝图只应引用或建议语义词典项。
- 不要在前端隐藏 Tab 的同时删除 API；蓝图/指标/维度内嵌编辑仍需要 API。
- 不要让知识库直接依赖蓝图触发词回答定义；定义类问题仍应先查结构化词条，长期再接知识库检索。

### Error & Rescue Registry

| Codepath | What can go wrong | Current handling | Plan requirement | User sees |
|---|---|---|---|---|
| `discover_terms` | 大数据集候选过多、重复候选、候选质量低 | 截断到 30，按 name 去重 | 前端改为来源内嵌后，展示来源和可忽略动作 | “建议别名”，不是“必须纳入” |
| `create_term` | 同名术语重复 | 409 `同名业务术语已存在` | 保持，并在内嵌编辑中提示改用现有术语 | 明确重复提示 |
| `term_normalize_node` | 同义词命中多个术语 | 返回 `term_conflict_clarification` | 保持运行时打断，不继续生成 SQL | 澄清卡片 |
| `_match_business_term` | 定义为空 | 返回“还没有维护定义” | 保持；长期接知识库 | 可理解的空定义提示 |
| `dataset_context` | token 预算裁剪术语 | `dataset_context_debug` 记录裁剪 | 保留命中资产优先策略 | 验证报告可解释 |
| 隐藏一级 Tab | 用户找不到高级术语入口 | 当前无 | 需要在高级治理和来源编辑处提供入口 | 主路径不受干扰，高级用户可找到 |

### Security & Threat Model

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 术语定义中输入 HTML/脚本，在前端展示时造成 XSS | Low-Medium | Medium | React 默认转义文本；计划不新增 `dangerouslySetInnerHTML` |
| 术语 ID 越权访问其他数据集术语 | Medium | High | 现有 `_get_term(ds_id, term_id)` 按 dataset 校验；保留 API 时继续复用 |
| 蓝图内嵌术语编辑绕过重复校验 | Medium | Medium | 内嵌入口仍调用 terms API，不另写保存逻辑 |
| 删除术语导致历史验证报告引用失效 | High if C | Medium | B 方案不删除模型，避免该风险 |

### Performance Review

| Area | Current risk | Plan handling |
|---|---|---|
| 数据集加载并行拉取 terms | 业务术语很多时数据集页加载变重 | 弱化一级入口后，可考虑仅高级治理页或需要时加载 terms |
| QueryGraph schema context 包含所有 active terms | 大量术语可能挤占 token 预算 | 已有 token_budget 裁剪和命中资产优先；后续可给 terms 做 top-K 召回 |
| 冲突检测遍历所有 terms | 大术语库下可能变慢 | 保留为人工触发治理动作，不放入每次问数 |
| 蓝图内嵌候选术语 | 如果每次实时发现会增加延迟 | 候选生成放在用户点击“建议别名”或保存草稿后异步提示 |

### Test Coverage Diagram

```text
CODE PATHS
[已有] term_normalize_node
  ├── [★★★ TESTED] alias match 注入 entities.terms
  ├── [★★★ TESTED] conflict -> clarification
  └── [★★★ TESTED] selected_term_id resolves conflict

[已有] clarification_resolution_node
  ├── [★★★ TESTED] structured selection
  ├── [★★★ TESTED] ordinal reply
  ├── [★★★ TESTED] name reply
  ├── [★★★ TESTED] invalid reply
  ├── [★★★ TESTED] missing state
  └── [★★★ TESTED] expired state

[已有] entry_intent_classification_node
  ├── [★★★ TESTED] blueprint hit
  ├── [★★★ TESTED] knowledge term hit
  └── [★★ TESTED] clarification route

[已有] semantic_asset_resolution_node
  ├── [★★★ TESTED] metric synonym
  ├── [★★★ TESTED] term feeds semantic asset resolution
  └── [★★★ TESTED] term linked metric expansion

[新增计划] UI 信息架构降级
  ├── [GAP] capabilityTabs 不再把 terms 作为普通一级主入口
  ├── [GAP] 高级治理或语义治理可进入语义词典
  ├── [GAP] 蓝图/指标/维度内嵌“别名与口径”入口
  └── [GAP] 语义验证继续展示术语命中

[新增计划] 蓝图创建内嵌候选术语
  ├── [GAP] 从蓝图名称/触发问法/参数/输出列生成候选
  ├── [GAP] 接受候选后调用 terms API
  └── [GAP] 忽略候选不阻塞蓝图保存

USER FLOWS
[已有] 用户问到冲突术语 -> 澄清卡片 -> 回复序号或名称 -> 原问题继续
  └── [★★★ TESTED backend] 前端需保留现有卡片

[新增计划] 用户创建蓝图 -> AI 草稿 -> 看到建议别名 -> 可确认或忽略
  └── [GAP] 需要前端交互测试或手工验收

[新增计划] 数据治理人员进入高级治理 -> 查看语义词典 -> 冲突检测
  └── [GAP] 需要页面渲染和 API 回归
```

### Required Tests

后端：

- 保留并运行 `tests/test_chat.py -k 'term_normalize or clarification or knowledge_term or semantic_asset_resolution'`。
- 保留并运行 `tests/test_dataset.py -k 'term'`，覆盖 terms CRUD、重复名和候选发现。
- 新增或补充蓝图候选术语测试：当蓝图草稿包含触发问法、参数、输出列时，候选术语可以关联到蓝图或对应资产。
- 若后续实现 terms lazy-load，补 `datasets` 页面所需 API 兼容测试。

前端：

- `npm run lint`。
- `npm run build`。
- 手工或浏览器验收：
  - 数据集能力页默认主路径不再突出“业务术语”。
  - 高级治理入口可打开语义词典。
  - 分析蓝图创建流程可看到/忽略/接受候选别名。
  - 语义验证报告仍展示术语命中。
  - 聊天术语澄清卡片仍可点击候选。

## Implementation Tasks

### P0：产品信息架构收敛

- [ ] 将数据集能力 Tab 中的 `业务术语` 从一级主路径移出，放入 `高级治理` 或 `语义治理` 分组。
- [ ] 将页面命名从 `业务术语` 调整为 `语义词典 / 别名与口径`，避免看起来像独立分析能力。
- [ ] 保留语义验证中的“术语命中”和聊天中的术语澄清卡片。

### P1：术语能力内嵌到主资产流程

- [ ] 指标表单内保留同义词，并提示“需要跨资产解释或冲突治理时进入语义词典”。
- [ ] 维度表单内保留同义词和值域解释，候选术语不作为单独必填。
- [ ] 分析蓝图向导第 2 步或第 3 步增加“建议别名与口径”区域。
- [ ] 候选术语接受后调用现有 terms API，不新增重复存储。

### P1：高级治理保留项

- [ ] 语义词典保留列表、搜索、编辑、删除。
- [ ] 保留冲突检测。
- [ ] 保留关联资产展示。
- [ ] 保留禁用词和示例问法。
- [ ] 降级术语总数等统计卡，不在主工作台强调。

### P2：后续架构优化

- [ ] 大术语库时，`build_dataset_query_context` 对 terms 增加 top-K 召回，而不是全量进入候选上下文。
- [ ] 知识库能力成熟后，将业务术语作为结构化词条索引入口，而不是最终知识回答来源。
- [ ] 语义验证支持展示“术语来自词典 / 指标同义词 / 蓝图触发词”的来源区分。

## Final Approval Gate

### Plan Summary

按 B 方案推进：业务术语不删除，但从一级主功能降级为语义基础设施。用户主路径以分析蓝图、指标、维度和语义验证为中心；术语继续支撑别名归一、冲突澄清、知识解释和资产关联。

### Decisions Made

- Total: 10
- Auto-decided: 9
- User-confirmed: 1
- Taste choices: 0
- User challenges: 0

### Review Scores

- CEO: 9/10。方向清晰，核心是降级而不是删除。
- Design: 9/10。已补齐信息架构、交互状态、用户旅程、AI Slop 风险、现有组件复用、响应式与可访问性约束。
- Eng: 8/10。后端应保持稳定，主要风险在前端重组和候选术语内嵌。
- DX: skipped。该计划不是开发者安装/集成型能力。
- Outside voices: unavailable。`codex exec` 因本地安全策略拒绝外部私有仓库审查，Claude subagent 工具不可用。

### Cross-Phase Themes

**Theme: 术语是基础设施，不是主业务功能** — CEO、Design、Eng 三个阶段都指向同一结论。高置信。

**Theme: 删除风险大于收益** — 工程链路已深度使用术语，删除会破坏澄清、验证和解释。高置信。

**Theme: 用户主路径必须回到蓝图/指标/维度** — 术语维护应嵌入这些来源流程，而不是让用户额外经营一套词表。高置信。

### Deferred to Future

- 完整知识库检索接入。
- terms top-K 语义召回。
- 术语来源细分审计。

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | documented in `/autoplan` body | CEO score 9/10; Approach B accepted |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | unavailable | External review blocked by local safety policy |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | documented in `/autoplan` body | Eng score 8/10; backend stable, frontend IA is main risk |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 7/10 -> 9/10, 6 decisions, 6 implementation tasks |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | skipped | Not a developer onboarding or integration plan |

- **VERDICT:** DESIGN CLEARED — Approach B has enough UI/UX detail to implement; eng review remains the required shipping gate when code changes start.

NO UNRESOLVED DECISIONS
