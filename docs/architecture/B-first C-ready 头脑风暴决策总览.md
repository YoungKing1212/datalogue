# C-shaped product, B-governed BI core 头脑风暴决策总览

本文记录本轮围绕 Datalogue / 数语 LeadAgent、DatasetAgent、Hermes-style Skill、AgentScope 2.0 改造的阶段性决策。它不是最终开发计划，而是后续整合设计和制定计划时的决策底稿。

---

## 一、已定方向

本轮倾向采用：

```text
C-shaped product, B-governed BI core
```

含义是：

- 产品目标直接采用 C：Agentic Shell + BI Capability Router + DatasetAgent Runtime。
- BI 查询内核仍按 B-governed 管控：能力路由、权限、Manifest、SQL Guard、Artifact 和审计真相源不能被外层 Agent 绕开。
- 不直接把 LeadAgent 改成自由 ReActAgent。
- 当前所有接口和产物边界，都要让外层 Agentic Shell 可以安全调用，但只能通过 `BIWorkbenchTool` / `ask_bi` 使用 BI 能力。

---

## 二、三种方案的阶段性判断

### A：受约束 ReAct Supervisor

判断：

- 可以作为 AgentScope G0 / MVP 验证线。
- 不建议直接作为生产主链路第一版。

原因：

- ReAct 形态能验证 AgentScope 的 tool calling、event stream、runtime 能力。
- 但 LeadAgent 一旦过度开放，SOUL 会从“结构上不可违反”退化成“prompt 约束 + middleware 拦截”。
- 对企业问数主链路来说，权限、口径、SQL、结果审计比开放探索更重要。

### B：Hermes-style Capability Router

判断：

- 作为 BI 查询内核的主改造方向。

原因：

- 和 Hermes skill 最小能力暴露验证结果一致。
- LeadAgent 只面对数据集能力，不面对 schema、SQL、候选资产和完整结果集。
- DatasetAgent 内部继续承载 Manifest、QueryGraph、SQL Guard、Artifact 和 Trace。
- 更适合在不推倒现有业务内核的前提下，逐步接 AgentScope runtime。

### C：Agentic Shell + BI Capability Router

判断：

- 作为产品目标形态。
- 第一阶段先完成产品骨架和调用边界，不让 AgentScope runtime 直接接管主链。

原因：

- 外层 Agentic Shell 适合承载报告、图表、多步骤分析、跨工具协作。
- 但 BI 主链路仍要保持受控，不能让外层 Agent 绕过 LeadAgent / DatasetAgent 直接访问 SQL、schema 或数据库。
- 先把 B 的 BI 能力做成稳定工具，C 的产品体验才能安全复用，而不是把开放编排建立在不受控的数据访问上。

---

## 三、核心架构决定

### 3.1 LeadAgent 的新定位

```text
LeadAgent = Hermes-style BI Capability Router
```

LeadAgent 负责：

- 理解用户问题。
- 判断是否需要澄清。
- 选择一个或多个数据集。
- 调用 `query_dataset` / `query_multiple_datasets`。
- 汇总 DatasetAgent 返回的 `display_summary`。
- 输出最终回答。

LeadAgent 不负责：

- 直接看完整 schema。
- 直接看候选资产详情。
- 直接生成 SQL。
- 直接修复 SQL。
- 直接执行 SQL。
- 直接消费完整结果集。
- 直接持有 DatasetAgent capsule 主体。

### 3.2 DatasetAgent 的新定位

```text
DatasetAgent = 一个共享问数 Runtime
```

不是每个数据集复制一套 Agent，而是：

```text
一个 DatasetAgent Runtime
一套共用 SKILL.md
一套共用 SOUL.md
每个数据集一份 capability_manifest
```

数据集差异来自：

- dataset_id
- manifest
- capability_manifest
- 语义资产
- 权限上下文
- 质量状态

### 3.3 Skill / SOUL / Artifact 的边界

```text
SKILL.md = 能力说明和使用方法
SOUL.md = 不可越界协议
capability_manifest = 每个数据集的能力广告
Artifact = 查询结果和执行证据的真相源
```

不能把 blueprint、raw SQL、完整结果集、capsule 主体当成 Skill 塞进 LeadAgent context。

---

## 四、C 产品形态的受控入口

外层 Agentic Shell 可以调用：

```text
ask_bi(question, context)
```

或：

```text
BIWorkbenchTool.run(question, context)
```

但外层 Shell 只能看到：

```text
llm_visible:
  status
  display_summary
  clarification_question
  error_summary
  dataset_id
  result_ref
  report_ref
```

外层 Shell 不能看到：

```text
control_plane:
  raw_sql
  raw_result
  capsule
  query_artifact body
  internal trace payload
```

这个决定的目标是：产品体验可以直接朝 C 演进，但 BI 能力本身仍然是高可信、可审计、可回放的受控能力。

### 4.1 C-ready 工作规划

第一阶段需要让 C 的产品骨架先存在，但 BI 查询内核仍优先按 B-governed 收紧。工作规划分为六条线：

1. `Agentic Shell`：定义产品级任务入口，负责识别用户想问数、写报告、做图表、跑分析还是查审计。
2. `BIWorkbenchTool` / `ask_bi`：定义外层调用 BI 的唯一工具入口，内部仍走 LeadAgent Capability Router 和 DatasetAgent Runtime。
3. `ReportAgent`：消费 BI 的 `display_summary/result_ref/report_ref`，生成报告草稿和报告引用，不直接访问 SQL 或 schema。
4. `PythonAgent`：只读取受控 `result_ref` 对应的数据切片，做二次分析、统计或可视化，不连接业务数据库。
5. `AuditAgent`：基于 artifact、trace、event envelope 和 guard 状态解释“为什么这么答”，按用户可见层级脱敏。
6. `Task/Event Orchestration`：用 `DatalogueEventEnvelope` 串起 Shell 任务、BI 子任务、产物创建、错误阻断和最终回答。

这六条线的共同约束是：外层 Agent 只能消费 `llm_visible` 和引用句柄，所有执行证据、SQL、原始结果、capsule 和 trace 主体都留在 `control_plane`。

### 4.2 Agentic Shell 第一阶段入口形态

第一版 Agentic Shell 采用混合模式：

```text
Chat as Shell Entry
+ Workbench-ready Protocol
```

也就是：

- 用户入口先复用现有 Chat 页面和 `/chat/stream` 体验。
- Chat 内部开始承载任务级结构，包括 `task_id`、`task_type`、`task_status`、子任务事件和产物引用。
- 事件、状态和产物引用按未来 BI 工作台设计，不只做一次性对话增强。
- 后续独立 BI 工作台必须复用同一套任务模型、事件协议和引用句柄，不能另起一套并行协议。

这个决定让第一阶段可以少改前端入口，但不会牺牲 C 形态后续演进能力。

### 4.3 Chat 内任务展示粒度

Chat 内第一版任务展示采用：

```text
业务级任务时间线
+ 预留双层可展开技术摘要
```

第一阶段默认展示五类用户可理解的任务卡片：

1. `任务理解卡`：展示系统识别出的任务类型，例如问数、报告、分析、审计解释或澄清。
2. `数据集匹配卡`：展示候选或已选数据集，以及简短业务理由，不展示字段、表和资产细节。
3. `BI 执行卡`：展示查询进行中、完成、被阻断或需要澄清，不展示 SQL。
4. `结果产物卡`：展示 `result_ref`、`report_ref`、`chart_ref`、`audit_ref` 等可操作引用。
5. `下一步动作卡`：提供生成报告、继续分析、查看解释、换个数据集等动作入口。

方案 3 的双层可展开时间线必须进入后续改造记录。也就是：默认展示业务节点，后续允许在权限和脱敏规则满足时展开受控技术摘要，例如能力清单匹配依据、guard 状态、artifact 引用和 trace 关联摘要；仍不得暴露 raw SQL、raw result、schema、capsule 或 `control_plane` 主体。

### 4.4 产物详情承载方式

报告草稿、图表、审计解释等产物详情采用：

```text
Chat 轻量产物卡
+ detail_view_ref / artifact_panel_ref 预留
```

第一阶段 Chat 内只展示：

- 产物类型，例如报告、图表、审计解释。
- 轻量摘要，例如标题、核心结论、引用来源摘要。
- 引用句柄，例如 `result_ref`、`report_ref`、`chart_ref`、`audit_ref`。
- 下一步动作，例如展开、继续编辑、继续分析、查看解释、导出。

Chat 内不直接塞完整长报告、完整表格、大图表或完整审计链路。完整产物后续通过右侧详情面板或独立 BI 工作台承载，并复用同一套引用句柄。

### 4.5 轻量产物卡组件形态

轻量产物卡采用：

```text
统一 ArtifactCard 壳
+ 类型化 preview_payload
```

通用外壳字段：

```text
artifact_type
title
status
summary_for_chat
refs
actions
detail_view_ref
artifact_panel_ref
```

类型化预览放在 `preview_payload` 中：

```text
report:
  outline
  key_points
  source_refs

chart:
  chart_type
  metrics
  dimensions
  preview_spec_ref

audit:
  explanation_level
  policy_summary
  evidence_refs

analysis:
  method_summary
  key_findings
  analysis_ref
```

这样第一阶段前端只需要一个稳定卡片壳，产物差异通过轻量内容区表达；后续右侧详情面板或独立 BI 工作台继续复用 `artifact_type + preview_payload + refs`。

### 4.6 preview_payload schema 策略

`ArtifactCard` 外层采用强 schema，`preview_payload` 采用半强 schema：

```text
ArtifactCard:
  artifact_type
  schema_version
  title
  status
  summary_for_chat
  refs
  actions
  preview_payload
  detail_view_ref
  artifact_panel_ref
```

`preview_payload.kind` 必须与 `artifact_type` 对齐，每类定义最小必填字段，并保留 `optional_details`：

```text
report:
  required: outline, key_points
  optional_details: source_refs, suggested_sections

chart:
  required: chart_type, metrics, dimensions
  optional_details: preview_spec_ref

audit:
  required: explanation_level, policy_summary
  optional_details: evidence_refs

analysis:
  required: method_summary, key_findings
  optional_details: analysis_ref
```

所有 `preview_payload` 必须携带 `schema_version`，并受 size guard、敏感字段扫描和 `visibility` 约束。`optional_details` 不能成为任意内部信息出口，不得承载 raw SQL、raw result、schema、capsule、trace 主体或 `control_plane` 主体。

### 4.7 actions 策略

`ArtifactCard.actions` 采用：

```text
固定 Action Registry
+ 后端下发受控动作实例
```

第一阶段 Action Registry：

```text
open_detail
continue_edit
analyze_more
export
explain
retry
change_dataset
```

后端只能下发 registry 中已有的 `action_type`，每个动作实例包含：

```text
action_type
enabled
disabled_reason
payload
```

`payload` 必须按 `action_type` 走白名单 schema，不能携带 raw SQL、raw result、schema、capsule、trace 主体或 `control_plane` 主体。前端遇到未知 `action_type` 时必须安全忽略，并记录 trace-only 事件。所有动作执行仍走受控工具入口、权限校验和事件审计。

### 4.8 refs 策略

`ArtifactCard` 引用拆分为：

```text
primary_ref
related_refs
```

`primary_ref` 表示当前卡片的主产物，`actions` 默认绑定 `primary_ref`。`related_refs` 表示来源结果、审计证据、图表依赖、分析依赖等辅助引用。

基础结构：

```text
primary_ref:
  ref_type
  ref_id
  label
  role

related_refs:
  - ref_type
    ref_id
    label
    role
```

`role` 作为预留字段，可以表达 `main_artifact`、`source_result`、`audit_evidence`、`chart_dependency`、`analysis_dependency` 等语义；第一阶段不强依赖完整 `ref_roles` 枚举体系。后续独立 BI 工作台可以基于 `primary_ref` 打开主产物，并基于 `related_refs` 展示来源、证据和依赖。

### 4.9 export 动作策略

`export` 第一阶段进入固定 Action Registry，但默认作为预留禁用态：

```text
action_type: export
enabled: false
disabled_reason: 导出能力将在后续版本开放
```

第一阶段不生成导出文件、不开放完整数据导出、不导出 raw result。后端可以按 `artifact_type`、权限、功能开关和产物状态返回禁用原因；前端必须尊重 `enabled=false`，只展示禁用态和原因，不自行构造下载链接。

这样可以提前稳定动作协议、按钮位置、禁用原因和事件审计，同时把第一阶段重点留给 BI 查询、产物卡、引用、动作协议和事件链路，先把核心链路跑通。

### 4.10 continue_edit 动作策略

`continue_edit` 第一阶段进入固定 Action Registry，但只作为详情面板或未来工作台的预留动作：

```text
action_type: continue_edit
enabled: false
disabled_reason: 编辑能力将在后续版本开放
```

第一阶段可以禁用，也可以只打开 `detail_view_ref` / `artifact_panel_ref` 指向的详情面板；不得直接启动 ReportAgent，不实现报告继续编辑、版本管理、保存、回滚或编辑审计链路。

这条边界同时适用于现阶段其他 ReportAgent 相关问题：第一阶段不实现 ReportAgent 增强链路，只保留禁用态、详情入口或协议预留。当前优先级继续放在智能问数核心链路，包括路由、确认、执行、结果、产物卡、引用、动作协议和事件流。

### 4.11 ask_bi / BIWorkbenchTool 最小契约

第一阶段定义最小 `ask_bi` / `BIWorkbenchTool` 契约，作为 Agentic Shell、未来 BI 工作台和外部 Agent 调用智能问数能力的稳定外壳；内部暂时复用现有 Chat、LeadAgent、DatasetAgent 和 `/chat/stream` 主链。

最小入参：

```text
question
conversation_id
caller
confirmed_dataset_id
context_refs
request_options
```

最小出参：

```text
task_id
event_envelope
candidate_datasets
answer
artifact_card
primary_ref
related_refs
status
error
```

第一阶段不重写完整 BI 工作台运行时，不实现完整任务编排、多产物编辑状态、完整详情面板状态机和跨 Agent 协作 runtime。后续 C-ready 改造时，再把 `ask_bi` 从“Chat 主链适配壳”升级为“BI 工作台原生能力入口”，补齐任务生命周期、权限视图、详情面板恢复、多产物状态和 AgentScope adapter。

### 4.12 retry 动作策略

`retry` 第一阶段进入固定 Action Registry，但默认只支持从最后安全检查点重试：

```text
action_type: retry
enabled: true
payload:
  primary_ref
  checkpoint_ref
  retry_scope: last_safe_checkpoint
  fallback_scope: whole_task
```

第一阶段允许的安全检查点包括 `dataset_confirmed`、`query_context_ready`、`artifact_generation_failed`。后端必须验证 `checkpoint_ref` 属于当前会话、当前用户、当前任务和当前权限范围；检查点过期、缺失或校验失败时，降级为整任务重试，并通过 event envelope 告知恢复策略。

第一阶段不实现完整任务 DAG、任意子任务重试或不受控内部状态重放，也不得通过 `retry` 重放 raw SQL、raw result、schema 主体、capsule 主体、trace 主体或 `control_plane` 主体。

### 4.13 主链路验收口径

第一阶段真实链路验收采用分层验收：

```text
P0 主链路：
  - 真实页面展示
  - SSE event envelope
  - 后端日志
  - Langfuse trace
  - query_artifact / conversation_state

普通 UI / 动作禁用态：
  - 页面展示
  - event envelope
  - disabled_reason / action payload

增强能力预留项：
  - 协议存在
  - 禁用态正确
  - 不触发后端增强链路
```

P0 主链路至少覆盖用户提问、能力路由、候选数据集确认、受控查询执行、最终 answer、`artifact_card`、`primary_ref` / `related_refs`、事件 envelope、状态写入和历史回放。`export`、`continue_edit`、ReportAgent、完整工作台、多产物编辑等预留能力第一阶段只验协议、禁用态和不触发增强链路。

### 4.14 DSL / QueryGraph 与 SQL 生成边界

C 产品形态下继续保留 `DSL / QueryGraph / query_plan` 作为 DatasetAgent 内部语义计划层：

```text
LLM 负责理解问题和辅助生成语义计划
Tools 负责 DSL / QueryGraph 校验、SQL 编译、方言适配、SQL Guard 和执行
```

LLM 可以在 DatasetAgent 内部辅助生成或补全：

- 指标。
- 维度。
- 过滤条件。
- 时间范围。
- 分组、排序和聚合意图。

但 LLM 不能直接输出最终 SQL 作为执行依据。即便调试、失败修复或复杂问题需要模型辅助，也只能输出候选语义计划或修复建议，再由工具链完成 schema 校验、语义资产映射、数据源方言适配、SQL 生成、SQL Guard、preview / execute 和 artifact 持久化。

最终 SQL 属于 `control_plane`，不能进入 LeadAgent、Agentic Shell、ReportAgent、PythonAgent、AuditAgent、`ArtifactCard`、`preview_payload` 或 user-visible event。不同数据库的 SQL 方言适配也不交给 LLM 猜测，而由工具层基于数据源类型和受控模板处理。

### 4.15 QueryGraph Compiler 第一阶段落地方式

`QueryGraph Compiler` 第一阶段采用：

```text
独立 compiler / dialect adapter 外壳
+ 内部复用现有 QueryGraph / SQL 生成 / Guard / preview 链路
```

具体边界：

- `query_plan_compiler.py` 作为语义计划到 SQL 的稳定入口。
- `sql_dialect_adapter.py` 作为数据源方言适配的稳定入口。
- 现有 QueryGraph、SQL context、SQL 生成、SQL Guard 和 preview 能力先作为内部实现复用。
- 上层只依赖 compiler 外壳契约，不依赖内部实现细节。
- 后续可以逐步替换内部 compiler，不影响 LeadAgent、BIWorkbenchTool、ArtifactCard、event envelope 和 AgentScope adapter。

这个决定排除了第一阶段直接重写完整 compiler，也避免继续让编译、方言适配和执行边界散落在旧链路里。

### 4.16 AgentScope 2.0 第一阶段技术落点

当前计划需要显式补入 AgentScope 2.0，但接入层级要受控：

```text
AgentScope 2.0 = 外层 Shell Adapter / 编排验证层
Datalogue BI Core = 问数主链真相源和执行内核
```

第一阶段新增 `AgentScopeShellAdapter`：

- 用 AgentScope 2.0 验证外层 Agentic Shell 的最小编排。
- 只能调用 `BIWorkbenchTool` / `ask_bi`。
- 只能消费 `llm_visible`、`ArtifactCard`、event envelope 和引用句柄。
- 不直接访问 schema、SQL、raw result、capsule、数据库或 `control_plane`。
- 不替换现有 `/chat/stream` SSE。
- 不用 AgentScope session / memory 替代 Datalogue 的 conversation_state、query_artifact、Manifest、SQL Guard 和业务审计真相源。

这样第一阶段能看到 AgentScope 2.0 技术路线，但不会把 BI 主链 runtime、状态写入、artifact、Guard、trace 和历史回放一起重写。P6 仍保留为 AgentScope 主链 runtime 接入预备，用于后续评估是否让 AgentScope 更深进入主链。

### 4.17 AgentScopeShellAdapter 放置位置

`AgentScopeShellAdapter` 第一阶段放在后端正式 service：

```text
datalogue-api/app/services/agentscope_shell_adapter.py
datalogue-api/app/services/agentscope_event_adapter.py
```

但第一阶段只做内部调用与 contract test 验证：

- 不新增公开 API route。
- 不接前端入口。
- 不替换 `/chat/stream`。
- 不做独立 runner 进程。
- 不注册 schema、SQL、preview、database、artifact body 或 `control_plane` 工具。

这个选择让 AgentScope 2.0 接入层成为正式工程模块，而不是继续停留在 `tests/agentscope_*` 实验目录；同时避免第一阶段扩大用户入口、部署面和权限面。后续是否开放 API、独立 runner 或主链 runtime，由 P6 的接入闸门再决定。

### 4.18 SOUL.md 归属

`SOUL.md` 抽成 Datalogue 内部契约，再同步到 Hermes skill、AgentScopeShellAdapter 或未来外部 Agent 入口。

第一阶段主版本建议放在：

```text
datalogue-api/app/contracts/BI_SOUL.md
```

同步目标包括：

```text
hermes-skills/datalogue/SOUL.md
AgentScopeShellAdapter system prompt / policy injection
```

规则：

- Datalogue 内部契约是 source of truth。
- 外部 skill 包不再作为唯一主版本。
- 同步目标必须通过测试或同步脚本校验一致性。
- AgentScopeShellAdapter 不直接依赖 Hermes skill 目录，而是引用 Datalogue 内部契约。

### 4.19 SQL 方言适配范围

`sql_dialect_adapter.py` 第一阶段只覆盖当前真实数据源。

```text
接口：按方言注册表设计
启用范围：当前真实数据源
未知方言：fail closed
```

不在 P0 同时实现 PostgreSQL / MySQL / SQLite 等多方言完整兼容。后续接入新数据源时，再补对应 dialect adapter、contract test 和真实链路验收。

### 4.20 旧会话兼容边界

旧会话不支持新 `artifact_card`、C-ready event envelope、`primary_ref` / `related_refs` 和新 conversation_state 的历史回放。

第一阶段规则：

- 不迁移旧 conversation_state。
- 不为旧消息生成伪造 ArtifactCard。
- 不为旧 query artifact 回填新 refs。
- 旧会话保留原始回答和历史消息展示。
- 新协议从上线后的新会话开始生效。

这条边界避免为了历史数据兼容而伪造执行证据，也避免 P0 被历史迁移拖慢。

---

## 五、第一阶段不做的事

- 不把 LeadAgent 直接改成自由 ReActAgent。
- 不让 LeadAgent 自己写 SQL。
- 不让 LeadAgent 自己修 SQL。
- 不让 LLM 输出的 SQL 直接作为执行依据。
- 不把 SQL 方言适配交给 LLM 猜测。
- 不把完整 `/chat/stream` 包成一个外部工具给 Hermes 或 AgentScope。
- 不按数据集复制多套 Agent Prompt。
- 不用 AgentScope memory/session 替代 Datalogue 的 conversation_state、query_artifact、Manifest 和 trace 真相源。
- 不让 AgentScope 第一阶段直接接管 BI 主链 runtime。
- 不让第一阶段的 Agentic Shell 绕过 BIWorkbenchTool 直接访问 BI 内部能力。
- 不在第一阶段实现导出文件生成、下载链接、Excel/CSV/Markdown 生成或完整数据导出。
- 不在第一阶段启动 ReportAgent，不实现报告继续编辑、版本管理、保存、回滚或编辑审计链路。
- 不在第一阶段重写完整 BI 工作台运行时，不实现完整任务编排、多产物编辑状态或跨 Agent 协作 runtime。
- 不在第一阶段为 AgentScopeShellAdapter 开放公开 API、前端入口或独立 runner 进程。
- 不在第一阶段支持多数据库方言完整适配，只支持当前真实数据源。
- 不在第一阶段为旧会话迁移或回填 ArtifactCard、event envelope、refs 或新 conversation_state。
- 不在第一阶段实现完整任务 DAG、任意子任务重试或不受控内部状态重放。

---

## 六、后续要继续收敛的问题

- ReportAgent、PythonAgent、AuditAgent 与 BIWorkbenchTool 的协作边界。
- `result_ref` 给 PythonAgent 使用时的数据范围、行数上限和脱敏策略。
- AuditAgent 的用户可见解释、管理员审计和开发排障三类视图边界。
- 双层可展开时间线中，普通用户、管理员、开发者分别能看到哪些受控技术摘要。

---

## 七、下一步文档拆分建议

本专题文件夹后续可以继续补：

```text
00-本轮决策总览.md
01-改造任务清单.md
02-决策沉淀 Hook 规则.md
decisions/001-capability_manifest 定位为轻量能力广告.md
decisions/002-capability_manifest 采用固化主体加运行态叠加.md
decisions/003-static_capability 字段边界只到业务摘要层.md
decisions/004-can_answer 等能力文案采用模型辅助生成加人工审核.md
decisions/005-LeadAgent 低置信路由采用候选数据集确认式澄清.md
decisions/006-query_multiple_datasets 采用保守加少量半自动 fan-out.md
decisions/007-DatasetAgentToolAdapter 先兼容迁移后强制细分语义块.md
decisions/008-SSE 先标准化为统一 event envelope 并预留 AgentScope adapter.md
decisions/009-AgentScope 第一阶段保留验证线暂不进入主链 runtime.md
decisions/010-C 产品形态优先且 BI 内核保持 B-governed.md
decisions/011-Agentic Shell 第一阶段采用 Chat 入口加工作台协议.md
decisions/012-Chat 内任务展示采用业务级时间线并预留双层展开.md
decisions/013-产物详情采用 Chat 轻量卡并预留详情面板.md
decisions/014-轻量产物卡采用统一壳加类型化 preview_payload.md
decisions/015-preview_payload 采用半强 schema.md
decisions/016-actions 采用固定注册表加受控动作实例.md
decisions/017-refs 拆分为 primary_ref 与 related_refs 并预留 role.md
decisions/018-export 第一阶段进入 Action Registry 但默认禁用.md
decisions/019-continue_edit 第一阶段只作为详情面板预留动作.md
decisions/020-ask_bi 采用最小稳定契约并复用现有主链.md
decisions/021-retry 第一阶段从最后安全检查点重试.md
decisions/022-主链路验收采用分层验收.md
decisions/023-DSL QueryGraph 保留为内部语义计划并由工具编译 SQL.md
decisions/024-QueryGraph Compiler 第一阶段采用外壳封装并复用现有链路.md
decisions/025-AgentScope 第一阶段作为 Shell Adapter 显式接入但不接管 BI 主链.md
decisions/026-AgentScopeShellAdapter 放入后端正式 service 但第一阶段不开放 API.md
decisions/027-SOUL.md 抽成 Datalogue 内部契约并同步到外部 Skill.md
decisions/028-方言适配第一阶段只覆盖当前真实数据源.md
decisions/029-旧会话不支持 artifact_card 历史回放.md
03-B-first C-ready 后续改造记录.md
04-B-first C-ready 正式开发计划.md
05-AgentScope 2.0 集成系统设计方案.md
05-capability_manifest 字段设计.md
06-DatasetAgentToolAdapter 出参协议.md
07-AgentScope Runtime 接入边界.md
08-C 产品形态工作规划.md
```

当前已先沉淀 `00` 和 `01`，后续每个敲定决策都按 Hook 规则写入 `decisions/` 目录，方便最终转正式开发计划。
