# B-first C-ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先跑通智能问数核心链路，把 LeadAgent 收敛为 Hermes-style Capability Router，并用 C-ready 协议承接 Chat、`ask_bi`、event envelope、ArtifactCard、候选数据集确认和五件套验收。

**Architecture:** 第一阶段采用 “C-shaped product, B-governed BI core”：产品入口保留 Chat，但协议按未来 BI 工作台设计；BI 查询仍由 LeadAgent、DatasetAgent、Manifest、SQL Guard、QueryArtifact 和 conversation_state 受控执行。AgentScope 2.0 第一阶段作为 Shell Adapter 显式验证外层编排，只能调用 `ask_bi`；ReportAgent、PythonAgent、AuditAgent、完整工作台和 AgentScope 主链 runtime 都作为后续增强，不阻塞主链路。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、Langfuse、assistant-ui React、Vitest / Testing Library、pytest。

---

## 一、文件结构与职责

### 后端核心文件

- `datalogue-api/app/services/capability_manifest.py`：新增。生成和校验数据集能力清单，只输出业务能力、典型问题、指标/维度摘要、路由提示和不可回答范围。
- `datalogue-api/app/schemas/capability_manifest.py`：新增。定义 `CapabilityManifest`、`CapabilityManifestSummary`、审核状态和 API 出参 schema。
- `datalogue-api/app/contracts/BI_SOUL.md`：新增。作为 Datalogue BI 能力不可越界契约的内部 source of truth，再同步到 Hermes skill 和 AgentScopeShellAdapter。
- `datalogue-api/app/services/soul_contract_sync.py`：新增或改造。校验 Datalogue 内部 SOUL 契约与外部 skill / adapter 同步目标一致。
- `datalogue-api/app/api/dataset.py`：修改。增加能力清单读取接口或在现有数据集接口中附带能力摘要。
- `datalogue-api/app/services/dataset_router.py`：修改。让路由优先消费 `capability_manifest`，不再依赖 LeadAgent 直接读取 schema 明细。
- `datalogue-api/app/services/lead_agent_routing.py`：修改。收窄 LeadAgent 可见工具面，保留候选数据集确认和保守 fan-out。
- `datalogue-api/app/services/query_plan_compiler.py`：新增或改造为第一阶段 compiler 外壳。把 `DSL / QueryGraph / query_plan` 编译为受控 SQL，内部先复用现有 QueryGraph / SQL 生成 / Guard / preview 链路，并确保 LLM 输出的 SQL 不能直接作为执行依据。
- `datalogue-api/app/services/sql_dialect_adapter.py`：新增或改造为第一阶段 dialect adapter 外壳。根据数据源类型完成 SQL 方言适配，第一阶段只启用当前真实数据源方言，未知方言 fail closed，避免让 LLM 猜测不同数据库方言。
- `datalogue-api/app/services/subagent_planning/contracts.py`、`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/app/services/subagent_planning/sql_context.py`、`datalogue-api/app/services/subagent_planning/execution.py`：修改。对齐语义计划、编译、执行和失败修复边界。
- `datalogue-api/app/services/subagent_tool_adapter.py`：修改。固化 `llm_visible`、`control_plane`、`trace_metadata` 分层，并为 `ArtifactCard` 提供标准引用。
- `datalogue-api/app/services/bi_workbench_tool.py`：新增。实现 `ask_bi` / `BIWorkbenchTool` 最小稳定契约，内部第一阶段复用现有 Chat 主链。
- `datalogue-api/app/services/agentscope_shell_adapter.py`：新增。作为正式后端 service 实现 AgentScope 2.0 外层 Shell Adapter 最小验证，只允许调用 `ask_bi` 并消费标准 event envelope、ArtifactCard 和引用句柄；第一阶段不开放公开 API。
- `datalogue-api/app/services/agentscope_event_adapter.py`：新增或改造。作为正式后端 service 将 `DatalogueEventEnvelope` 映射为 AgentScope event stream 验证事件，不替换现有 `/chat/stream` SSE。
- `datalogue-api/app/schemas/bi_workbench.py`：新增。定义 `AskBIRequest`、`AskBIResponse`、`ArtifactCard`、`ArtifactAction`、`ArtifactRef`、`DatalogueEventEnvelope`。
- `datalogue-api/app/api/chat.py`：修改。把现有 SSE 映射成统一 event envelope，输出 ArtifactCard、candidate datasets、checkpoint 和 final payload。
- `datalogue-api/app/services/conversation_store.py`：修改。保存候选数据集确认、最小安全检查点和 retry 状态。
- `datalogue-api/app/services/artifact_store.py`、`datalogue-api/app/services/multiturn/query_artifacts.py`：修改。确保 `primary_ref`、`related_refs`、`artifact_card` 与 query artifact 可互相追溯。
- `datalogue-api/app/services/observability/tracer.py`：修改。对齐 event envelope、Langfuse observation 和 trace metadata。

### 后端测试文件

- `datalogue-api/tests/test_capability_manifest.py`：新增。覆盖能力清单字段边界、不可回答范围、审核状态和泄露扫描。
- `datalogue-api/tests/test_bi_soul_contract.py`：新增。覆盖 Datalogue 内部 SOUL 契约存在、禁止项完整、同步目标一致。
- `datalogue-api/tests/test_lead_agent_capability_router.py`：新增。覆盖单数据集、候选确认、无法回答和保守 fan-out。
- `datalogue-api/tests/test_query_plan_compiler.py`：新增。覆盖 DSL / QueryGraph 到 SQL 的工具编译、LLM SQL 禁止直执行和 control plane 边界。
- `datalogue-api/tests/test_sql_dialect_adapter.py`：新增。覆盖当前主数据源方言适配、非法方言降级和防泄露。
- `datalogue-api/tests/test_bi_workbench_tool.py`：新增。覆盖 `ask_bi` 入参、出参、内部转接和安全边界。
- `datalogue-api/tests/test_agentscope_shell_adapter.py`：新增。覆盖 AgentScope 只通过 `ask_bi` 调用 BI 能力、不暴露 schema / SQL / control_plane。
- `datalogue-api/tests/test_agentscope_event_adapter.py`：新增。覆盖 event envelope 到 AgentScope event stream 的只读映射和 visibility 边界。
- `datalogue-api/tests/test_event_envelope.py`：新增。覆盖 SSE 到 event envelope 的映射和 visibility 约束。
- `datalogue-api/tests/test_artifact_card_contract.py`：新增。覆盖 ArtifactCard、preview_payload、actions、refs 和禁用态。
- `datalogue-api/tests/test_retry_checkpoint.py`：新增。覆盖 checkpoint 校验、恢复和降级整任务重试。
- `datalogue-api/tests/test_chat.py`、`datalogue-api/tests/test_conversation.py`、`datalogue-api/tests/test_subagent_tool_adapter.py`：修改。补现有主链回归。
- `datalogue-api/tests/test_legacy_conversation_replay.py`：新增或修改。覆盖旧会话缺少 ArtifactCard / refs / event envelope 时不报错、不伪造新产物卡。

### 前端文件

- `datalogue-web/src/assistant/chat-adapter.js`：修改。解析统一 event envelope，并向 Chat 运行时传递业务级任务事件和 ArtifactCard。
- `datalogue-web/src/assistant/Thread.jsx`：修改。承接业务级任务时间线和轻量产物卡区域。
- `datalogue-web/src/assistant/MyMessage.jsx`：修改。渲染候选数据集确认、结果产物卡和 action 禁用态。
- `datalogue-web/src/components/artifact-card.jsx`：新增。统一渲染 `ArtifactCard` 外壳、preview_payload、refs 和 actions。
- `datalogue-web/src/components/task-timeline.jsx`：新增。渲染任务理解、数据集匹配、BI 执行、结果产物、下一步动作。
- `datalogue-web/src/styles.css`：修改。补 ArtifactCard、任务时间线、禁用动作和候选确认样式。

### 前端测试文件

- `datalogue-web/src/components/artifact-card.test.jsx`：新增。覆盖不同 artifact_type、禁用动作和未知动作安全忽略。
- `datalogue-web/src/components/task-timeline.test.jsx`：新增。覆盖业务级时间线渲染。
- `datalogue-web/src/assistant/chat-adapter.test.js`：新增或修改。覆盖 event envelope 到前端事件的映射。
- `datalogue-web/src/assistant/MyMessage.test.jsx`：新增或修改。覆盖候选数据集确认和 ArtifactCard 展示。

---

## 二、依赖顺序

```text
P0.1 capability_manifest schema
  -> P0.1b BI_SOUL internal contract
  -> P0.2 Capability Router
  -> P0.3 QueryGraph Compiler / Dialect Adapter
  -> P0.4 ToolAdapter 分层
  -> P0.5 event envelope
  -> P0.6 ask_bi 最小契约
  -> P1.1 ArtifactCard
  -> P1.2 Chat 任务时间线
  -> P1.3 候选数据集确认
  -> P1.4 retry checkpoint
  -> P1.5 AgentScope Shell Adapter
  -> P2.1 五件套验收
```

不能跳过的硬依赖：

- `ArtifactCard` 依赖 `ArtifactRef`、Action Registry 和 `preview_payload` schema。
- SOUL 内部契约是 LeadAgent、DatasetAgent、Hermes skill 和 AgentScopeShellAdapter 的共同边界，必须先固化再同步到外部入口。
- `ask_bi` 依赖 event envelope 和 `ArtifactCard` schema。
- AgentScope Shell Adapter 依赖 `ask_bi`、event envelope、ArtifactCard 和引用句柄，不依赖 AgentScope 接管 `/chat/stream`。
- ToolAdapter 分层依赖 QueryGraph Compiler / Dialect Adapter 明确 SQL 只进入 `control_plane`。
- `retry` 依赖最小安全检查点和 conversation_state / query_artifact 引用。
- 五件套验收依赖页面、SSE、日志、Langfuse 和 query_artifact 都能输出同一个 `task_id` / `trace_id` / `artifact_ref`。

---

## 三、P0 后端核心链路

### Task P0.1：定义 capability_manifest 最小模型

**Files:**
- Create: `datalogue-api/app/schemas/capability_manifest.py`
- Create: `datalogue-api/app/services/capability_manifest.py`
- Create: `datalogue-api/tests/test_capability_manifest.py`
- Modify: `datalogue-api/app/schemas/__init__.py`

- [ ] **Step 1：编写 schema 测试**

测试内容：

```python
def test_capability_manifest_rejects_internal_details():
    manifest = build_capability_manifest(
        dataset_id=12,
        business_name="工作日志",
        can_answer=["查询个人工作日志数量"],
        cannot_answer=["不能回答财务付款明细"],
        metrics=["日志数量"],
        dimensions=["人员", "日期"],
        typical_questions=["查询杨凯 2024 年工作日志"],
        route_hints=["工作日志", "日报"],
        raw_fields=["employee_name"],
    )

    visible = manifest.model_dump()

    assert visible["dataset_id"] == 12
    assert visible["quality_status"] in {"draft", "reviewed", "published"}
    assert "raw_fields" not in visible
    assert "employee_name" not in str(visible)
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_capability_manifest.py -q
```

Expected: FAIL，因为 schema 和 service 还不存在。

- [ ] **Step 2：实现最小 schema**

定义字段：

```python
class CapabilityManifest(BaseModel):
    dataset_id: int
    business_name: str
    can_answer: list[str]
    cannot_answer: list[str]
    metrics: list[str]
    dimensions: list[str]
    typical_questions: list[str]
    route_hints: list[str]
    permission_scope: str = "dataset"
    quality_status: Literal["draft", "reviewed", "published"] = "draft"
    schema_version: str = "capability_manifest.v1"
```

边界：不定义字段、表、SQL、blueprint、资产详情、样例行和 raw result 相关字段。

- [ ] **Step 3：实现 builder 和泄露扫描**

在 `capability_manifest.py` 中实现 `build_capability_manifest()`，对传入的内部字段参数直接忽略，并对输出做关键字扫描：

```python
FORBIDDEN_VISIBLE_KEYS = {
    "raw_sql",
    "sql",
    "table",
    "field",
    "blueprint",
    "asset_detail",
    "raw_result",
}
```

扫描命中时抛出 `ValueError("capability_manifest contains forbidden internal details")`。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_capability_manifest.py -q
```

Expected: PASS。

### Task P0.1b：定义 BI_SOUL 内部契约并同步到外部入口

**Files:**
- Create: `datalogue-api/app/contracts/BI_SOUL.md`
- Create or modify: `datalogue-api/app/services/soul_contract_sync.py`
- Modify: `hermes-skills/datalogue/SOUL.md`
- Create: `datalogue-api/tests/test_bi_soul_contract.py`

- [ ] **Step 1：编写契约一致性测试**

测试内容：

```python
def test_internal_bi_soul_is_source_of_truth():
    internal = load_internal_bi_soul()
    hermes = load_hermes_skill_soul()

    assert "不得直接访问 SQL" in internal
    assert "control_plane" in internal
    assert normalize_contract(internal) == normalize_contract(hermes)
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_bi_soul_contract.py -q
```

Expected: FAIL，因为内部契约和同步校验还不存在。

- [ ] **Step 2：新增内部 SOUL 契约**

`BI_SOUL.md` 至少覆盖：

```text
LeadAgent 不看 schema 明细
外层 Agent 只能调用 ask_bi
LLM 不直接生成可执行 SQL
raw SQL / raw result / capsule / trace 主体属于 control_plane
ArtifactCard / event envelope / refs 只能承载 llm_visible 摘要和引用
AgentScopeShellAdapter 不替代 Datalogue 真相源
```

- [ ] **Step 3：同步到 Hermes skill 和 AgentScopeShellAdapter**

第一阶段可以用同步函数或测试校验完成：

```text
BI_SOUL.md -> hermes-skills/datalogue/SOUL.md
BI_SOUL.md -> AgentScopeShellAdapter system prompt / policy injection
```

- [ ] **Step 4：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_bi_soul_contract.py -q
```

Expected: PASS。

### Task P0.2：让 LeadAgent 基于能力清单路由

**Files:**
- Modify: `datalogue-api/app/services/dataset_router.py`
- Modify: `datalogue-api/app/services/lead_agent_routing.py`
- Create: `datalogue-api/tests/test_lead_agent_capability_router.py`

- [ ] **Step 1：编写路由测试**

测试覆盖：

```python
def test_router_returns_candidate_datasets_without_schema_details():
    candidates = route_with_capabilities(
        "查询杨凯 2024 年工作日志",
        manifests=[
            capability("工作日志", can_answer=["查询工作日志"], route_hints=["工作日志", "日报"]),
            capability("合同管理", can_answer=["查询合同金额"], route_hints=["合同", "金额"]),
        ],
    )

    assert candidates[0].dataset_name == "工作日志"
    assert candidates[0].reason
    assert "字段" not in candidates[0].reason
    assert "SQL" not in candidates[0].reason
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_lead_agent_capability_router.py -q
```

Expected: FAIL。

- [ ] **Step 2：实现候选数据集结果结构**

候选项只包含：

```python
dataset_id
dataset_name
reason
confidence
requires_confirmation
```

不得包含 schema、字段、资产详情和 SQL。

- [ ] **Step 3：接入 LeadAgent 路由**

在 `lead_agent_routing.py` 中把数据集选择依据改为 `CapabilityManifest` 摘要；低置信时返回候选确认，不直接进入 DatasetAgent。

- [ ] **Step 4：运行回归**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_lead_agent_capability_router.py tests/test_lead_agent_routing.py -q
```

Expected: PASS。

### Task P0.3：定义 QueryGraph Compiler / Dialect Adapter

**Files:**
- Create or modify: `datalogue-api/app/services/query_plan_compiler.py`（第一阶段 compiler 外壳，内部复用现有链路）
- Create or modify: `datalogue-api/app/services/sql_dialect_adapter.py`（第一阶段 dialect adapter 外壳，内部先覆盖当前真实数据源）
- Modify: `datalogue-api/app/services/subagent_planning/contracts.py`
- Modify: `datalogue-api/app/services/subagent_planning/planner.py`
- Modify: `datalogue-api/app/services/subagent_planning/sql_context.py`
- Modify: `datalogue-api/app/services/subagent_planning/execution.py`
- Create: `datalogue-api/tests/test_query_plan_compiler.py`
- Create: `datalogue-api/tests/test_sql_dialect_adapter.py`

- [ ] **Step 1：编写语义计划编译测试**

断言 LLM 只能提供语义计划，不能把 SQL 直接作为执行依据：

```python
def test_query_plan_compiler_rejects_llm_sql_as_execution_source():
    plan = QueryPlan(
        metrics=["日志数量"],
        dimensions=["人员", "日期"],
        filters=[{"field": "人员", "op": "=", "value": "杨凯"}],
        llm_generated_sql="select * from worklog",
    )

    compiled = compile_query_plan(plan, dialect="postgresql")

    assert compiled.sql
    assert compiled.execution_source == "tool_compiler"
    assert "llm_generated_sql" not in compiled.user_visible_json()
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_query_plan_compiler.py -q
```

Expected: FAIL，因为 compiler 外壳和禁止直执行规则还未固化。

- [ ] **Step 2：实现 QueryGraph Compiler 外壳**

Compiler 负责：

```text
DSL / QueryGraph schema 校验
指标、维度、过滤、时间范围归一化
语义资产到物理字段 / 表的受控映射
SQL 生成
SQL Guard 前置上下文组装
```

LLM 失败修复时只能修语义计划，不能把 SQL 文本直接提升为执行 SQL。

第一阶段不重写完整 compiler；外壳内部先调用现有 QueryGraph、SQL context、SQL 生成、Guard 和 preview 能力，先把上层依赖的稳定契约、trace、泄露扫描和 fail-closed 行为固化。

- [ ] **Step 3：实现 SQL Dialect Adapter**

Adapter 负责：

```text
按 datasource type 选择方言
处理 limit / date / identifier quoting / aggregate 等方言差异
非法或未知方言 fail closed
输出 trace-only 编译摘要
```

第一阶段只启用当前真实数据源方言；其他方言只保留注册表接口，未实现时必须 fail closed。

- [ ] **Step 4：接入现有执行链**

将 DatasetAgent 内部 `plan_query -> compile_query_plan -> adapt_dialect -> guard_sql -> preview_sql -> persist_artifact` 串起来；最终 SQL 只进入 `control_plane`、query_artifact、trace 和执行层，不进入 `llm_visible`、ArtifactCard 或 user-visible event。

- [ ] **Step 5：预留内部替换边界**

为 compiler 输出增加 `schema_version`、`compiler_version`、`dialect`、`execution_source`、`trace_metadata`，确保后续替换内部 QueryGraph / SQL 生成实现时，上层 `BIWorkbenchTool`、event envelope、ArtifactCard 和 AgentScope adapter 不需要改协议。

- [ ] **Step 6：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_query_plan_compiler.py tests/test_sql_dialect_adapter.py tests/test_subagent_run.py -q
```

Expected: PASS。

### Task P0.4：固化 ToolAdapter 分层出参

**Files:**
- Modify: `datalogue-api/app/services/subagent_tool_adapter.py`
- Modify: `datalogue-api/tests/test_subagent_tool_adapter.py`

- [ ] **Step 1：补充分层出参测试**

断言：

```python
def test_subagent_tool_result_does_not_leak_control_plane_to_llm_visible():
    result = SubAgentToolResult(
        llm_visible={"status": "completed", "display_summary": "查询完成", "result_ref": "result://1"},
        control_plane={"raw_sql": "select * from t", "raw_result": [{"name": "x"}]},
        trace_metadata={"schema_version": "subagent_tool_result.v1"},
    )

    assert "raw_sql" not in str(result.llm_visible)
    assert result.control_plane["raw_sql"].startswith("select")
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_subagent_tool_adapter.py -q
```

Expected: FAIL 或现有测试暴露协议缺口。

- [ ] **Step 2：实现分层协议**

确保 `SubAgentToolResult` 至少包含：

```python
llm_visible
control_plane
trace_metadata
```

并给 `llm_visible` 加 size guard 和敏感字段扫描。

- [ ] **Step 3：迁移调用点**

让 LeadAgent 和 Chat 只消费 `llm_visible`；`control_plane` 只写入 artifact、conversation_state、日志或 trace。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_subagent_tool_adapter.py tests/test_subagent_run.py -q
```

Expected: PASS。

### Task P0.5：定义 event envelope 并映射 SSE

**Files:**
- Create: `datalogue-api/app/schemas/bi_workbench.py`
- Modify: `datalogue-api/app/api/chat.py`
- Create: `datalogue-api/tests/test_event_envelope.py`

- [ ] **Step 1：编写 event envelope 测试**

```python
def test_user_visible_event_rejects_raw_sql():
    event = DatalogueEventEnvelope(
        event_type="dataset.query.completed",
        visibility="user_visible",
        task_id="task-1",
        payload={"raw_sql": "select * from t"},
    )

    with pytest.raises(ValueError):
        validate_event_visibility(event)
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_event_envelope.py -q
```

Expected: FAIL。

- [ ] **Step 2：实现 schema**

最小字段：

```python
event_id
event_type
task_id
conversation_id
visibility
payload
trace_id
created_at
```

`visibility` 支持：

```text
user_visible
trace_only
control_plane
```

- [ ] **Step 3：映射现有 `/chat/stream`**

在 `chat.py` 中把关键 checkpoint 映射成：

```text
route.started
dataset.selected
clarification.required
dataset.query.started
dataset.query.completed
artifact.created
answer.completed
error.blocked
```

保持现有前端流式体验不退化。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_event_envelope.py tests/test_chat.py -q
```

Expected: PASS。

### Task P0.6：实现 ask_bi / BIWorkbenchTool 最小契约

**Files:**
- Create: `datalogue-api/app/services/bi_workbench_tool.py`
- Modify: `datalogue-api/app/schemas/bi_workbench.py`
- Create: `datalogue-api/tests/test_bi_workbench_tool.py`

- [ ] **Step 1：编写契约测试**

```python
def test_ask_bi_returns_stable_outer_contract():
    response = ask_bi(
        AskBIRequest(
            question="查询杨凯 2024 年工作日志",
            conversation_id=1,
            caller="chat",
            confirmed_dataset_id=12,
            context_refs=[],
            request_options={},
        )
    )

    assert response.task_id
    assert response.status in {"completed", "waiting_user", "blocked"}
    assert response.event_envelope
    assert response.answer is not None
    assert "raw_sql" not in response.model_dump_json()
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_bi_workbench_tool.py -q
```

Expected: FAIL。

- [ ] **Step 2：实现请求和响应 schema**

`AskBIRequest` 字段：

```text
question
conversation_id
caller
confirmed_dataset_id
context_refs
request_options
```

`AskBIResponse` 字段：

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

- [ ] **Step 3：内部转接现有主链**

第一阶段 `BIWorkbenchTool` 不重写主链，只封装当前 Chat / LeadAgent / DatasetAgent 输出。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_bi_workbench_tool.py tests/test_chat.py -q
```

Expected: PASS。

---

## 四、P1 前端 C-ready 承接

### Task P1.1：实现 ArtifactCard

**Files:**
- Create: `datalogue-web/src/components/artifact-card.jsx`
- Create: `datalogue-web/src/components/artifact-card.test.jsx`
- Modify: `datalogue-web/src/styles.css`

- [ ] **Step 1：编写组件测试**

```jsx
it('renders disabled export without creating a download link', () => {
  render(<ArtifactCard artifact={artifactWithDisabledExport} />);

  expect(screen.getByText('导出能力将在后续版本开放')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /导出/ })).not.toBeInTheDocument();
});
```

Run:

```bash
cd datalogue-web
npm run test -- artifact-card
```

Expected: FAIL。

- [ ] **Step 2：实现组件**

组件只渲染：

```text
title
status
summary_for_chat
preview_payload
primary_ref
related_refs
actions
```

未知 `action_type` 不显示，并记录 console debug 或 trace-only hook。

- [ ] **Step 3：补样式**

在 `styles.css` 中补 `.artifact-card`、`.artifact-card-action`、`.artifact-card-action[disabled]`、`.artifact-ref`。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-web
npm run test -- artifact-card
```

Expected: PASS。

### Task P1.2：实现业务级任务时间线

**Files:**
- Create: `datalogue-web/src/components/task-timeline.jsx`
- Create: `datalogue-web/src/components/task-timeline.test.jsx`
- Modify: `datalogue-web/src/assistant/Thread.jsx`
- Modify: `datalogue-web/src/styles.css`

- [ ] **Step 1：编写时间线测试**

```jsx
it('renders business timeline without technical details', () => {
  render(<TaskTimeline events={timelineEvents} />);

  expect(screen.getByText('任务理解')).toBeInTheDocument();
  expect(screen.getByText('数据集匹配')).toBeInTheDocument();
  expect(screen.queryByText(/select \\*/i)).not.toBeInTheDocument();
});
```

Run:

```bash
cd datalogue-web
npm run test -- task-timeline
```

Expected: FAIL。

- [ ] **Step 2：实现五类节点**

节点类型：

```text
task_understood
dataset_matching
bi_execution
artifact_created
next_action
```

- [ ] **Step 3：接入 Thread**

在 `Thread.jsx` 中根据 message metadata 或 adapter state 渲染 `TaskTimeline`。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-web
npm run test -- task-timeline
```

Expected: PASS。

### Task P1.3：承接候选数据集确认

**Files:**
- Modify: `datalogue-web/src/assistant/MyMessage.jsx`
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Create or modify: `datalogue-web/src/assistant/MyMessage.test.jsx`

- [ ] **Step 1：编写候选确认测试**

```jsx
it('shows candidate datasets with reasons but no schema details', () => {
  render(<MyMessage message={candidateDatasetMessage} />);

  expect(screen.getByText('工作日志')).toBeInTheDocument();
  expect(screen.getByText(/匹配工作日志查询/)).toBeInTheDocument();
  expect(screen.queryByText(/字段/)).not.toBeInTheDocument();
});
```

Run:

```bash
cd datalogue-web
npm run test -- MyMessage
```

Expected: FAIL。

- [ ] **Step 2：实现候选展示**

展示：

```text
dataset_name
short_reason
confirm action
change_dataset action
```

不展示 schema、字段、表、资产详情。

- [ ] **Step 3：发送确认**

确认时把 `confirmed_dataset_id` 通过 chat adapter 写回后端，并继续原始问题。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-web
npm run test -- MyMessage chat-adapter
```

Expected: PASS。

### Task P1.4：支持 retry checkpoint 动作

**Files:**
- Modify: `datalogue-api/app/services/conversation_store.py`
- Modify: `datalogue-api/app/api/chat.py`
- Create: `datalogue-api/tests/test_retry_checkpoint.py`
- Modify: `datalogue-web/src/components/artifact-card.jsx`
- Modify: `datalogue-web/src/components/artifact-card.test.jsx`

- [ ] **Step 1：编写后端 checkpoint 测试**

```python
def test_retry_uses_last_safe_checkpoint_or_falls_back():
    restored = restore_retry_checkpoint(
        checkpoint_ref="checkpoint://task-1/query_context_ready",
        user_id="1",
        conversation_id=1,
    )

    assert restored.retry_scope == "last_safe_checkpoint"
    assert restored.dataset_id == 12
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_retry_checkpoint.py -q
```

Expected: FAIL。

- [ ] **Step 2：实现安全检查点结构**

允许：

```text
dataset_confirmed
query_context_ready
artifact_generation_failed
```

校验：

```text
user_id
conversation_id
task_id
permission_scope
expires_at
```

- [ ] **Step 3：实现 retry 事件**

事件：

```text
retry.started
retry.checkpoint_restored
retry.fallback_to_whole_task
retry.completed
retry.failed
```

- [ ] **Step 4：前端触发 retry**

ArtifactCard 点击 `retry` 时只发送 `checkpoint_ref`，不发送内部状态。

- [ ] **Step 5：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_retry_checkpoint.py tests/test_chat.py -q
cd ../datalogue-web
npm run test -- artifact-card
```

Expected: PASS。

### Task P1.5：AgentScope Shell Adapter 最小验证

**Files:**
- Create: `datalogue-api/app/services/agentscope_shell_adapter.py`（正式 service，第一阶段不开放公开 API）
- Create or modify: `datalogue-api/app/services/agentscope_event_adapter.py`（正式 service，第一阶段只供内部验证和测试）
- Create: `datalogue-api/tests/test_agentscope_shell_adapter.py`
- Create: `datalogue-api/tests/test_agentscope_event_adapter.py`

- [ ] **Step 1：编写 Shell Adapter 边界测试**

断言 AgentScope 只能通过 `ask_bi` 使用 BI 能力：

```python
def test_agentscope_shell_adapter_only_calls_ask_bi():
    adapter = AgentScopeShellAdapter(allowed_tools=["ask_bi"])

    response = adapter.run("查询杨凯 2024 年工作日志")

    assert response.used_tools == ["ask_bi"]
    assert response.artifact_card.primary_ref
    assert "raw_sql" not in response.model_dump_json()
    assert "control_plane" not in response.model_dump_json()
```

Run:

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_agentscope_shell_adapter.py -q
```

Expected: FAIL，因为 adapter 外壳还不存在。

- [ ] **Step 2：实现 AgentScopeShellAdapter 外壳**

第一阶段只做最小验证：

```text
AgentScope 2.0 Agent / runner
  -> ask_bi / BIWorkbenchTool
  -> DatalogueEventEnvelope
  -> ArtifactCard / refs
```

AgentScope 可见工具白名单第一阶段只包含 `ask_bi`；不得注册 schema、SQL、preview、database、artifact body 或 control plane 工具。

第一阶段不得新增公开 API route，不接前端入口，不做独立 runner 进程；只通过 service 内部调用和 contract test 验证 AgentScope 2.0 接入边界。

- [ ] **Step 3：实现 AgentScopeEventAdapter 验证映射**

将 `DatalogueEventEnvelope` 映射为 AgentScope event stream 验证事件：

```text
user_visible -> AgentScope shell visible event
trace_only -> AgentScope trace event
control_plane -> 不进入 AgentScope 可见事件
```

第一阶段不替换 `/chat/stream` SSE，只验证映射边界。

- [ ] **Step 4：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_bi_workbench_tool.py tests/test_event_envelope.py -q
```

Expected: PASS。

---

## 五、P2 验收与防泄露

### Task P2.1：P0 主链路五件套验收用例

**Files:**
- Create: `datalogue-api/tests/test_bi_main_chain_acceptance.py`
- Modify: `datalogue-api/tests/test_chat.py`
- Modify: `datalogue-web/src/assistant/chat-adapter.test.js`

- [ ] **Step 1：定义验收用例矩阵**

核心用例：

```text
单数据集问数成功
低置信候选数据集确认
无法回答范围拒答
受控查询失败后 retry
历史回放展示 ArtifactCard
```

历史回放口径调整为：旧会话缺少 ArtifactCard 时不回填、不伪造、不报错；ArtifactCard 回放只要求新协议上线后的新会话。

- [ ] **Step 2：每个 P0 用例核对五件套**

核对项：

```text
真实页面展示
SSE event envelope
后端 chat.stream checkpoint 日志
Langfuse trace / observation
query_artifact / conversation_state
```

- [ ] **Step 3：自动测试覆盖可自动化部分**

pytest 断言：

```python
assert final_payload["answer"]
assert final_payload["artifact_card"]["primary_ref"]
assert "raw_sql" not in json.dumps(final_payload["artifact_card"], ensure_ascii=False)
assert query_artifact is not None
assert conversation_state is not None
```

旧会话回归断言：

```python
assert legacy_message.get("artifact_card") is None
assert "raw_sql" not in json.dumps(legacy_message, ensure_ascii=False)
```

- [ ] **Step 4：人工验收记录模板**

每个主链路用例记录：

```text
用例名
conversation_id
task_id
trace_id
artifact_ref
页面截图位置
SSE 关键事件
后端日志 checkpoint
Langfuse observation
数据库状态
结论
```

### Task P2.2：轻量协议验收

**Files:**
- Create: `datalogue-api/tests/test_reserved_actions_contract.py`
- Modify: `datalogue-web/src/components/artifact-card.test.jsx`

- [ ] **Step 1：覆盖禁用动作**

检查：

```text
export enabled=false
continue_edit enabled=false 或只打开 detail panel
未知 action 被安全忽略
ReportAgent 未被启动
```

- [ ] **Step 2：覆盖防泄露**

断言禁用动作 payload 不含：

```text
raw_sql
raw_result
schema
capsule
trace body
control_plane
```

- [ ] **Step 3：运行测试**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_reserved_actions_contract.py -q
cd ../datalogue-web
npm run test -- artifact-card
```

Expected: PASS。

### Task P2.3：全量回归命令

- [ ] **Step 1：后端核心回归**

```bash
cd datalogue-api
.venv/bin/python -m pytest tests/test_capability_manifest.py tests/test_bi_soul_contract.py tests/test_lead_agent_capability_router.py tests/test_query_plan_compiler.py tests/test_sql_dialect_adapter.py tests/test_bi_workbench_tool.py tests/test_event_envelope.py tests/test_agentscope_shell_adapter.py tests/test_agentscope_event_adapter.py tests/test_artifact_card_contract.py tests/test_retry_checkpoint.py tests/test_legacy_conversation_replay.py tests/test_chat.py -q
```

Expected: PASS。

- [ ] **Step 2：后端默认回归**

```bash
cd datalogue-api
.venv/bin/python -m pytest -q
```

Expected: PASS，允许既有 warning。

- [ ] **Step 3：前端回归**

```bash
cd datalogue-web
npm run lint
npm run test
npm run build
```

Expected: PASS，允许既有 warning。

- [ ] **Step 4：真实链路验收**

启动本地服务后，在浏览器验证：

```text
候选数据集确认不暴露 schema
最终 answer 与 ArtifactCard 一致
SSE event envelope 中 task_id / trace_id / artifact_ref 一致
后端日志存在 chat.stream checkpoint
Langfuse trace 存在对应 observation
query_artifact / conversation_state 可回放
```

---

## 六、P0 / P1 / P2 边界

### P0 必须完成

- `capability_manifest` schema 和生成逻辑。
- `BI_SOUL.md` 内部契约和同步校验。
- LeadAgent 基于能力清单路由。
- 候选数据集确认。
- QueryGraph Compiler / Dialect Adapter 外壳。
- SQL 方言适配第一阶段只覆盖当前真实数据源，未知方言 fail closed。
- ToolAdapter 分层。
- event envelope。
- `ask_bi` 最小契约。
- P0 主链路五件套验收。

### P1 必须完成

- Chat 内业务级任务时间线。
- `ArtifactCard`。
- Action Registry 渲染。
- `export` / `continue_edit` 禁用态。
- `retry` 最后安全检查点。
- 历史回放可展示引用和产物卡。
- 旧会话缺少 ArtifactCard 时不回填、不伪造；新 ArtifactCard 回放只对新协议会话生效。
- AgentScope Shell Adapter 最小验证，只能调用 `ask_bi`，不接管 BI 主链 runtime。
- AgentScopeShellAdapter 位于正式后端 service，但第一阶段无公开 API、无前端入口、无独立 runner。

### P2 必须完成

- 防泄露扫描。
- Langfuse / 后端日志 / event envelope 对齐。
- 轻量协议验收。
- 正式文档和开发交接。

---

## 七、第一阶段不做

- 不启动 ReportAgent 真实编辑链路。
- 不开放 PythonAgent 数据切片分析。
- 不实现完整 AuditAgent 分层视图。
- 不实现完整 BI 工作台 runtime。
- 不迁移旧 conversation_state，不为旧会话回填 ArtifactCard、event envelope 或 refs。
- 不让 AgentScope Shell Adapter 访问 schema、SQL、数据库、raw result、capsule 或 `control_plane`。
- 不为 AgentScopeShellAdapter 开放公开 API route、前端入口或独立 runner 进程。
- 不让 LLM 生成的 SQL 直接作为执行依据。
- 不把 SQL 方言适配交给 LLM 猜测；第一阶段不实现多数据库完整方言矩阵。
- 不让 AgentScope 接管 `/chat/stream` 主链。
- 不实现完整 DAG 级子任务 retry。
- 不开放导出文件生成或完整数据导出。
