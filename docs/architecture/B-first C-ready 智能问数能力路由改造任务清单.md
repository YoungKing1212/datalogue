# C-shaped product, B-governed BI core 智能问数改造任务清单

本文用于承接当前头脑风暴结论，后续可继续整理为正式设计文档和开发计划。

核心方向：

```text
产品形态直接 C：Agentic Shell + BIWorkbenchTool + ReportAgent / PythonAgent / AuditAgent
BI 查询内核按 B-governed 管控：Capability Router + Shared DatasetAgent Runtime
AgentScope 保留验证线：event adapter / remote runner / runtime gate
```

当前不把 LeadAgent 直接改成自由 ReActAgent。更稳的目标是：产品上直接朝 Agentic Shell 工作台演进，但所有 BI 查询都必须经由 `BIWorkbenchTool` / `ask_bi` 进入受控内核，外层 Agent 只面对能力、摘要和引用，不面对数据集内部执行细节。

---

## 一、总目标

- [ ] 将 LeadAgent 从“混合规划器 / 编排器”收窄为 Hermes-style Capability Router。
- [ ] 定义 Agentic Shell 产品入口，让用户可以在同一工作流里问数、生成报告、做二次分析和查看审计解释。
- [ ] 定义 `BIWorkbenchTool` / `ask_bi`，作为 Agentic Shell、ReportAgent、PythonAgent、AuditAgent 使用 BI 能力的唯一入口。
- [ ] 建立数据集能力清单 `capability_manifest`，让 LeadAgent 基于能力而不是 schema 明细做路由。
- [ ] 将 DatasetAgent 固化为一个共享 Runtime，每次调用绑定 `dataset_id + manifest + capability_manifest`。
- [ ] 统一 `SKILL.md` / `SOUL.md` 协议，不按数据集复制 Agent Prompt。
- [ ] 将 DatasetAgent 输出拆成 `llm_visible` 与 `control_plane`，为未来外层 Agentic Shell 调用留安全边界。
- [ ] 保持 Manifest、SQL Guard、QueryArtifact、conversation_state、Langfuse trace 仍由 Datalogue 业务内核掌握。
- [ ] 明确 ReportAgent、PythonAgent、AuditAgent 只能消费 `llm_visible`、`result_ref`、`report_ref` 和脱敏后的事件，不得直接访问 schema、SQL、数据库或 `control_plane` 主体。

---

## 二、边界原则

### 2.1 LeadAgent 可以做什么

- [ ] 理解用户问题所属的业务意图。
- [ ] 判断是否需要用户澄清。
- [ ] 选择一个或多个数据集。
- [ ] 调用 `query_dataset` 或 `query_multiple_datasets`。
- [ ] 汇总 DatasetAgent 返回的轻量摘要。
- [ ] 生成最终面向用户的自然语言回答。

### 2.2 LeadAgent 不应该做什么

- [ ] 不直接读取完整 schema。
- [ ] 不直接读取候选资产详情。
- [ ] 不直接生成 SQL。
- [ ] 不直接修复 SQL。
- [ ] 不直接执行 SQL。
- [ ] 不把完整结果集放入 LLM context。
- [ ] 不把 DatasetAgent capsule 主体放入 LLM context。
- [ ] 不绕过 Manifest、权限、SQL Guard 和 Artifact 持久化。

### 2.3 DatasetAgent 应该做什么

- [ ] 在单个数据集边界内完成资产召回、查询规划、SQL 生成、SQL 校验、执行预览、失败修复和结果摘要。
- [ ] 所有内部能力继续受 Manifest、权限、质量状态和 SQL Guard 约束。
- [ ] 产出结构化 QueryArtifact / result_ref / report_ref，供多轮、审计和外层调用引用。
- [ ] 向 LeadAgent 返回轻量摘要，不返回内部执行主体。

---

## 三、P0：能力清单模型

目标：先定义数据集能力卡，这是 B 的核心，也是未来 C 调用 BI 能力的说明书。

- [ ] 定义 `CapabilityManifest` 的字段模型。
- [ ] 明确哪些字段来自当前 Manifest，哪些字段来自语义资产聚合，哪些字段由规则生成。
- [ ] 支持表达数据集可回答范围。
- [ ] 支持表达数据集不可回答范围。
- [ ] 支持表达核心指标、核心维度、业务术语、典型问题和质量状态。
- [ ] 将 `can_answer`、`cannot_answer`、`typical_questions` 的生成方式定为“模型辅助生成 + 人工审核，发布时固化”。
- [ ] 为能力文案增加审核状态、发布版本和内容安全扫描，禁止字段、表、SQL、blueprint 主体进入能力广告。
- [ ] 支持表达权限、发布状态、schema freshness 和 Manifest guard 状态。
- [ ] 定义 `list_datasets()` 返回的最小字段。
- [ ] 定义 `describe_dataset_capability(dataset_id)` 返回的详细字段。
- [ ] 增加能力清单快照或 API 输出，用于人工审查和后续测试。
- [ ] 准备至少 2 个真实数据集的能力清单样例。

验收关注点：

- [ ] LeadAgent 不需要 schema 明细也能判断大多数数据集路由。
- [ ] 能力清单能明确表达“不能回答什么”，避免误路由。
- [ ] 能力清单输出体积可控，适合进入 LeadAgent context。

---

## 四、P1：LeadAgent Capability Router

目标：把 LeadAgent 的工具面收窄成能力路由，而不是开放执行器。

- [ ] 梳理当前 LeadAgent 直接使用的 schema、asset、planner、SubAgent 调用和 fan-out 入口。
- [ ] 定义 LeadAgent 可见工具集合：
  - [ ] `list_datasets`
  - [ ] `describe_dataset_capability`
  - [ ] `query_dataset`
  - [ ] `query_multiple_datasets`
  - [ ] `clarify`
  - [ ] `final_answer`
- [ ] 明确 LeadAgent Prompt / SOUL 中的禁止项。
- [ ] 将数据集选择依据从内部资产细节转向 `capability_manifest`。
- [ ] 保留低风险 deterministic fallback，防止模型路由异常时主链路不可用。
- [ ] 为低置信路由定义候选数据集确认式澄清策略：展示候选数据集和简短业务理由，让用户确认，不暴露 schema、字段、资产细节。
- [ ] 为多数据集问题定义“保守 + 少量半自动”fan-out 条件：用户明确跨域或问题天然多域时允许 `query_multiple_datasets`，候选相近但意图不清时先澄清。
- [ ] 定义多数据集结果汇总边界：只汇总 `llm_visible` 摘要和引用，不做跨数据集 SQL join，不把多个数据集 schema 合并给 LeadAgent。
- [ ] 确认 LeadAgent 最终回答只基于 `display_summary + result_ref/report_ref + metadata`。

验收关注点：

- [ ] LeadAgent trace 中看不到 raw SQL、完整结果集和 DatasetAgent capsule 主体。
- [ ] 单数据集、跨数据集、需要澄清、无法回答四类问题都有稳定路径。
- [ ] 低置信澄清能把候选数据集、原因和用户选择写入状态，并支持下一轮恢复。
- [ ] fan-out 场景能证明每个数据集独立通过 runtime overlay，并且最终只做结果级汇总。
- [ ] 现有 `/chat/stream` 用户体验不因内部边界收窄而退化。

---

## 五、P2：DatasetAgent 共享 Runtime

目标：只保留一个 DatasetAgent Runtime，通过数据集绑定和能力清单体现差异。

- [ ] 明确 DatasetAgent 调用入参：
  - [ ] `dataset_id`
  - [ ] `question`
  - [ ] `conversation_context`
  - [ ] `manifest`
  - [ ] `capability_manifest`
  - [ ] `permission_context`
- [ ] 明确 DatasetAgent 内部工具集合：
  - [ ] `recall_assets`
  - [ ] `plan_query`
  - [ ] `get_asset_detail`
  - [ ] `generate_sql`
  - [ ] `guard_sql`
  - [ ] `preview_sql`
  - [ ] `repair_sql`
  - [ ] `persist_artifact`
  - [ ] `summarize_result`
- [ ] 将共用 `SKILL.md` 作为能力说明层。
- [ ] 将共用 `SOUL.md` 作为不可越界协议层。
- [ ] 明确 DatasetAgent 内部可以使用更细资产，但这些资产不回流到 LeadAgent context。
- [ ] 复用现有 QueryGraph、Manifest guard、SQL preview、ArtifactStore 和 conversation_state 能力。
- [ ] 建立 DatasetAgent Runtime 的最小 contract test。

验收关注点：

- [ ] 不按数据集复制 Agent Prompt。
- [ ] 数据集差异只来自 manifest、capability_manifest 和语义资产。
- [ ] DatasetAgent 内部失败时能返回澄清、拒答、修复失败或安全阻断摘要。

---

## 六、P3：DatasetAgentToolAdapter 出参分层

目标：把 DatasetAgent 封装成可被 LeadAgent 和未来 Agentic Shell 调用的稳定能力。

- [ ] 第一阶段采用兼容迁移协议：用 adapter 包裹现有 `SubAgentToolResult`，但 legacy 结构只能进入 `control_plane`。
- [ ] 后续必须升级到三段式 + 细分语义块协议，明确 `result / artifact / error / clarification` 是必做目标，不作为 optional。
- [ ] 定义 `SubAgentToolResult` 或同等结果协议。
- [ ] 定义 `llm_visible` 字段：
  - [ ] `status`
  - [ ] `display_summary`
  - [ ] `clarification_question`
  - [ ] `error_summary`
  - [ ] `dataset_id`
  - [ ] `result_ref`
  - [ ] `report_ref`
- [ ] 定义 `control_plane` 字段：
  - [ ] `capsule`
  - [ ] `query_artifact_id`
  - [ ] `last_success_task`
  - [ ] `raw_sql`
  - [ ] `raw_result_ref`
  - [ ] `trace_id`
  - [ ] `raw_error`
- [ ] 定义 `trace_metadata` 字段：
  - [ ] `schema_version`
  - [ ] `dataset_id`
  - [ ] `tool_name`
  - [ ] `manifest_version`
  - [ ] `guard_status`
  - [ ] `artifact_id`
- [ ] 增加 size guard，防止 `llm_visible` 超预算。
- [ ] 增加敏感字段脱敏和错误脱敏。
- [ ] 明确 control plane 只在代码层和持久化层流转，不进入 LLM context。
- [ ] 为 v2 细分语义块补充迁移计划，完成后逐步移除上层对 legacy result 的依赖。

验收关注点：

- [ ] 未来外层 Agentic Shell 也只能拿到 `llm_visible`。
- [ ] 业务追溯仍可通过 `control_plane`、artifact 和 trace 完成。
- [ ] 出参 schema version 可进入 Langfuse trace。
- [ ] v1 兼容阶段不得把 `legacy_subagent_result` 暴露给 LeadAgent；v2 细分语义块必须进入后续里程碑。

---

## 七、P4：事件与观测协议

目标：让当前 Web Chat SSE 和未来 AgentScope event stream 可以复用同一批业务事件。

- [ ] 定义统一 `DatalogueEventEnvelope`，先服务现有 `/chat/stream` SSE，再为 AgentScope event stream 预留 adapter。
- [ ] 统一业务事件命名：
  - [ ] `route.started`
  - [ ] `dataset.selected`
  - [ ] `clarification.required`
  - [ ] `dataset.query.started`
  - [ ] `dataset.query.completed`
  - [ ] `artifact.created`
  - [ ] `answer.completed`
  - [ ] `error.blocked`
- [ ] 明确每类事件的 payload 上限。
- [ ] 定义事件 `visibility`：`user_visible`、`trace_only`、`control_plane`。
- [ ] 明确哪些事件给前端展示，哪些只进 trace。
- [ ] 将现有 SSE 输出映射到 event envelope，并保留当前前端流式体验。
- [ ] 预留 `AgentScopeEventAdapter` 接口，第一阶段不直接替换 SSE。
- [ ] 对齐 Langfuse observation 名称和 metadata。
- [ ] 对齐后端 checkpoint 日志字段。
- [ ] 保持最终 SSE payload 与数据库落库状态一致。
- [ ] 增加事件泄露扫描，阻止 raw SQL、完整结果集、capsule 主体进入 user-visible event。

验收关注点：

- [ ] 页面展示、SSE、后端日志、Langfuse trace、query_artifact 能交叉核对。
- [ ] 事件协议不依赖 AgentScope，但后续可映射到 AgentScope event stream。
- [ ] 第一阶段不让 AgentScope event stream 替换 `/chat/stream`，只验证 adapter 映射边界。

---

## 八、P5：C 产品形态入口与 C-ready 工作规划

目标：产品层直接按 C 形态规划，让 Agentic Shell 先具备清晰入口和任务骨架；BI 查询能力仍通过 B-governed 内核提供，避免外层 Agent 绕过治理边界。

### 8.1 Agentic Shell 产品入口

- [x] 定义第一版 Agentic Shell 的入口形态：先复用现有 Chat 页面承接用户入口，同时按未来 BI 工作台设计任务模型、事件流、产物引用和状态结构。
- [ ] 在现有 Chat 回答区承接任务卡片、结果引用、报告草稿、分析产物和审计解释入口。
- [ ] 定义 Chat 到未来独立 BI 工作台的迁移口，确保后续工作台复用同一套任务模型、事件协议和产物引用。
- [x] 定义 Chat 内第一版任务展示粒度：采用业务级任务时间线，默认展示任务理解、数据集匹配、BI 执行、结果产物和下一步动作。
- [ ] 为方案 3 预留双层可展开时间线改造：默认业务节点，后续在权限和脱敏规则满足时展开受控技术摘要。
- [x] 定义产物详情第一阶段承载方式：Chat 内轻量产物卡，只展示摘要、引用和下一步动作。
- [ ] 预留 `detail_view_ref` / `artifact_panel_ref`，后续用右侧详情面板或独立 BI 工作台承载完整报告、图表和审计解释。
- [x] 定义轻量产物卡组件形态：统一 `ArtifactCard` 壳 + 类型化 `preview_payload`。
- [ ] 定义 `ArtifactCard` 通用字段：`artifact_type`、`title`、`status`、`summary_for_chat`、`primary_ref`、`related_refs`、`actions`、`detail_view_ref`、`artifact_panel_ref`。
- [ ] 定义 `preview_payload` 类型分支：`report`、`chart`、`audit`、`analysis`。
- [x] 定义 `preview_payload` schema 策略：外层 `ArtifactCard` 强 schema，`preview_payload` 半强 schema。
- [ ] 定义每类 `preview_payload` 的最小必填字段和 `optional_details` 扩展位。
- [ ] 为所有 `preview_payload` 增加 `schema_version`、size guard、敏感字段扫描和 `visibility` 约束。
- [x] 定义 `actions` 策略：固定 Action Registry + 后端下发受控动作实例。
- [ ] 定义第一阶段 Action Registry：`open_detail`、`continue_edit`、`analyze_more`、`export`、`explain`、`retry`、`change_dataset`。
- [ ] 定义每个 `action_type` 的 payload 白名单 schema。
- [x] 定义引用结构：拆分 `primary_ref` 与 `related_refs`，并预留 `role` 字段。
- [ ] 定义 `primary_ref` 最小字段：`ref_type`、`ref_id`、`label`，可选 `role`。
- [ ] 定义 `related_refs` 最小字段：`ref_type`、`ref_id`、`label`，可选 `role`。
- [ ] 定义 Shell 可识别的任务类型：
  - [ ] `ask_bi`：问数。
  - [ ] `make_report`：基于 BI 结果生成报告。
  - [ ] `analyze_with_python`：基于受控结果切片做二次分析。
  - [ ] `explain_audit`：解释数据来源、口径、guard、artifact 和 trace。
  - [ ] `clarify_task`：任务意图或数据集低置信时澄清。
- [ ] 定义 Shell 的任务状态：`planning`、`waiting_user`、`running_bi`、`running_agent`、`blocked`、`completed`。
- [ ] 定义 Shell 任务级 `task_id` / `trace_id`，并与 BI 内部 trace 建立父子关系。

验收关注点：

- [ ] 用户从产品上看到的是可连续工作的智能分析入口，而不是只能做单轮问数。
- [ ] 第一阶段不需要新建完整 BI 工作台页面，也能在 Chat 内呈现 C 形态的任务结构。
- [ ] 后续独立 BI 工作台可以复用 Chat 阶段沉淀的任务、事件和产物协议。
- [ ] 第一阶段默认只展示业务级节点，不展示 SQL、schema、raw result、trace 或 `control_plane` 主体。
- [ ] 事件和状态协议已预留可展开技术摘要扩展位，后续双层时间线不需要另起协议。
- [ ] Chat 内轻量产物卡不承载完整长报告、完整表格、大图表或完整审计链路。
- [ ] 完整产物可通过引用句柄迁移到详情面板或独立工作台。
- [ ] 产物卡协议保持统一，产物差异只通过 `artifact_type` 和 `preview_payload` 表达。
- [ ] `preview_payload` 只承载轻量脱敏摘要，不承载完整产物主体或 `control_plane` 主体。
- [ ] `optional_details` 不得承载 raw SQL、raw result、schema、capsule、trace 主体或 `control_plane` 主体。
- [ ] `actions` 只能使用白名单 `action_type` 和白名单 payload，未知动作必须安全忽略。
- [ ] 所有动作执行仍走受控工具入口、权限校验和事件审计。
- [ ] `actions` 默认绑定 `primary_ref`；如需使用 `related_refs`，必须在白名单 payload 中显式声明引用用途。
- [ ] Shell 不直接持有 schema、SQL、raw result、capsule 或 artifact body。
- [ ] Shell 的每个子任务都能落到标准工具、标准事件和标准引用。

### 8.2 BIWorkbenchTool / ask_bi

- [ ] 定义未来外层可调用的 BI 工具入口：
  - [ ] `ask_bi(question, context)`
  - [ ] 或 `BIWorkbenchTool.run(question, context)`
- [ ] 明确 `BIWorkbenchTool` 内部仍调用 LeadAgent Capability Router。
- [ ] 明确外层 Agentic Shell 的权限：只能调用 BI 工具入口，不能绕过 LeadAgent/DatasetAgent 直接访问 schema、SQL 或数据库。
- [ ] 明确外层 Shell 可见结果只来自 `llm_visible`。
- [ ] 明确外层 Shell 可引用 `result_ref/report_ref`，但不能展开 `control_plane` 主体。
- [ ] 预留外层 Shell 的任务级 trace id，与 BI 内部 trace 做父子关联。

验收关注点：

- [ ] 当前 BI 内核接口无需重写即可被 C 形态调用。
- [ ] C 的开放性不会突破 BI 内核的安全边界。
- [ ] BI 仍然是一个高可信、可审计、可回放的受控能力。

### 8.3 ReportAgent

- [ ] 定义 ReportAgent 只消费 `display_summary`、`result_ref`、`report_ref` 和用户补充要求。
- [ ] 定义报告产物类型：文本草稿、章节结构、图表建议、引用来源列表。
- [ ] 定义 `summary_for_chat` 与 `report_ref` 的分层，Chat 内只展示报告摘要、标题、引用和动作入口。
- [ ] 定义 `report.preview_payload`：`outline`、`key_points`、`source_refs`。
- [ ] 将 `report.preview_payload` 最小必填字段定为 `outline`、`key_points`，`source_refs`、`suggested_sections` 进入 `optional_details`。
- [ ] 定义 ReportAgent 不能做的事：不能直接查库、不能展开 schema、不能读取 raw SQL、不能绕过 BIWorkbenchTool 重新问数。
- [ ] 定义报告生成后的 `report_ref`，用于多轮继续编辑、下载或审计。
- [ ] 定义报告中引用 BI 结果的最小证据格式，避免把内部执行细节暴露给用户。

验收关注点：

- [ ] 报告内容可追溯到受控 BI 结果或用户显式输入。
- [ ] 报告 Agent 不会因为写作任务拿到 BI 内核权限。

### 8.4 PythonAgent

- [ ] 定义 PythonAgent 只读取 `result_ref` 对应的受控数据切片。
- [ ] 定义可执行分析范围：聚合、排序、分组、轻量统计、可视化数据准备。
- [ ] 定义资源限制：行数、列数、执行时长、内存、输出体积。
- [ ] 定义脱敏策略：敏感字段默认不可进入 PythonAgent，除非权限和任务场景允许。
- [ ] 定义 PythonAgent 输出：分析摘要、图表数据、代码执行记录、结果引用。
- [ ] 定义 `chart_ref` / `analysis_ref`，Chat 内只展示分析摘要、轻量预览和动作入口。
- [ ] 定义 `chart.preview_payload`：`chart_type`、`metrics`、`dimensions`、`preview_spec_ref`。
- [ ] 定义 `analysis.preview_payload`：`method_summary`、`key_findings`、`analysis_ref`。
- [ ] 将 `chart.preview_payload` 最小必填字段定为 `chart_type`、`metrics`、`dimensions`，`preview_spec_ref` 进入 `optional_details`。
- [ ] 将 `analysis.preview_payload` 最小必填字段定为 `method_summary`、`key_findings`，`analysis_ref` 进入 `optional_details`。

验收关注点：

- [ ] PythonAgent 不能连接业务数据库。
- [ ] PythonAgent 的输入来自 artifact/ref，而不是来自 LeadAgent context 中的 raw result。
- [ ] Python 执行记录可审计、可回放、可阻断。

### 8.5 AuditAgent

- [ ] 定义 AuditAgent 的三类视图：
  - [ ] 用户可见解释：数据集、指标口径摘要、结果引用、阻断原因。
  - [ ] 管理员审计：权限、Manifest guard、artifact、trace、事件链。
  - [ ] 开发排障：checkpoint、raw error、内部 trace 关联。
- [ ] 定义不同视图的脱敏边界，避免把 `control_plane` 主体直接暴露给普通用户。
- [ ] 定义 AuditAgent 只能读取审计 API 或脱敏后的 artifact/trace 摘要。
- [ ] 定义无法回答或被阻断时的审计解释模板。
- [ ] 定义 `audit_ref`，Chat 内只展示用户可见审计摘要和“查看解释”入口。
- [ ] 定义 `audit.preview_payload`：`explanation_level`、`policy_summary`、`evidence_refs`。
- [ ] 将 `audit.preview_payload` 最小必填字段定为 `explanation_level`、`policy_summary`，`evidence_refs` 进入 `optional_details`。

验收关注点：

- [ ] 审计解释能说明“为什么这么答 / 为什么不能答”。
- [ ] 普通用户看不到 raw SQL、raw result、capsule 或内部错误主体。

### 8.6 C-ready 产物与事件协议

- [ ] 将 `DatalogueEventEnvelope` 扩展到 Shell 任务层，覆盖 Shell task、BI 子任务、Agent 子任务和 artifact 创建。
- [ ] 为业务级任务时间线定义事件：
  - [ ] `task.understood`
  - [ ] `dataset.matching`
  - [ ] `dataset.selected`
  - [ ] `bi.execution.running`
  - [ ] `bi.execution.completed`
  - [ ] `artifact.reference.created`
  - [ ] `next_action.available`
- [ ] 预留 `expandable_details` 或 `technical_summary` 字段，用于后续双层可展开时间线。
- [ ] 明确 `expandable_details` 只能承载脱敏摘要，不能包含 raw SQL、raw result、schema、capsule 或 `control_plane` 主体。
- [ ] 定义产物引用协议：
  - [ ] `result_ref`
  - [ ] `report_ref`
  - [ ] `chart_ref`
  - [ ] `audit_ref`
  - [ ] `detail_view_ref`
  - [ ] `artifact_panel_ref`
- [ ] 定义前端可展示的任务时间线，事件 payload 仍遵守 `visibility` 边界。
- [ ] 定义轻量产物卡 payload：`artifact_type`、`title`、`summary_for_chat`、`primary_ref`、`related_refs`、`actions`。
- [ ] 将轻量产物卡 payload 升级为统一 `ArtifactCard` 壳 + 类型化 `preview_payload`。
- [ ] 定义 `ArtifactCard` schema version，便于后续扩展详情面板和独立工作台。
- [ ] 定义 `preview_payload.kind` 与 `artifact_type` 的一致性校验。
- [ ] 定义 `optional_details` 的 size guard、visibility 和敏感字段扫描。
- [ ] 定义动作事件：`artifact.action.presented`、`artifact.action.clicked`、`artifact.action.blocked`、`artifact.action.completed`。
- [ ] 定义未知动作和非法 payload 的 trace-only 安全忽略事件。
- [ ] 定义引用事件 payload 中的 `primary_ref` 与 `related_refs`，避免动作和详情打开时引用歧义。
- [ ] 定义完整产物不得直接进入 Chat message body 的 size guard 和泄露扫描。
- [ ] 定义 C 形态下的最终 answer payload，既能返回自然语言，也能携带可继续操作的引用。
- [ ] 定义 C 形态真实链路验收：页面、SSE、日志、Langfuse、artifact、final payload 必须能交叉核对。

验收关注点：

- [ ] C 形态不是口头预留，而是有入口、任务、工具、事件和产物引用。
- [ ] 所有 C 形态 Agent 都通过 BIWorkbenchTool 使用问数能力。
- [ ] 产物可以继续编辑、引用和审计，但不能展开内部执行主体。

---

## 九、P6：AgentScope 后续验证线

目标：第一阶段主链暂不接 AgentScope runtime，但保留 AgentScope MVP / runner / adapter 验证线，等 B-governed BI 内核和 C 产品入口边界稳定后再接主链。

- [ ] 保留并强化 AgentScope MVP 验证线，继续验证 tool calling、LiteLLM 适配、Hermes-style 最小能力暴露和 react_trace。
- [ ] 等 `DatalogueEventEnvelope` 稳定后，设计 `AgentScopeEventAdapter`，验证事件如何映射到 AgentScope event stream。
- [ ] 等 `DatasetAgentToolAdapter` v1 稳定后，设计 Remote Runner Adapter，验证 DatasetAgent 远程调用协议。
- [ ] 等 `BIWorkbenchTool` / `ask_bi` 稳定后，验证 AgentScope 外层 Agentic Shell 如何调用 BI 能力。
- [ ] 等 ReportAgent / PythonAgent / AuditAgent 的工具边界稳定后，验证 AgentScope 多 Agent 编排是否只消费标准引用和 `llm_visible`。
- [ ] 定义 AgentScope 进入主链 runtime 的闸门：capability manifest、Capability Router、ToolAdapter、EventEnvelope、真实链路验收全部稳定。
- [ ] 明确 AgentScope 不替代 Datalogue 的 conversation_state、query_artifact、Manifest、SQL Guard 和业务审计真相源。

验收关注点：

- [ ] AgentScope 验证线能复用主链协议，而不是另起一套能力暴露规则。
- [ ] AgentScope adapter 只接标准化事件和工具结果，不读取 raw SQL、完整结果集或 capsule 主体。
- [ ] 主链接入前必须能证明页面、SSE、日志、Langfuse、artifact 和 final payload 仍可交叉核对。

---

## 十、暂不纳入第一阶段

- [ ] 不把 LeadAgent 直接改成自由 ReActAgent。
- [ ] 不让 LeadAgent 直接生成或修复 SQL。
- [ ] 不把完整 `/chat/stream` 直接包装成一个外部 Hermes/AgentScope 工具。
- [ ] 不按数据集复制多套 Agent。
- [ ] 不让 AgentScope session/memory 替代 Datalogue 的 conversation_state、query_artifact 和 Manifest 真相源。
- [ ] 不让 AgentScope 第一阶段接管 `/chat/stream` 主链 runtime。
- [ ] 不让第一阶段的 Agentic Shell 绕过 BIWorkbenchTool 访问 schema、SQL、数据库或 `control_plane` 主体。
- [ ] 不让 ReportAgent、PythonAgent、AuditAgent 获得比 BIWorkbenchTool 更高的数据权限。

---

## 十一、后续头脑风暴问题

- [ ] `capability_manifest` 是运行时动态生成、发布时固化，还是两者结合？
- [ ] 数据集“不可回答范围”由人工维护、规则生成，还是模型辅助生成后人工审核？
- [ ] LeadAgent 的 deterministic fallback 应保留到什么程度？
- [ ] 多数据集 fan-out 的默认策略是 LeadAgent 决策，还是先由规则筛选候选再交给 LeadAgent？
- [x] Chat 内第一版任务卡片展示到什么粒度？结论：业务级任务时间线，后续必须升级双层可展开时间线。
- [x] 报告草稿、图表、审计解释是内嵌在回答区域，还是以右侧详情面板展开？结论：第一阶段 Chat 轻量产物卡，后续详情面板/工作台承载完整产物。
- [x] 轻量产物卡是统一组件，还是按 report/chart/audit 分类型组件？结论：统一 `ArtifactCard` 壳 + 类型化 `preview_payload`。
- [x] `preview_payload` 第一阶段采用强 schema，还是宽松 JSON 加版本号？结论：外层强 schema，`preview_payload` 半强 schema。
- [x] `actions` 第一阶段是固定枚举，还是允许后端下发受控动作列表？结论：固定 Action Registry + 后端下发受控动作实例。
- [x] `refs` 是否需要拆成 `primary_ref` 与 `related_refs`？结论：拆分主引用与辅助引用，并预留 `role` 字段。
- [ ] `export` 第一阶段是否进入可用动作，还是只做预留禁用态？
- [ ] ReportAgent 第一阶段只生成文字报告，还是同时生成图表和可下载产物？
- [ ] PythonAgent 第一阶段允许的数据切片范围、行数上限和脱敏策略是什么？
- [ ] AuditAgent 的用户可见解释、管理员审计和开发排障三类视图如何分层？
- [ ] `SOUL.md` 是放在 Hermes skill 包内复用，还是抽成 Datalogue 内部契约文件后同步到 skill 包？

---

## 十二、建议里程碑

### M0：纸面设计收敛

- [ ] 固化 C-shaped product, B-governed BI core 架构图。
- [ ] 固化 Tool / Skill / Artifact / Control Plane 边界。
- [ ] 固化 `capability_manifest` 初版 schema。
- [ ] 固化 `DatasetAgentToolAdapter` 出参协议。
- [ ] 固化 `ask_bi` / `BIWorkbenchTool` 最小入参、出参和边界约束。
- [ ] 固化 Agentic Shell、BIWorkbenchTool、ReportAgent、PythonAgent、AuditAgent 的边界图。

### M1：能力清单与路由最小闭环

- [ ] 生成真实数据集能力清单。
- [ ] LeadAgent 基于能力清单选择数据集。
- [ ] `query_dataset` 打通现有 DatasetAgent。
- [ ] 保证现有单数据集问数链路不退化。

### M2：出参与观测治理

- [ ] 完成 `llm_visible/control_plane/trace_metadata` 分层。
- [ ] 完成 artifact/result_ref/report_ref 回传协议。
- [ ] 完成事件协议和 Langfuse trace 对齐。
- [ ] 补齐 P0 主链路五件套验收用例，覆盖真实页面、SSE event envelope、后端日志、Langfuse trace、query_artifact / conversation_state。
- [ ] 补齐普通 UI、动作禁用态和增强能力预留项的轻量协议验收用例。

### M3：C 产品入口最小闭环

- [ ] 定义 `ask_bi` / `BIWorkbenchTool` 外部调用入口，内部第一阶段复用现有 Chat / LeadAgent / DatasetAgent 主链。
- [ ] 将现有 SSE 输出映射成统一 `event_envelope`，作为 `ask_bi` 出参的一部分。
- [ ] 将最终 answer、候选数据集、产物卡、主引用和辅助引用整理成 `ask_bi` 标准出参。
- [ ] 在现有 Chat 中落地 Agentic Shell 第一版任务模型和事件模型。
- [ ] 在现有 Chat 中展示任务卡片、结果引用、报告草稿和审计解释入口。
- [ ] 在现有 Chat 中落地业务级任务时间线，覆盖任务理解、数据集匹配、BI 执行、结果产物和下一步动作。
- [ ] 在现有 Chat 中落地轻量产物卡，展示摘要、引用和下一步动作。
- [ ] 在现有 Chat 中落地统一 `ArtifactCard` 壳，按 `artifact_type` 渲染轻量内容区。
- [ ] 在 `ArtifactCard` 动作区展示 `export` 禁用态和 `disabled_reason`，第一阶段不生成导出文件。
- [ ] 在 `ArtifactCard` 动作区展示 `continue_edit` 禁用态或详情面板跳转，第一阶段不启动 ReportAgent。
- [ ] 在 `ArtifactCard` 动作区支持 `retry`，第一阶段只携带受控 `checkpoint_ref`。
- [ ] 在事件协议中预留 `export` 禁用态展示或点击的 trace-only 事件。
- [ ] 在事件协议中预留 `continue_edit` 禁用态展示、点击或打开详情面板的 trace-only 事件。
- [ ] 在事件协议中增加 `retry.started`、`retry.checkpoint_restored`、`retry.fallback_to_whole_task`、`retry.completed`、`retry.failed` 等业务级事件。
- [ ] 定义最小安全检查点结构，并接入现有 conversation_state / query_artifact / artifact ref。
- [ ] 完成外部 Agent 只能拿轻量摘要和引用句柄的安全验证。
- [ ] 验证 Chat 入口、`ask_bi`、`ArtifactCard`、`retry`、事件 envelope 和引用写入在 P0 主链路中五件套一致。
- [ ] 验证 `export`、`continue_edit`、ReportAgent 预留入口只表现为协议和禁用态，不触发增强链路。
- [ ] 打通“问数后生成报告草稿”的最小产品链路。
- [ ] 打通“基于 result_ref 做受控二次分析”的最小产品链路。
- [ ] 打通“解释本次回答来源和阻断原因”的最小审计链路。

### M4：C-ready 能力扩展

- [ ] 完成 ReportAgent 报告产物 `report_ref`。
- [ ] 完成 PythonAgent 受控执行沙箱和结果引用。
- [ ] 完成 AuditAgent 分层解释视图。
- [ ] 完成任务级时间线 UI 和产物继续操作入口。
- [ ] 完成右侧详情面板或独立 BI 工作台设计，用于承载完整报告、图表、审计解释和可编辑产物。
- [ ] 完成 `detail_view_ref` / `artifact_panel_ref` 到详情面板的跳转和状态恢复。
- [ ] 完成 ReportAgent 编辑链路、版本管理、保存、回滚和编辑审计设计，再决定是否启用 `continue_edit`。
- [ ] 完成双层可展开时间线设计，支持按权限查看受控技术摘要。
- [ ] 完成 `expandable_details` / `technical_summary` 的脱敏规则和泄露扫描。
- [ ] 完成导出权限、脱敏规则、文件生命周期、下载审计和格式白名单设计，再决定是否启用 `export`。
- [ ] 将 `ask_bi` 从 Chat 主链适配壳升级为 BI 工作台原生能力入口，补齐任务生命周期、权限视图、详情面板恢复、多产物状态和 AgentScope adapter。
- [ ] 评估完整 DAG 级子任务 retry、幂等执行和可视化任务恢复是否进入后续工作台版本。

### M5：AgentScope 主链接入预备

- [ ] 完成 AgentScope MVP / runner / adapter 验证线和主链协议对齐。
- [ ] 完成 `AgentScopeEventAdapter` 原型验证。
- [ ] 完成 Remote Runner Adapter 原型验证。
- [ ] 基于真实链路验收结果决定 AgentScope runtime 是否进入主链。

---

## 十三、当前推荐结论

采用：

```text
C-shaped product, B-governed BI core
```

当前实施目标：

```text
Agentic Shell 产品入口
+ BIWorkbenchTool / ask_bi
+ Hermes-style BI Capability Router
+ Shared DatasetAgent Runtime
+ Capability Manifest
+ llm_visible/control_plane 分层
```

未来演进目标：

```text
Agentic Shell
+ BI Capability Router
+ ReportAgent / PythonAgent / AuditAgent
+ AgentScope Runtime
```

关键约束：

```text
Agent 可以更聪明，但业务边界不能更松。
```
