# AgentScope 2.0 集成系统设计方案

> 本文是 2026-06-26 头脑风暴后的现阶段完整系统设计稿。设计目标不是第一阶段直接把 Datalogue 改成 AgentScope runtime，而是在保持智能问数主链稳定的前提下，把产品形态、协议边界和外层编排能力做成 AgentScope 2.0 ready。

## 一、设计结论

### 1. 总路线

采用 `C-shaped product, B-governed BI core`：

- 产品形态面向 C：用户看到的是可持续演进为 BI 工作台的 Chat / Shell 体验，而不是简单问答接口。
- BI 内核保持 B-governed：LeadAgent、DatasetAgent、QueryGraph、SQL Guard、QueryArtifact、conversation_state 和 Langfuse trace 仍然是智能问数的受控真相源。
- AgentScope 2.0 第一阶段只作为 `AgentScopeShellAdapter` 接入外层 Shell 编排验证，不接管 `/chat/stream`，不直接运行 DatasetAgent 主链。

### 2. 核心判断

当前阶段最重要的不是“用不用 AgentScope 运行所有 Agent”，而是先把 Datalogue 的 BI 能力整理成可被 AgentScope 消费的稳定能力面：

```text
业务意图 -> 能力路由 -> 受控语义计划 -> 工具编译 SQL -> 安全执行 -> 产物引用 -> 可观测事件
```

AgentScope 2.0 后续可以接入的前提，是这条能力面已经稳定、可测试、可追踪、可降级。

### 3. 真相源归属

- `BI_SOUL.md` 是 Datalogue 内部契约 source of truth。
- Hermes skill、AgentScopeShellAdapter、未来外部 Agent skill 都从 Datalogue 内部契约同步。
- 外部 skill 包内的 `SOUL.md` 只是分发副本，不再作为唯一主版本。

## 二、当前阶段目标和非目标

### 当前阶段目标

第一阶段要把智能问数主链跑通并协议化：

- 建立 `capability_manifest`，让 LeadAgent 只看到业务能力、典型问题、指标/维度名称摘要、路由提示和不可回答范围。
- 建立 `BI_SOUL.md` 内部契约，并同步到 Hermes skill 和 AgentScopeShellAdapter。
- 让 LeadAgent 收敛为 Hermes-style Capability Router，不直接消费字段、表、SQL、blueprint 主体和完整语义资产详情。
- 保留 `DSL / QueryGraph / query_plan` 作为 DatasetAgent 内部语义计划。
- 由 Tools 负责 QueryGraph 编译、SQL 方言适配、SQL Guard、preview / execute 和 artifact 持久化。
- 标准化 `DatalogueEventEnvelope`，让现有 SSE 先映射到统一事件协议。
- 建立 `ask_bi` / `BIWorkbenchTool` 最小稳定契约，供 Chat、AgentScopeShellAdapter 和未来工作台复用。
- 建立 `ArtifactCard`、`primary_ref`、`related_refs`、Action Registry 和候选数据集确认协议。
- 用五件套验收主链一致性：页面、SSE/event、后端日志、Langfuse trace、query_artifact / conversation_state。

### 当前阶段非目标

以下内容不进入第一阶段主链实现：

- 不让 AgentScope 2.0 接管 `/chat/stream` 或 DatasetAgent runtime。
- 不开放 AgentScopeShellAdapter 公开 API、前端入口或独立 runner。
- 不启动 ReportAgent、PythonAgent、AuditAgent 的完整链路；相关动作可以禁用或只打开详情面板。
- 不实现完整多数据库方言矩阵；`sql_dialect_adapter.py` 只覆盖当前真实数据源。
- 不为旧会话迁移或回填 `artifact_card`、event envelope、refs 或新 conversation_state。
- 不让 LLM 直接生成可执行 SQL；LLM 只能生成或修复语义计划，SQL 执行依据必须来自 Tools。

## 三、目标架构

### 1. 总体链路

```text
User
  -> Chat as Shell Entry
  -> DatalogueEventEnvelope
  -> ask_bi / BIWorkbenchTool
  -> LeadAgent Capability Router
  -> capability_manifest
  -> DatasetAgent Runtime
  -> QueryGraph / query_plan
  -> QueryGraph Compiler
  -> SQL Dialect Adapter
  -> SQL Guard
  -> preview / execute
  -> QueryArtifact / ArtifactStore
  -> ArtifactCard / refs / actions
  -> Chat UI / AgentScopeShellAdapter / future BI Workbench
```

### 2. AgentScope 2.0 的位置

第一阶段 AgentScope 2.0 位于 Shell 外层：

```text
AgentScopeShellAdapter
  -> ask_bi
      -> Datalogue BI Core
  <- event envelope / ArtifactCard / refs
```

它只能调用 `ask_bi`，不能绕过 Datalogue 的 LeadAgent、DatasetAgent、SQL Guard 和 ArtifactStore。

### 3. 分层边界

所有跨层数据必须按 visibility 分层：

| 层级 | 可见对象 | 禁止对象 |
| --- | --- | --- |
| `llm_visible` | 业务摘要、候选数据集、指标/维度名称摘要、结果摘要、ArtifactCard 预览 | schema 明细、表字段、SQL、raw result、capsule、trace 主体 |
| `control_plane` | SQL、QueryGraph、Guard 结果、执行计划、artifact 元数据、conversation_state | 用户可见直接输出 |
| `trace_metadata` | task_id、trace_id、dataset_id、artifact_ref、event_type、耗时、失败原因 | 密钥、敏感数据、完整 raw result |

## 四、核心模块设计

### 1. `BI_SOUL.md` 内部契约

建议文件：

```text
datalogue-api/app/contracts/BI_SOUL.md
```

职责：

- 定义 LeadAgent、DatasetAgent、外层 Agent、AgentScopeShellAdapter 的不可越界规则。
- 规定 LLM 不直接执行 SQL，SQL 只能来自工具编译和 Guard 后的 control plane。
- 规定 schema、字段、SQL、raw result、capsule、trace 主体不进入用户可见或外层 Agent 可见面。
- 规定 ArtifactCard、event envelope 和 refs 只能承载摘要和引用句柄。
- 作为 Hermes skill、AgentScopeShellAdapter 和未来外部 Skill 的同步源。

同步方式：

```text
BI_SOUL.md
  -> hermes-skills/datalogue/SOUL.md
  -> AgentScopeShellAdapter policy injection
  -> future external skill packages
```

验收：

- `test_bi_soul_contract.py` 校验内部契约存在、禁止项完整、外部分发副本一致。
- 同步检查失败时 fail closed，不允许使用过期外部 SOUL 副本进入正式链路。

### 2. `capability_manifest`

职责：

- 把数据集能力压缩成 LeadAgent 可消费的业务能力广告。
- 只暴露业务能力、典型问题、指标/维度名称摘要、路由提示、不可回答范围、权限范围和质量状态。
- 不暴露字段、表、SQL、blueprint 主体、完整语义资产、样例行或 raw result。

核心字段：

```text
dataset_id
business_name
can_answer
cannot_answer
metrics
dimensions
typical_questions
route_hints
permission_scope
quality_status
schema_version
```

### 3. LeadAgent Capability Router

职责：

- 基于 `capability_manifest` 做数据集路由。
- 低置信时先给候选数据集和简短理由，让用户确认。
- 多数据集问题采用保守少量 fan-out。
- 不读取完整 schema、不生成 SQL、不访问 raw result。

第一阶段输出：

```text
selected_dataset_id
candidate_datasets
route_reason
confidence
needs_user_confirmation
cannot_answer_reason
```

### 4. Shared DatasetAgent Runtime

职责：

- 接收 LeadAgent 确认后的数据集和用户问题。
- 生成或修复内部语义计划：`DSL / QueryGraph / query_plan`。
- 调用 QueryGraph Compiler 和 SQL Guard。
- 负责 preview / execute、artifact 持久化和 result summary。

边界：

- DatasetAgent 内部可以使用字段、表、blueprint 和完整语义资产。
- 这些内容只能进入 control plane、artifact 或 trace，不直接暴露给 LeadAgent / AgentScope / 用户可见面。

### 5. QueryGraph Compiler / Dialect Adapter

第一阶段采用外壳封装：

```text
query_plan
  -> query_plan_compiler.py
  -> sql_dialect_adapter.py
  -> SQL Guard
  -> preview / execute
```

设计规则：

- `query_plan_compiler.py` 内部先复用现有 QueryGraph / SQL 生成 / Guard / preview 链路。
- `sql_dialect_adapter.py` 接口按方言注册表设计，但第一阶段只启用当前真实数据源。
- 未支持方言直接 fail closed，不让 LLM 猜测。
- 最终 SQL 只进入 `control_plane`、artifact 和 trace，不进入 `llm_visible`。

### 6. ToolAdapter 分层

`DatasetAgentToolAdapter` 必须固化三层输出：

```text
llm_visible:
  answer_summary
  candidate_datasets
  artifact_card
  user_next_actions

control_plane:
  query_plan
  sql
  sql_guard
  raw_preview
  artifact_ref
  retry_checkpoint

trace_metadata:
  task_id
  trace_id
  dataset_id
  datasource_type
  event_type
  latency_ms
  fallback_reason
```

验收重点：

- LeadAgent 和 AgentScopeShellAdapter 只能消费 `llm_visible` 和受控 refs。
- SQL、raw result、capsule、control_plane 不进入用户消息。

### 7. `DatalogueEventEnvelope`

现有 SSE 不直接替换，第一阶段先标准化为统一 envelope：

```text
event_id
task_id
trace_id
event_type
phase
visibility
payload
artifact_ref
created_at
```

典型事件：

```text
task.started
intent.understood
dataset.candidates
dataset.confirmation_required
dataset.selected
query_plan.created
sql_guard.checked
preview.ready
artifact.created
answer.completed
task.failed
```

后续 AgentScope event stream 通过 adapter 从该 envelope 映射，不第一阶段直接替换 SSE。

### 8. `ask_bi` / `BIWorkbenchTool`

最小稳定契约：

```text
AskBIRequest:
  question
  conversation_id
  user_context
  dataset_hint
  previous_artifact_ref

AskBIResponse:
  answer
  artifact_card
  primary_ref
  related_refs
  candidate_datasets
  event_summary
  retry_checkpoint
```

职责：

- 对 Chat、AgentScopeShellAdapter、未来 BI 工作台提供统一问数工具面。
- 内部第一阶段复用现有 Chat 主链，不复制第二套问数逻辑。
- 保证所有入口看到的是同一个 artifact 和 event 协议。

### 9. ArtifactCard / refs / actions

`ArtifactCard` 是用户可见产物壳：

```text
artifact_id
artifact_type
title
summary
preview_payload
primary_ref
related_refs
actions
created_at
status
```

第一阶段动作策略：

- `open_detail`：允许打开详情面板。
- `export`：进入 Action Registry，但默认禁用。
- `continue_edit`：只作为详情面板预留动作，不直接启动 ReportAgent。
- `retry`：从最后安全检查点重试。

### 10. AgentScopeShellAdapter

建议文件：

```text
datalogue-api/app/services/agentscope_shell_adapter.py
datalogue-api/app/services/agentscope_event_adapter.py
```

职责：

- 正式后端 service，不是测试目录脚本。
- 第一阶段只做内部调用和 contract test。
- 只允许调用 `ask_bi`。
- 只消费 event envelope、ArtifactCard 和 refs。
- 不开放公开 API、前端入口或独立 runner。

验收：

- contract test 证明 AgentScopeShellAdapter 无法直接访问 schema、SQL、raw result 或 control_plane。
- event adapter 能把 DatalogueEventEnvelope 映射为 AgentScope 可消费事件。
- AgentScopeShellAdapter 返回的回答和 ArtifactCard 与普通 Chat 主链一致。

### 11. 旧会话兼容策略

第一阶段不支持旧会话回放新协议：

- 历史 `conversation_state` 不迁移。
- 历史消息不回填 `artifact_card`。
- 历史 artifact 不伪造 `primary_ref / related_refs`。
- 历史 SSE 不补 event envelope。

旧会话展示策略：

- 保留原回答和历史消息展示。
- 缺 ArtifactCard 时不报错、不伪造、不触发新动作。
- 新 ArtifactCard、任务时间线和 refs 从协议上线后的新会话开始生效。

## 五、P0 开发计划

### P0.1 `capability_manifest`

目标：

- 建立数据集能力清单 schema 和生成服务。
- 明确 `capability_manifest` 只暴露业务摘要层信息。
- 增加泄露扫描，禁止字段、表、SQL、blueprint、资产详情进入 manifest。

验收：

- `test_capability_manifest.py` 通过。
- LeadAgent 路由输入中看不到 schema 明细。

### P0.1b `BI_SOUL.md` 内部契约

目标：

- 新增 `datalogue-api/app/contracts/BI_SOUL.md`。
- 新增 `soul_contract_sync.py` 或等价校验逻辑。
- 同步到 `hermes-skills/datalogue/SOUL.md`。
- AgentScopeShellAdapter 使用内部契约注入 policy。

验收：

- `test_bi_soul_contract.py` 通过。
- 内部契约和外部分发副本一致。

### P0.2 LeadAgent Capability Router

目标：

- LeadAgent 改为基于 `capability_manifest` 路由。
- 实现候选数据集确认。
- 保留保守 fan-out。
- 不让 LeadAgent 读取 schema 明细或 SQL。

验收：

- `test_lead_agent_capability_router.py` 通过。
- 低置信问题返回候选数据集和简短理由。

### P0.3 QueryGraph Compiler / Dialect Adapter

目标：

- 新增或改造 `query_plan_compiler.py`。
- 新增或改造 `sql_dialect_adapter.py`。
- 第一阶段只启用当前真实数据源方言。
- 未知方言 fail closed。

验收：

- `test_query_plan_compiler.py` 通过。
- `test_sql_dialect_adapter.py` 通过。
- LLM SQL 不能绕过工具直执行。

### P0.4 ToolAdapter 分层

目标：

- 固化 `llm_visible / control_plane / trace_metadata`。
- 让 DatasetAgent 输出可追溯 ArtifactRef。
- 保证 raw result 和 SQL 不进入用户可见输出。

验收：

- `test_subagent_tool_adapter.py` 增强用例通过。
- 泄露扫描无 SQL / schema / raw result 外泄。

### P0.5 Event Envelope

目标：

- 把现有 SSE 映射为 `DatalogueEventEnvelope`。
- 保持原 SSE 兼容，不第一阶段替换。
- 为 AgentScope event adapter 预留 mapping。

验收：

- `test_event_envelope.py` 通过。
- `/chat/stream` 中关键事件都有 `task_id / trace_id / artifact_ref`。

### P0.6 `ask_bi` 最小契约

目标：

- 新增 `bi_workbench_tool.py` 和 `schemas/bi_workbench.py`。
- 第一阶段内部复用现有 Chat 主链。
- 对 Chat 和 AgentScopeShellAdapter 提供统一问数工具面。

验收：

- `test_bi_workbench_tool.py` 通过。
- 同一问题通过 Chat 和 `ask_bi` 得到同一 artifact/ref 语义。

## 六、P1 / P1.5 / P2 开发计划

### P1.1 ArtifactCard

目标：

- 建立统一产物卡协议和前端组件。
- 支持 `preview_payload` 半强 schema。
- 支持 `primary_ref / related_refs`。
- 支持固定 Action Registry 和禁用态。

验收：

- 后端 `test_artifact_card_contract.py` 通过。
- 前端 `artifact-card.test.jsx` 通过。

### P1.2 Chat 业务级任务时间线

目标：

- 在现有 Chat 中承接任务理解、数据集匹配、BI 执行、结果产物、下一步动作。
- 第一阶段只展示业务级事件，不展开内部 trace。

验收：

- 前端时间线组件测试通过。
- 页面事件顺序与 SSE/event envelope 一致。

### P1.3 候选数据集确认

目标：

- 低置信时先列候选数据集和简短理由。
- 用户确认后继续执行。
- 不暴露 schema、字段或资产细节。

验收：

- 候选确认前不执行 SQL。
- 用户确认后能复用同一 task / checkpoint 继续。

### P1.4 Retry Checkpoint

目标：

- 保存最后安全检查点。
- 支持从候选确认、SQL Guard 后或 preview 前重试。
- checkpoint 不安全时降级为整任务重试。

验收：

- `test_retry_checkpoint.py` 通过。
- 页面 retry 不重复写入混乱 artifact。

### P1.5 AgentScope Shell Adapter

目标：

- AgentScopeShellAdapter 进入正式后端 service。
- 第一阶段只做内部 contract test。
- 只允许调用 `ask_bi`。
- 不开放公开入口。

验收：

- `test_agentscope_shell_adapter.py` 通过。
- `test_agentscope_event_adapter.py` 通过。

### P2 五件套验收和防泄露

目标：

- 按页面、SSE/event、日志、Langfuse、query_artifact / conversation_state 做真实链路验收。
- 对 schema、SQL、raw result、capsule、control_plane 做全链路泄露扫描。
- 验证旧会话不回填、不伪造 ArtifactCard。

验收：

- 主链问题能在五件套中用同一 `task_id / trace_id / artifact_ref` 对齐。
- `test_legacy_conversation_replay.py` 通过。

## 七、边界和约束

### 1. 可见性边界

以下内容不得进入 LeadAgent、AgentScopeShellAdapter 或用户可见输出：

- schema 明细
- 表名、字段名明细
- raw SQL
- raw result
- blueprint 主体
- 完整语义资产详情
- conversation capsule
- control_plane 主体
- Langfuse trace 主体

### 2. SQL 方言边界

- 第一阶段只覆盖当前真实数据源。
- 方言接口按注册表设计，后续可扩展。
- 未支持方言 fail closed。
- LLM 不负责猜测或改写数据库方言。

### 3. SOUL 归属边界

- Datalogue 内部 `BI_SOUL.md` 是 source of truth。
- Hermes skill 和 AgentScope policy 都是同步副本。
- 外部副本过期时必须阻断或至少在 contract test 中失败。

### 4. 旧会话边界

- 不迁移旧 `conversation_state`。
- 不为旧会话回填 ArtifactCard。
- 不伪造历史 refs。
- 新协议只保证上线后的新会话完整回放。

### 5. AgentScope 边界

- 第一阶段 AgentScope 不接管主链 runtime。
- AgentScope 只能通过 `ask_bi` 消费 BI 能力。
- AgentScope 不直接访问 DatasetAgent 内部工具、SQL Guard、数据库或 artifact store 写接口。

## 八、当前阶段完成后的 AgentScope 2.0 完整集成目标

当前阶段完成后，还需要设定三组目标，才能把 AgentScope 2.0 从“接入验证”推进到“完整集成”。

### G1：Shell Adapter 真实可用

目标：

- AgentScopeShellAdapter 能在内部 runner 中稳定调用 `ask_bi`。
- AgentScopeShellAdapter 能消费标准 event envelope、ArtifactCard 和 refs。
- AgentScopeShellAdapter 的回答、产物、trace 与普通 Chat 主链一致。

必须完成的工作：

- 增加 AgentScope optional live test。
- 把测试目录中的 Hermes-style MVP 经验迁移到正式 service。
- 增加 AgentScopeShellAdapter 的 Langfuse observation。
- 增加失败重试、超时和权限上下文透传。
- 建立 AgentScope 调用与 Datalogue `task_id / trace_id / artifact_ref` 的映射。

进入下一阶段的闸门：

- AgentScopeShellAdapter 连续通过真实问数用例。
- 与普通 Chat 主链产物一致。
- 未发现 schema / SQL / raw result 泄露。

### G2：AgentScope Event / Runner Adapter

目标：

- 建立 `AgentScopeEventAdapter`，把 DatalogueEventEnvelope 映射成 AgentScope event stream。
- 建立可选 remote runner 或 internal runner adapter。
- 明确 AgentScope session / memory 与 Datalogue conversation_state 的边界。

必须完成的工作：

- event stream 双向映射设计。
- runner 生命周期管理：start、cancel、timeout、retry、finalize。
- AgentScope memory 不直接替代 Datalogue conversation_state。
- AgentScope trace 与 Langfuse trace 建立父子关系。
- 引入灰度开关和回滚策略。

进入下一阶段的闸门：

- AgentScope runner 失败不会污染 Datalogue 主链状态。
- Chat 主链可以关闭 AgentScope 后继续正常工作。
- AgentScope event 与 SSE/event envelope 一致。

### G3：多 Agent 产品链路集成

目标：

- 评估 ReportAgent、PythonAgent、AuditAgent 是否进入工作台链路。
- 多 Agent 只消费 ArtifactCard、refs 和受控摘要，不直接读取 BI control plane。
- BI 查询仍由 Datalogue BI Core 负责，Report/Python/Audit 只做后续增强能力。

必须完成的工作：

- ReportAgent：基于 `artifact_ref` 生成报告，不直接重跑 SQL。
- PythonAgent：基于授权后的 export / sample artifact 进行分析，不直接访问数据库。
- AuditAgent：消费 trace metadata 和 event summary，不读取敏感 raw result。
- 工作台详情面板：支持继续编辑、导出、审计、报告生成。
- 权限和租户上下文贯穿 AgentScope 多 Agent 调用。

进入完整集成的闸门：

- AgentScope 可以编排多个增强 Agent，但 BI 主链依旧可独立运行。
- 每个增强 Agent 都有明确输入、输出、权限和失败隔离。
- 用户可见产物全部通过 ArtifactCard / refs 追溯。

## 九、完整集成 AgentScope 2.0 前必须补齐的后续工作

当前 P0/P1/P2 做完后，还需要做以下工作：

1. AgentScope optional live test 产品化：从实验测试目录迁移到正式 service contract test 和可选真实集成测试。
2. AgentScope 依赖管理：明确版本、安装方式、可选依赖开关和 CI 跳过策略。
3. AgentScopeEventAdapter：把 Datalogue event envelope 映射为 AgentScope event stream，同时保持 SSE 主链不被替换。
4. AgentScopeRunnerAdapter：设计 internal runner / remote runner 生命周期、取消、超时、重试和失败清理。
5. Trace 统一：建立 Datalogue trace 与 AgentScope trace 的父子关系，Langfuse 可回溯到同一个 `task_id`。
6. Session / Memory 边界：明确 AgentScope memory 不取代 conversation_state，只能持有可见摘要和 refs。
7. 权限上下文透传：用户、租户、数据集权限、Manifest 权限和 AgentScope 调用上下文必须一致。
8. 多 Agent 增强链路：ReportAgent、PythonAgent、AuditAgent 只能基于 refs 和授权产物工作。
9. 多方言扩展：在当前真实数据源稳定后，再按注册表扩展 PostgreSQL / MySQL / SQLite 等方言。
10. 独立 BI 工作台：从 Chat as Shell Entry 迁移到独立工作台时，复用 event envelope、ArtifactCard、refs 和 action registry。
11. 灰度与回滚：AgentScope runtime 进入主链前必须可按租户、用户、数据集或功能开关关闭。
12. 安全审计：对 prompt、event、artifact、trace、前端消息和导出结果做泄露扫描。

## 十、验收标准

### P0 验收

- `capability_manifest` 只输出业务摘要层信息。
- `BI_SOUL.md` 内部契约存在，并与 Hermes skill / AgentScope policy 同步。
- LeadAgent 基于能力清单路由，低置信返回候选数据集确认。
- QueryGraph Compiler 和 Dialect Adapter 跑通当前真实数据源。
- 未知方言 fail closed。
- `ask_bi` 可以复用现有主链返回标准响应。

### P1 验收

- Chat 可展示业务级任务时间线。
- ArtifactCard 能展示结果摘要、preview_payload、refs 和禁用动作。
- 候选数据集确认不泄露 schema、字段和资产详情。
- retry 能从安全检查点恢复或降级整任务重试。
- 旧会话缺 ArtifactCard 时不报错、不回填、不伪造。

### P1.5 验收

- AgentScopeShellAdapter 进入正式后端 service。
- AgentScopeShellAdapter 只通过 `ask_bi` 调用 BI 能力。
- AgentScopeShellAdapter 不开放公开 API。
- AgentScopeShellAdapter contract test 证明不会看到 schema、SQL、raw result 或 control_plane。

### P2 验收

- 页面、SSE/event、后端日志、Langfuse、query_artifact / conversation_state 五件套能用同一 `task_id / trace_id / artifact_ref` 对齐。
- 主链泄露扫描通过。
- 新会话完整写入 ArtifactCard、refs 和 event envelope。
- 旧会话保持原始展示，不支持新协议历史回放。

### AgentScope 2.0 完整集成验收

完整集成不是“装上 AgentScope 依赖”，而是达到以下条件：

- AgentScopeShellAdapter 能稳定调用 `ask_bi` 并通过真实链路验收。
- AgentScopeEventAdapter 与 DatalogueEventEnvelope 对齐。
- AgentScope runner 失败不会破坏 Datalogue 主链状态。
- AgentScope session / memory 与 Datalogue conversation_state 边界清晰。
- ReportAgent / PythonAgent / AuditAgent 等增强 Agent 只消费 refs 和授权产物。
- 权限、租户、trace、artifact、retry 和回滚策略完整。
- 关闭 AgentScope 开关后，现有 Chat 智能问数主链仍然可独立运行。
