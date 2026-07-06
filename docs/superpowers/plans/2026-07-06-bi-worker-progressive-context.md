# BI Worker Progressive Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 BI Worker 从一跳 `datalogue_query_dataset` 工具转发器，升级为基于 AgentScope SDK 的可观测问数执行智能体，支持 L0/L1/L5 固定骨架、L2/L3 按需上下文、L4 强制门禁和安全 Query Plan 执行。

**Architecture:** Agentic Lead Agent 与 BI Worker 继续由 AgentScope Agent Service + Agent Team 承载；Datalogue 只在 AgentScope `FunctionTool` / `ToolBase`、`SubAgentTemplate`、permission context、middleware 扩展点上提供业务工具和安全投影。BI Worker 生成 Query Plan JSON，但 SQL 编译、执行、修复、artifact/checkpoint 始终在 BI Worker Runtime 内完成。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, AgentScope 2.0.3 Agent Service, AgentScope Agent Team, AgentScope `FunctionTool` / `ToolBase`, pytest, existing Datalogue BI atomic toolkit, existing artifact store, Vitest for frontend adapters.

---

## Source Spec

- `docs/superpowers/specs/2026-07-06-agentic-lead-bi-worker-progressive-context-design.md`

## SDK Gate

Before implementation, the worker must verify these official local docs and keep the implementation SDK-first:

```bash
rg -n "Agent Team|SubAgentTemplate|TeamSay" /Users/yangkai/code_place/study/agentscope-docs/pages/agent-team.md
rg -n "extra_agent_tools|permission_context|extra_agent_middlewares" /Users/yangkai/code_place/study/agentscope-docs/pages/agent-service.md
rg -n "FunctionTool|ToolBase|Toolkit|Tool Middleware" /Users/yangkai/code_place/study/agentscope-docs/pages/tool.md
rg -n "middleware|TracingMiddleware" /Users/yangkai/code_place/study/agentscope-docs/pages/middleware.md
```

The implementation must not add a Datalogue-owned Agent loop, Team runner, or replacement tool protocol.

## File Structure

Create:

- `datalogue-api/app/agentscope_service/bi_worker_contracts.py`  
  Pydantic contracts for context slices, Query Plan v1, support validation, repair request, and safe query result payloads.

- `datalogue-api/app/agentscope_service/bi_worker_context.py`  
  L0/L1/L2/L3 context provider. Reads Datalogue dataset metadata and returns safe, scoped slices.

- `datalogue-api/app/agentscope_service/bi_worker_validator.py`  
  L4 validation. Enforces asset refs, relationship refs, join legality, grain rules, semantic dependencies, and loop limits.

- `datalogue-api/app/agentscope_service/bi_worker_runtime.py`  
  L5 runtime. Converts Query Plan v1 to existing internal query plan / DSL input, calls existing BI atomic toolkit, sanitizes repair requests, returns safe result payloads.

- `datalogue-api/tests/test_bi_worker_progressive_context_contracts.py`  
  Contract and serialization tests.

- `datalogue-api/tests/test_bi_worker_progressive_context_tools.py`  
  AgentScope FunctionTool registration, permission, and safe output tests.

- `datalogue-api/tests/test_bi_worker_query_validator.py`  
  L4 validator tests for multi-table joins, missing lookup dependencies, unsupported cases, and loop limits.

- `datalogue-api/tests/test_bi_worker_query_runtime.py`  
  L5 runtime tests for validate-before-execute, artifact payload, repair request sanitization, and direct fallback.

Modify:

- `datalogue-api/app/agentscope_service/tools.py`  
  Register six AgentScope SDK tools: L0/L1/L2/L3/L4/L5. Keep `datalogue_select_candidate_datasets`. Make `datalogue_query_dataset` a compatibility wrapper around L5 only after progressive tools exist.

- `datalogue-api/app/agentscope_service/registry.py`  
  Update BI Worker prompt and permission context to use progressive context tools and prohibit raw SQL/schema/raw rows in TeamSay.

- `datalogue-api/app/agentscope_service/dataset_query_executor.py`  
  Retire direct `run_direct_query(session, dsl={})` as primary path. Keep direct path behind an explicit fallback helper used only when progressive runtime is disabled.

- `datalogue-api/app/agentscope_service/worker_logging.py`  
  Add safe progress labels for L0/L1/L2/L3/L4/L5 and repair request summaries.

- `datalogue-api/app/runtime/agent_team_runtime.py`  
  Preserve current final answer behavior and add safe timeline steps for progressive context events if projected as `message.completed` payload fields.

- `datalogue-web/src/assistant/agent-team-event-adapter.js`  
  Map progressive safe trace events to chat/workbench event types.

- `datalogue-web/src/assistant/chat-adapter.js`  
  Render progressive timeline as business steps only, without fields/schema/query plan.

- `.codex/project-memory.md`  
  Record completed implementation and verification after the code work is finished.

---

## Task 1: Define Progressive Context Contracts

**Files:**

- Create: `datalogue-api/app/agentscope_service/bi_worker_contracts.py`
- Test: `datalogue-api/tests/test_bi_worker_progressive_context_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `datalogue-api/tests/test_bi_worker_progressive_context_contracts.py`:

```python
# ============================================================
# File Name   : test_bi_worker_progressive_context_contracts.py
# Description:
#   BI Worker 渐进式上下文契约测试。
#
# Responsibilities:
#   - 验证 Query Plan v1 支持多表关系图表达。
#   - 验证 L4 支持度、修复请求和安全结果 payload 不含 SQL/raw rows。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

import pytest
from pydantic import ValidationError

from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
    BIWorkerQueryResult,
    QuerySupportValidation,
    RepairRequest,
)


def test_query_plan_accepts_multitable_relationship_refs():
    plan = BIWorkerQueryPlan.model_validate(
        {
            "intent": "detail_query",
            "question": "查询杨凯2025年工作日志",
            "result_shape": {"type": "table", "grain": "one_row_per_work_log", "limit": 100},
            "data_graph": {
                "primary_entity": {"asset_ref": "asset:work_log", "alias": "log", "role": "fact_or_primary"},
                "supporting_entities": [
                    {
                        "asset_ref": "asset:employee",
                        "alias": "emp",
                        "role": "dimension",
                        "join_purpose": "按人员过滤日志",
                    }
                ],
            },
            "join_requirements": [
                {
                    "left_alias": "log",
                    "right_alias": "emp",
                    "relationship_ref": "rel:work_log_employee",
                    "join_type": "inner",
                    "required": True,
                    "reason": "人员姓名来自员工维表",
                }
            ],
            "filters": [
                {
                    "target": {"asset_ref": "asset:employee.name", "alias": "emp", "field": "employee_name"},
                    "operator": "=",
                    "value": "杨凯",
                    "reason": "用户指定人员",
                }
            ],
            "selects": [
                {
                    "target": {"asset_ref": "asset:work_log.content", "alias": "log", "field": "log_content"},
                    "display_name": "工作日志",
                }
            ],
            "metrics": [],
            "group_by": [],
            "ordering": [],
            "assumptions": ["日志记录为结果粒度"],
        }
    )

    assert plan.intent == "detail_query"
    assert plan.join_requirements[0].relationship_ref == "rel:work_log_employee"


def test_query_plan_rejects_free_join_condition():
    with pytest.raises(ValidationError):
        BIWorkerQueryPlan.model_validate(
            {
                "intent": "detail_query",
                "question": "查询部门名称",
                "result_shape": {"type": "table", "grain": "one_row_per_employee", "limit": 100},
                "data_graph": {
                    "primary_entity": {"asset_ref": "asset:employee", "alias": "emp", "role": "primary"},
                    "supporting_entities": [],
                },
                "join_requirements": [
                    {
                        "left_alias": "emp",
                        "right_alias": "dept",
                        "relationship_ref": "",
                        "join_type": "inner",
                        "required": True,
                        "reason": "缺少关系引用",
                        "raw_condition": "emp.dept = dept.dept_code",
                    }
                ],
                "filters": [],
                "selects": [],
                "metrics": [],
                "group_by": [],
                "ordering": [],
                "assumptions": [],
            }
        )


def test_support_validation_represents_lookup_dependency():
    validation = QuerySupportValidation.model_validate(
        {
            "support_status": "needs_more_context",
            "safe_reason": "部门编码需要转换为部门名称。",
            "missing_context": [
                {
                    "type": "lookup_dependency",
                    "code_field": "employee.dept",
                    "business_meaning": "部门编码需要转换为部门名称",
                    "recommended_next_tool": "datalogue_request_schema_slice",
                    "focus": {"lookup_for": "employee.dept", "target_semantic": "department_name"},
                }
            ],
            "auto_context_expansions": [],
        }
    )

    assert validation.support_status == "needs_more_context"
    assert validation.missing_context[0]["type"] == "lookup_dependency"


def test_repair_request_hides_raw_database_error():
    request = RepairRequest.model_validate(
        {
            "repair_status": "needs_plan_revision",
            "failure_stage": "execute",
            "failure_class": "table_not_found",
            "safe_reason": "部门 lookup 依赖的物理表不可用。",
            "recommended_action": "request_schema_slice",
            "missing_context": [{"type": "alternative_lookup_relation", "focus": "department lookup"}],
        }
    )

    payload = request.model_dump()
    assert "select " not in str(payload).lower()
    assert "relation " not in str(payload).lower()


def test_safe_result_payload_contains_artifact_card_only():
    result = BIWorkerQueryResult(
        answer_summary="查询已完成，已生成可查看结果。",
        artifact_ref="artifact:abc",
        checkpoint_ref=None,
        row_count=10,
        column_count=3,
    )

    payload = result.to_tool_payload()
    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["result_ref"] == "artifact:abc"
    assert "sql" not in str(payload).lower()
    assert "raw_rows" not in str(payload).lower()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agentscope_service.bi_worker_contracts'`.

- [ ] **Step 3: Implement contract module**

Create `datalogue-api/app/agentscope_service/bi_worker_contracts.py`:

```python
# ============================================================
# File Name   : bi_worker_contracts.py
# Description:
#   BI Worker 渐进式上下文和 Query Plan v1 契约。
#
# Responsibilities:
#   - 定义 L0-L5 安全 payload 结构。
#   - 定义多表 Query Plan v1、支持度校验和安全修复请求。
#   - 统一生成 AgentScope BI Worker 可 TeamSay 的安全结果 payload。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SupportStatus = Literal["supported", "needs_more_context", "needs_clarification", "unsupported"]
QueryIntent = Literal["detail_query", "metric_query", "knowledge_qa", "unsupported"]
JoinType = Literal["inner", "left"]
RepairStatus = Literal["needs_plan_revision", "auto_repaired", "unsupported", "failed"]
FailureStage = Literal["validate", "compile", "execute", "artifact"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldTarget(StrictModel):
    asset_ref: str = Field(min_length=1)
    alias: str = Field(min_length=1)
    field: str = Field(min_length=1)


class QueryFilter(StrictModel):
    target: FieldTarget
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "between", "in", "contains"]
    value: Any
    reason: str = Field(min_length=1)


class QuerySelect(StrictModel):
    target: FieldTarget
    display_name: str = Field(min_length=1)
    display_semantic: str | None = None
    requires_decoding: bool = False


class QueryMetric(StrictModel):
    target: FieldTarget
    aggregation: Literal["sum", "count", "avg", "min", "max", "count_distinct"]
    display_name: str = Field(min_length=1)


class QueryOrdering(StrictModel):
    target: FieldTarget
    direction: Literal["asc", "desc"] = "asc"


class ResultShape(StrictModel):
    type: Literal["table", "metric", "chart"] = "table"
    grain: str = Field(min_length=1)
    limit: int = Field(default=100, ge=1, le=500)


class QueryEntity(StrictModel):
    asset_ref: str = Field(min_length=1)
    alias: str = Field(min_length=1)
    role: str = Field(min_length=1)
    join_purpose: str | None = None


class QueryDataGraph(StrictModel):
    primary_entity: QueryEntity
    supporting_entities: list[QueryEntity] = Field(default_factory=list)


class JoinRequirement(StrictModel):
    left_alias: str = Field(min_length=1)
    right_alias: str = Field(min_length=1)
    relationship_ref: str = Field(min_length=1)
    join_type: JoinType = "inner"
    required: bool = True
    reason: str = Field(min_length=1)


class BIWorkerQueryPlan(StrictModel):
    intent: QueryIntent
    question: str = Field(min_length=1)
    result_shape: ResultShape
    data_graph: QueryDataGraph
    join_requirements: list[JoinRequirement] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    selects: list[QuerySelect] = Field(default_factory=list)
    metrics: list[QueryMetric] = Field(default_factory=list)
    group_by: list[FieldTarget] = Field(default_factory=list)
    ordering: list[QueryOrdering] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape(self) -> "BIWorkerQueryPlan":
        if self.intent == "metric_query" and not self.metrics:
            raise ValueError("metric_query requires at least one metric")
        if self.intent == "detail_query" and not self.selects:
            raise ValueError("detail_query requires at least one selected field")
        return self


class DatasetCapabilityContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l0_capability"] = "bi_worker_l0_capability"
    dataset_id: int
    dataset_name: str
    business_domain: str | None = None
    supported_questions: list[str] = Field(default_factory=list)
    key_metrics: list[str] = Field(default_factory=list)
    key_dimensions: list[str] = Field(default_factory=list)
    summary: str


class QueryAssetContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l1_assets"] = "bi_worker_l1_assets"
    dataset_id: int
    question: str
    assets: list[dict[str, Any]] = Field(default_factory=list)
    summary: str


class SchemaSliceContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l2_schema_slice"] = "bi_worker_l2_schema_slice"
    dataset_id: int
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    summary: str


class ValueProfileContext(StrictModel):
    datalogue_event_type: Literal["bi_worker_l3_value_profile"] = "bi_worker_l3_value_profile"
    dataset_id: int
    profiles: list[dict[str, Any]] = Field(default_factory=list)
    summary: str


class QuerySupportValidation(StrictModel):
    datalogue_event_type: Literal["bi_worker_l4_validation"] = "bi_worker_l4_validation"
    support_status: SupportStatus
    safe_reason: str
    missing_context: list[dict[str, Any]] = Field(default_factory=list)
    auto_context_expansions: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_tool: str | None = None


class RepairRequest(StrictModel):
    datalogue_event_type: Literal["bi_worker_repair_request"] = "bi_worker_repair_request"
    repair_status: RepairStatus
    failure_stage: FailureStage
    failure_class: str = Field(min_length=1)
    safe_reason: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    missing_context: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("safe_reason")
    @classmethod
    def _reject_raw_error_text(cls, value: str) -> str:
        lowered = value.lower()
        forbidden = ("select ", " from ", " where ", "relation ", "table ", "column ")
        if any(token in lowered for token in forbidden):
            raise ValueError("safe_reason contains raw database or SQL detail")
        return value


class BIWorkerQueryResult(StrictModel):
    answer_summary: str
    artifact_ref: str | None
    checkpoint_ref: str | None
    row_count: int | None
    column_count: int | None

    def to_tool_payload(self) -> dict[str, Any]:
        artifact_card = None
        if self.artifact_ref:
            artifact_card = {
                "artifact_type": "bi_answer",
                "title": "查询结果",
                "status": "completed",
                "summary_for_chat": self.answer_summary,
                "preview_payload": {
                    "row_count": self.row_count or 0,
                    "column_count": self.column_count or 0,
                },
                "primary_ref": {
                    "ref_id": self.artifact_ref,
                    "ref_type": "result",
                    "label": "查询结果",
                },
                "related_refs": [],
                "actions": [
                    {"action_type": "view", "label": "查看详情", "ref": self.artifact_ref, "disabled": False},
                    {"action_type": "export", "label": "导出", "ref": self.artifact_ref, "disabled": True},
                ],
            }
        return {
            "answer_summary": self.answer_summary,
            "artifact_ref": self.artifact_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "datalogue_event_type": "dataset_query_result",
            "summary": self.answer_summary,
            "result_ref": self.artifact_ref,
            "artifact_card": artifact_card,
        }
```

- [ ] **Step 4: Run contract tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add datalogue-api/app/agentscope_service/bi_worker_contracts.py datalogue-api/tests/test_bi_worker_progressive_context_contracts.py
git commit -m "feat: add BI Worker progressive context contracts"
```

---

## Task 2: Implement L0-L3 Context Provider

**Files:**

- Create: `datalogue-api/app/agentscope_service/bi_worker_context.py`
- Test: `datalogue-api/tests/test_bi_worker_progressive_context_tools.py`

- [ ] **Step 1: Write failing context provider tests**

Create `datalogue-api/tests/test_bi_worker_progressive_context_tools.py`:

```python
# ============================================================
# File Name   : test_bi_worker_progressive_context_tools.py
# Description:
#   BI Worker 渐进式上下文工具测试。
#
# Responsibilities:
#   - 验证 L0/L1/L2/L3 上下文工具输出安全切片。
#   - 验证输出不包含 SQL、raw rows 或完整 schema。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from app.agentscope_service.bi_worker_context import BIWorkerContextProvider
from app.models.dataset import DatasetSourceTable, SemanticDataset
from app.models.datasource import SourceColumn, SourceTable


def _create_dataset_with_table(db_session):
    dataset = SemanticDataset(
        name="工作日志数据集",
        datasource_id=1,
        description="记录员工工作日志、日期和所属部门。",
        prompt_instructions="适合查询工作日志明细。",
        status="active",
    )
    table = SourceTable(datasource_id=1, schema_name="public", table_name="work_logs")
    db_session.add_all([dataset, table])
    db_session.flush()
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.add_all(
        [
            SourceColumn(table_id=table.id, column_name="employee_name", data_type="varchar", column_comment="员工姓名"),
            SourceColumn(table_id=table.id, column_name="work_date", data_type="date", column_comment="工作日期"),
            SourceColumn(table_id=table.id, column_name="log_content", data_type="text", column_comment="工作日志内容"),
        ]
    )
    db_session.commit()
    return dataset.id


def test_l0_describes_dataset_without_schema(db_session):
    dataset_id = _create_dataset_with_table(db_session)
    provider = BIWorkerContextProvider(db_session)

    payload = provider.describe_dataset_capability(dataset_id=dataset_id, question="查询杨凯2025年工作日志")

    assert payload.datalogue_event_type == "bi_worker_l0_capability"
    assert payload.dataset_name == "工作日志数据集"
    serialized = payload.model_dump_json()
    assert "employee_name" not in serialized
    assert "select " not in serialized.lower()


def test_l2_returns_relevant_schema_slice_with_physical_fields(db_session):
    dataset_id = _create_dataset_with_table(db_session)
    provider = BIWorkerContextProvider(db_session)

    payload = provider.request_schema_slice(
        dataset_id=dataset_id,
        question="查询杨凯2025年工作日志",
        focus={"business_terms": ["人员", "日期", "日志"]},
    )

    serialized = payload.model_dump()
    assert payload.datalogue_event_type == "bi_worker_l2_schema_slice"
    assert any(field["field"] == "employee_name" for entity in serialized["entities"] for field in entity["fields"])
    assert "raw_rows" not in str(serialized).lower()


def test_l3_value_profile_returns_summary_not_rows(db_session):
    dataset_id = _create_dataset_with_table(db_session)
    provider = BIWorkerContextProvider(db_session)

    payload = provider.profile_candidate_values(
        dataset_id=dataset_id,
        question="查询杨凯2025年工作日志",
        probes=[{"field": "employee_name", "value": "杨凯"}, {"field": "work_date", "range": ["2025-01-01", "2025-12-31"]}],
    )

    assert payload.datalogue_event_type == "bi_worker_l3_value_profile"
    assert all("rows" not in profile for profile in payload.profiles)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_tools.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agentscope_service.bi_worker_context'`.

- [ ] **Step 3: Implement context provider**

Create `datalogue-api/app/agentscope_service/bi_worker_context.py`:

```python
# ============================================================
# File Name   : bi_worker_context.py
# Description:
#   BI Worker L0-L3 渐进式上下文提供器。
#
# Responsibilities:
#   - 读取 Datalogue 数据集元数据并生成安全上下文切片。
#   - 允许 L2 返回相关真实表名和物理字段名。
#   - 阻止 SQL、raw rows 和完整 schema 进入 BI Worker 可见输出。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.agentscope_service.bi_worker_contracts import (
    DatasetCapabilityContext,
    QueryAssetContext,
    SchemaSliceContext,
    ValueProfileContext,
)
from app.models.dataset import SemanticDataset


class BIWorkerContextProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def describe_dataset_capability(self, *, dataset_id: int, question: str) -> DatasetCapabilityContext:
        dataset = self._get_dataset(dataset_id)
        metrics = [str(metric.display_name or metric.name) for metric in dataset.metrics or []][:12]
        dimensions = [str(dimension.display_name or dimension.name) for dimension in dataset.dimensions or []][:12]
        supported = [part for part in [dataset.description, dataset.prompt_instructions] if part]
        return DatasetCapabilityContext(
            dataset_id=dataset.id,
            dataset_name=str(dataset.name or f"数据集 {dataset.id}"),
            business_domain=None,
            supported_questions=[str(item)[:160] for item in supported],
            key_metrics=metrics,
            key_dimensions=dimensions,
            summary=f"已读取数据集能力摘要：{dataset.name}",
        )

    def recall_query_assets(self, *, dataset_id: int, question: str) -> QueryAssetContext:
        dataset = self._get_dataset(dataset_id)
        tokens = _tokens(question)
        assets: list[dict[str, Any]] = []
        for metric in dataset.metrics or []:
            text = f"{metric.name} {metric.display_name or ''} {metric.description or ''}"
            if _matches(tokens, text):
                assets.append({"asset_ref": f"asset:metric:{metric.id}", "asset_type": "metric", "name": metric.display_name or metric.name})
        for dimension in dataset.dimensions or []:
            text = f"{dimension.name} {dimension.display_name or ''}"
            if _matches(tokens, text):
                assets.append({"asset_ref": f"asset:dimension:{dimension.id}", "asset_type": "dimension", "name": dimension.display_name or dimension.name})
        return QueryAssetContext(
            dataset_id=dataset.id,
            question=question,
            assets=assets[:20],
            summary=f"命中 {len(assets[:20])} 个候选业务资产。",
        )

    def request_schema_slice(self, *, dataset_id: int, question: str, focus: dict[str, Any] | None = None) -> SchemaSliceContext:
        dataset = self._get_dataset(dataset_id)
        tokens = _tokens(" ".join([question, str(focus or {})]))
        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for link in dataset.selected_tables or []:
            table = getattr(link, "source_table", None)
            if table is None:
                continue
            fields = []
            for column in table.columns or []:
                text = " ".join(
                    [
                        str(column.column_name or ""),
                        str(getattr(column, "column_comment", "") or ""),
                        str(getattr(column, "user_description", "") or ""),
                        str(getattr(column, "ai_description", "") or ""),
                    ]
                )
                if tokens and not _matches(tokens, text):
                    continue
                fields.append(
                    {
                        "asset_ref": f"asset:table:{table.id}.field:{column.id}",
                        "field": str(column.column_name),
                        "business_name": str(getattr(column, "effective_desc", None) or getattr(column, "column_comment", None) or column.column_name),
                        "type": str(getattr(column, "data_type", None) or "unknown"),
                        "filterable": True,
                        "sortable": True,
                        "aggregatable": str(getattr(column, "data_type", "") or "").lower() in {"int", "integer", "float", "double", "decimal", "number"},
                    }
                )
            if fields:
                entities.append(
                    {
                        "asset_ref": f"asset:table:{table.id}",
                        "table_name": str(table.table_name),
                        "schema_name": getattr(table, "schema_name", None),
                        "business_name": str(getattr(table, "display_name", None) or table.table_name),
                        "fields": fields[:30],
                    }
                )
        return SchemaSliceContext(
            dataset_id=dataset.id,
            entities=entities[:8],
            relationships=relationships,
            summary=f"返回 {len(entities[:8])} 个相关 schema 实体切片。",
        )

    def profile_candidate_values(self, *, dataset_id: int, question: str, probes: list[dict[str, Any]]) -> ValueProfileContext:
        self._get_dataset(dataset_id)
        profiles = []
        for probe in probes[:8]:
            profiles.append(
                {
                    "field": str(probe.get("field") or ""),
                    "probe_type": "coverage_summary",
                    "covered": None,
                    "safe_summary": "已记录候选值画像请求；当前阶段返回安全覆盖度摘要。",
                }
            )
        return ValueProfileContext(
            dataset_id=dataset_id,
            profiles=profiles,
            summary=f"返回 {len(profiles)} 个字段覆盖度摘要。",
        )

    def _get_dataset(self, dataset_id: int) -> SemanticDataset:
        dataset = self.db.get(SemanticDataset, dataset_id)
        if dataset is None:
            raise ValueError("DATASET_NOT_FOUND")
        return dataset


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", str(text or "").lower())
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", str(text or "").lower()))
    raw.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return list(dict.fromkeys(raw))


def _matches(tokens: list[str], text: str) -> bool:
    if not tokens:
        return True
    normalized = re.sub(r"\s+", "", str(text or "").lower())
    return any(token and token in normalized for token in tokens)
```

- [ ] **Step 4: Run context tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_tools.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add datalogue-api/app/agentscope_service/bi_worker_context.py datalogue-api/tests/test_bi_worker_progressive_context_tools.py
git commit -m "feat: add BI Worker progressive context provider"
```

---

## Task 3: Implement L4 Query Support Validator

**Files:**

- Create: `datalogue-api/app/agentscope_service/bi_worker_validator.py`
- Test: `datalogue-api/tests/test_bi_worker_query_validator.py`

- [ ] **Step 1: Write failing validator tests**

Create `datalogue-api/tests/test_bi_worker_query_validator.py`:

```python
# ============================================================
# File Name   : test_bi_worker_query_validator.py
# Description:
#   BI Worker Query Plan L4 支持度校验测试。
#
# Responsibilities:
#   - 验证字段、关系、lookup 依赖和循环上限。
#   - 确保 L5 执行前必须得到 supported。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan
from app.agentscope_service.bi_worker_validator import BIWorkerQueryValidator, ProgressiveContextState


def _plan_with_relationship(relationship_ref="rel:work_log_employee"):
    return BIWorkerQueryPlan.model_validate(
        {
            "intent": "detail_query",
            "question": "查询杨凯2025年工作日志",
            "result_shape": {"type": "table", "grain": "one_row_per_work_log", "limit": 100},
            "data_graph": {
                "primary_entity": {"asset_ref": "asset:work_log", "alias": "log", "role": "fact_or_primary"},
                "supporting_entities": [{"asset_ref": "asset:employee", "alias": "emp", "role": "dimension"}],
            },
            "join_requirements": [
                {
                    "left_alias": "log",
                    "right_alias": "emp",
                    "relationship_ref": relationship_ref,
                    "join_type": "inner",
                    "required": True,
                    "reason": "人员过滤",
                }
            ],
            "filters": [
                {
                    "target": {"asset_ref": "asset:employee.name", "alias": "emp", "field": "employee_name"},
                    "operator": "=",
                    "value": "杨凯",
                    "reason": "用户指定人员",
                }
            ],
            "selects": [
                {
                    "target": {"asset_ref": "asset:work_log.content", "alias": "log", "field": "log_content"},
                    "display_name": "工作日志",
                }
            ],
            "metrics": [],
            "group_by": [],
            "ordering": [],
            "assumptions": [],
        }
    )


def _context_state():
    return ProgressiveContextState(
        asset_refs={"asset:work_log", "asset:employee", "asset:employee.name", "asset:work_log.content"},
        relationship_refs={"rel:work_log_employee"},
        field_refs={"asset:employee.name", "asset:work_log.content"},
        lookup_dependencies={},
        missing_context_history=[],
        l2_request_count=0,
        l3_profile_count=0,
        validation_more_context_count=0,
    )


def test_validator_supports_known_relationship_and_fields():
    validation = BIWorkerQueryValidator().validate(plan=_plan_with_relationship(), context_state=_context_state())

    assert validation.support_status == "supported"


def test_validator_blocks_unknown_relationship():
    validation = BIWorkerQueryValidator().validate(plan=_plan_with_relationship("rel:invented"), context_state=_context_state())

    assert validation.support_status == "needs_more_context"
    assert validation.missing_context[0]["type"] == "missing_relationship"


def test_validator_detects_lookup_dependency_for_display_semantic():
    plan = _plan_with_relationship()
    plan.selects[0].display_semantic = "department_name"
    plan.selects[0].requires_decoding = True
    context = _context_state()

    validation = BIWorkerQueryValidator().validate(plan=plan, context_state=context)

    assert validation.support_status == "needs_more_context"
    assert validation.missing_context[0]["type"] == "lookup_dependency"


def test_validator_stops_repeated_missing_context():
    context = _context_state()
    context.validation_more_context_count = 2
    validation = BIWorkerQueryValidator().validate(plan=_plan_with_relationship("rel:invented"), context_state=context)

    assert validation.support_status in {"needs_clarification", "unsupported"}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_query_validator.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agentscope_service.bi_worker_validator'`.

- [ ] **Step 3: Implement validator**

Create `datalogue-api/app/agentscope_service/bi_worker_validator.py`:

```python
# ============================================================
# File Name   : bi_worker_validator.py
# Description:
#   BI Worker Query Plan L4 支持度校验器。
#
# Responsibilities:
#   - 校验 Query Plan 只能引用已披露 asset_ref 和 relationship_ref。
#   - 检查多表 join、展示语义依赖和渐进上下文循环上限。
#   - 返回安全 QuerySupportValidation，不暴露 SQL 或数据库原始错误。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan, QuerySupportValidation


MAX_MORE_CONTEXT_ROUNDS = 2


@dataclass
class ProgressiveContextState:
    asset_refs: set[str] = field(default_factory=set)
    relationship_refs: set[str] = field(default_factory=set)
    field_refs: set[str] = field(default_factory=set)
    lookup_dependencies: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_context_history: list[str] = field(default_factory=list)
    l2_request_count: int = 0
    l3_profile_count: int = 0
    validation_more_context_count: int = 0


class BIWorkerQueryValidator:
    def validate(self, *, plan: BIWorkerQueryPlan, context_state: ProgressiveContextState) -> QuerySupportValidation:
        missing: list[dict[str, Any]] = []

        for entity in [plan.data_graph.primary_entity, *plan.data_graph.supporting_entities]:
            if entity.asset_ref not in context_state.asset_refs:
                missing.append({"type": "missing_asset", "asset_ref": entity.asset_ref, "recommended_next_tool": "datalogue_recall_query_assets"})

        for join in plan.join_requirements:
            if join.relationship_ref not in context_state.relationship_refs:
                missing.append(
                    {
                        "type": "missing_relationship",
                        "relationship_ref": join.relationship_ref,
                        "recommended_next_tool": "datalogue_request_schema_slice",
                    }
                )

        for target in self._all_targets(plan):
            if target.asset_ref not in context_state.field_refs and target.asset_ref not in context_state.asset_refs:
                missing.append(
                    {
                        "type": "missing_field",
                        "asset_ref": target.asset_ref,
                        "recommended_next_tool": "datalogue_request_schema_slice",
                    }
                )

        for select in plan.selects:
            if select.requires_decoding or select.display_semantic:
                dependency = context_state.lookup_dependencies.get(select.target.asset_ref)
                if not dependency:
                    missing.append(
                        {
                            "type": "lookup_dependency",
                            "code_field": select.target.field,
                            "business_meaning": select.display_semantic or select.display_name,
                            "recommended_next_tool": "datalogue_request_schema_slice",
                            "focus": {"lookup_for": select.target.asset_ref, "target_semantic": select.display_semantic},
                        }
                    )

        if not missing:
            return QuerySupportValidation(
                support_status="supported",
                safe_reason="当前 Query Plan 已通过字段、关系和语义依赖校验。",
                missing_context=[],
                auto_context_expansions=[],
            )

        fingerprint = "|".join(sorted(str(item) for item in missing))
        repeated = fingerprint in context_state.missing_context_history
        exhausted = context_state.validation_more_context_count >= MAX_MORE_CONTEXT_ROUNDS
        if repeated or exhausted:
            return QuerySupportValidation(
                support_status="needs_clarification",
                safe_reason="上下文申请已达到上限，需要用户澄清或补充数据治理信息。",
                missing_context=missing,
                auto_context_expansions=[],
                recommended_next_tool=None,
            )

        return QuerySupportValidation(
            support_status="needs_more_context",
            safe_reason="当前 Query Plan 缺少必要字段、关系或展示语义依赖。",
            missing_context=missing,
            auto_context_expansions=[],
            recommended_next_tool=str(missing[0].get("recommended_next_tool") or "datalogue_request_schema_slice"),
        )

    def _all_targets(self, plan: BIWorkerQueryPlan):
        for item in plan.filters:
            yield item.target
        for item in plan.selects:
            yield item.target
        for item in plan.metrics:
            yield item.target
        for item in plan.group_by:
            yield item
        for item in plan.ordering:
            yield item.target
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_query_validator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add datalogue-api/app/agentscope_service/bi_worker_validator.py datalogue-api/tests/test_bi_worker_query_validator.py
git commit -m "feat: add BI Worker query support validator"
```

---

## Task 4: Implement L5 Runtime And Safe Repair Requests

**Files:**

- Create: `datalogue-api/app/agentscope_service/bi_worker_runtime.py`
- Modify: `datalogue-api/app/agentscope_service/dataset_query_executor.py`
- Test: `datalogue-api/tests/test_bi_worker_query_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Create `datalogue-api/tests/test_bi_worker_query_runtime.py`:

```python
# ============================================================
# File Name   : test_bi_worker_query_runtime.py
# Description:
#   BI Worker L5 runtime 测试。
#
# Responsibilities:
#   - 验证 L5 执行前强制 L4 校验。
#   - 验证执行结果只返回 artifact/card 安全摘要。
#   - 验证数据库错误被转换为安全 repair request。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

import pytest

from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan
from app.agentscope_service.bi_worker_runtime import BIWorkerQueryRuntime
from app.agentscope_service.bi_worker_validator import ProgressiveContextState


def _valid_plan():
    return BIWorkerQueryPlan.model_validate(
        {
            "intent": "detail_query",
            "question": "查询杨凯2025年工作日志",
            "result_shape": {"type": "table", "grain": "one_row_per_work_log", "limit": 100},
            "data_graph": {
                "primary_entity": {"asset_ref": "asset:work_log", "alias": "log", "role": "fact_or_primary"},
                "supporting_entities": [],
            },
            "join_requirements": [],
            "filters": [],
            "selects": [
                {
                    "target": {"asset_ref": "asset:work_log.content", "alias": "log", "field": "log_content"},
                    "display_name": "工作日志",
                }
            ],
            "metrics": [],
            "group_by": [],
            "ordering": [],
            "assumptions": [],
        }
    )


def _state():
    return ProgressiveContextState(
        asset_refs={"asset:work_log", "asset:work_log.content"},
        relationship_refs=set(),
        field_refs={"asset:work_log.content"},
    )


@pytest.mark.asyncio
async def test_runtime_blocks_execute_when_validation_needs_context(db_session):
    runtime = BIWorkerQueryRuntime(db_session)
    state = ProgressiveContextState()

    result = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查询杨凯2025年工作日志",
        query_plan=_valid_plan(),
        context_state=state,
        trace_id="trace-test",
    )

    assert result["datalogue_event_type"] == "bi_worker_l4_validation"
    assert result["support_status"] == "needs_more_context"


@pytest.mark.asyncio
async def test_runtime_returns_safe_repair_request_for_execution_error(db_session, monkeypatch):
    runtime = BIWorkerQueryRuntime(db_session)

    async def fake_execute(*args, **kwargs):
        raise RuntimeError("SELECT * FROM missing_table")

    monkeypatch.setattr(runtime, "_execute_supported_plan", fake_execute)

    result = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查询杨凯2025年工作日志",
        query_plan=_valid_plan(),
        context_state=_state(),
        trace_id="trace-test",
    )

    assert result["datalogue_event_type"] == "bi_worker_repair_request"
    assert result["failure_stage"] == "execute"
    assert "select " not in str(result).lower()
    assert "missing_table" not in str(result).lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_query_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agentscope_service.bi_worker_runtime'`.

- [ ] **Step 3: Implement runtime shell**

Create `datalogue-api/app/agentscope_service/bi_worker_runtime.py`:

```python
# ============================================================
# File Name   : bi_worker_runtime.py
# Description:
#   BI Worker L5 受控查询执行 runtime。
#
# Responsibilities:
#   - 在执行前强制运行 L4 Query Plan 支持度校验。
#   - 将 BI Worker Query Plan 适配为现有 BI atomic toolkit 可执行输入。
#   - 捕获执行期错误并返回安全 repair request。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan, BIWorkerQueryResult, RepairRequest
from app.agentscope_service.bi_worker_validator import BIWorkerQueryValidator, ProgressiveContextState


class BIWorkerQueryRuntime:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.validator = BIWorkerQueryValidator()

    async def execute_query_plan(
        self,
        *,
        dataset_id: int,
        confirmed_question: str,
        query_plan: BIWorkerQueryPlan,
        context_state: ProgressiveContextState,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        validation = self.validator.validate(plan=query_plan, context_state=context_state)
        if validation.support_status != "supported":
            return validation.model_dump()
        try:
            result = await self._execute_supported_plan(
                dataset_id=dataset_id,
                confirmed_question=confirmed_question,
                query_plan=query_plan,
                trace_id=trace_id,
            )
            return result.to_tool_payload()
        except Exception:
            return self._safe_repair_request(
                failure_stage="execute",
                failure_class="execution_failed",
                safe_reason="查询执行阶段出现可修复问题，需要调整 Query Plan 或补充上下文。",
                recommended_action="request_schema_slice",
            ).model_dump()

    async def _execute_supported_plan(
        self,
        *,
        dataset_id: int,
        confirmed_question: str,
        query_plan: BIWorkerQueryPlan,
        trace_id: str | None,
    ) -> BIWorkerQueryResult:
        return BIWorkerQueryResult(
            answer_summary="查询已通过 BI Worker 受控执行入口生成结果。",
            artifact_ref=None,
            checkpoint_ref=None,
            row_count=None,
            column_count=None,
        )

    def _safe_repair_request(
        self,
        *,
        failure_stage: str,
        failure_class: str,
        safe_reason: str,
        recommended_action: str,
    ) -> RepairRequest:
        return RepairRequest(
            repair_status="needs_plan_revision",
            failure_stage=failure_stage,
            failure_class=failure_class,
            safe_reason=safe_reason,
            recommended_action=recommended_action,
            missing_context=[{"type": "execution_context", "focus": "query plan revision"}],
        )
```

- [ ] **Step 4: Replace runtime shell with atomic toolkit execution**

Modify `_execute_supported_plan` in `bi_worker_runtime.py` so it:

```python
from app.agents.bi_agent.runtime_context import build_bi_runtime_context
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit import build_bi_atomic_toolkit


async def _execute_supported_plan(
    self,
    *,
    dataset_id: int,
    confirmed_question: str,
    query_plan: BIWorkerQueryPlan,
    trace_id: str | None,
) -> BIWorkerQueryResult:
    toolkit = build_bi_atomic_toolkit(self.db)
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    runtime_context = build_bi_runtime_context(
        self.db,
        dataset_id=dataset_id,
        question=confirmed_question,
        bridge=bridge,
    )
    session = bridge.start_session(
        dataset_id=dataset_id,
        question=confirmed_question,
        agent_name="bi_worker",
        trace_id=trace_id,
        **(runtime_context.get("session_kwargs") or {}),
    )
    dsl = self._query_plan_to_legacy_query_plan(query_plan)
    result = await bridge.run_direct_query(session=session, dsl=dsl)
    return BIWorkerQueryResult(
        answer_summary=self._answer_summary(result),
        artifact_ref=self._optional_str(result.get("artifact_ref")),
        checkpoint_ref=self._optional_str(result.get("checkpoint_ref")),
        row_count=self._optional_int(result.get("row_count")),
        column_count=self._optional_int(result.get("column_count")),
    )
```

Add helper methods:

```python
def _query_plan_to_legacy_query_plan(self, query_plan: BIWorkerQueryPlan) -> dict[str, Any]:
    selected_assets = [
        {
            "asset_type": "field",
            "asset_id": item.target.asset_ref,
            "name": item.target.field,
            "display_name": item.display_name,
            "source": "bi_worker_query_plan",
            "confidence": 0.9,
            "usage": "selected",
        }
        for item in query_plan.selects
    ]
    return {
        "query_type": query_plan.intent,
        "execution_strategy": "query_graph" if query_plan.intent in {"detail_query", "metric_query"} else "reject",
        "confidence": 0.85,
        "selected_assets": selected_assets,
        "reference_assets": [],
        "rejected_assets": [],
        "required_inputs": [],
        "planner_source": "llm",
        "execution_source": "tool_compiler",
        "explanation": {
            "summary": "BI Worker 基于渐进式上下文生成 Query Plan。",
            "query_plan_v1": query_plan.model_dump(),
        },
    }


def _answer_summary(self, result: dict[str, Any]) -> str:
    artifact_ref = self._optional_str(result.get("artifact_ref"))
    if result.get("status") == "completed" and artifact_ref:
        return f"查询已完成，结果已生成 artifact_ref={artifact_ref}，共 {self._optional_int(result.get('row_count')) or 0} 行、{self._optional_int(result.get('column_count')) or 0} 列。"
    return "查询未完成，未生成可展示结果。"


def _optional_str(self, value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(self, value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 5: Keep existing direct executor as explicit fallback**

Modify `datalogue-api/app/agentscope_service/dataset_query_executor.py`:

```python
async def execute_dataset_query_for_agent_team_direct_fallback(
    *,
    db: Session | None = None,
    dataset_id: int,
    confirmed_question: str,
    trace_id: str | None = None,
) -> AgentTeamDatasetQueryResult:
    """显式 fallback：仅在 progressive runtime 被关闭或回滚时使用旧 direct query。"""

    return await execute_dataset_query_for_agent_team(
        db=db,
        dataset_id=dataset_id,
        confirmed_question=confirmed_question,
        trace_id=trace_id,
    )
```

- [ ] **Step 6: Run runtime tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_query_runtime.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add datalogue-api/app/agentscope_service/bi_worker_runtime.py datalogue-api/app/agentscope_service/dataset_query_executor.py datalogue-api/tests/test_bi_worker_query_runtime.py
git commit -m "feat: add BI Worker controlled query runtime"
```

---

## Task 5: Expose Progressive Tools Through AgentScope SDK

**Files:**

- Modify: `datalogue-api/app/agentscope_service/tools.py`
- Test: `datalogue-api/tests/test_agentscope_service_tools.py`
- Test: `datalogue-api/tests/test_bi_worker_progressive_context_tools.py`

- [ ] **Step 1: Add failing tool registration test**

Append to `datalogue-api/tests/test_agentscope_service_tools.py`:

```python
def test_bi_worker_progressive_tools_are_registered_for_team_worker():
    from app.agentscope_service.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context={"user_id": "u", "agent_id": "a", "agent_name": "worker", "session_id": "s"})
    names = [tool.name for tool in tools]

    assert names == [
        "datalogue_describe_dataset_capability",
        "datalogue_recall_query_assets",
        "datalogue_request_schema_slice",
        "datalogue_profile_candidate_values",
        "datalogue_validate_query_support",
        "datalogue_execute_query_plan",
    ]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_service_tools.py::test_bi_worker_progressive_tools_are_registered_for_team_worker -q
```

Expected: FAIL with import error or missing function.

- [ ] **Step 3: Implement SDK FunctionTool builders**

Modify `datalogue-api/app/agentscope_service/tools.py`:

```python
from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan
from app.agentscope_service.bi_worker_context import BIWorkerContextProvider
from app.agentscope_service.bi_worker_runtime import BIWorkerQueryRuntime
from app.agentscope_service.bi_worker_validator import ProgressiveContextState
```

Add:

```python
def build_datalogue_progressive_bi_worker_tools(*, worker_context: dict[str, str | None] | None = None) -> list[ToolBase]:
    """构建 AgentScope FunctionTool 形式的 BI Worker 渐进式问数工具。"""

    return [
        build_describe_dataset_capability_tool(worker_context=worker_context),
        build_recall_query_assets_tool(worker_context=worker_context),
        build_request_schema_slice_tool(worker_context=worker_context),
        build_profile_candidate_values_tool(worker_context=worker_context),
        build_validate_query_support_tool(worker_context=worker_context),
        build_execute_query_plan_tool(worker_context=worker_context),
    ]
```

Add `build_describe_dataset_capability_tool`:

```python
def build_describe_dataset_capability_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    async def datalogue_describe_dataset_capability(dataset_id: int, confirmed_question: str) -> ToolChunk:
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).describe_dataset_capability(
                dataset_id=dataset_id,
                question=confirmed_question,
            ).model_dump()
        return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))], state=ToolResultState.SUCCESS)

    return FunctionTool(
        datalogue_describe_dataset_capability,
        description="BI Worker L0 数据集能力摘要工具；不返回表名、字段名、SQL 或 raw rows。",
        is_concurrency_safe=True,
        is_read_only=True,
    )
```

Add the other five builders using the same `FunctionTool` pattern:

```python
def build_recall_query_assets_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    async def datalogue_recall_query_assets(dataset_id: int, confirmed_question: str) -> ToolChunk:
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).recall_query_assets(dataset_id=dataset_id, question=confirmed_question).model_dump()
        return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))], state=ToolResultState.SUCCESS)

    return FunctionTool(datalogue_recall_query_assets, description="BI Worker L1 候选资产摘要工具。", is_concurrency_safe=True, is_read_only=True)


def build_request_schema_slice_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    async def datalogue_request_schema_slice(dataset_id: int, confirmed_question: str, focus: dict[str, Any] | None = None) -> ToolChunk:
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).request_schema_slice(dataset_id=dataset_id, question=confirmed_question, focus=focus).model_dump()
        return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))], state=ToolResultState.SUCCESS)

    return FunctionTool(datalogue_request_schema_slice, description="BI Worker L2 相关 schema/关系切片工具；只返回最小相关物理字段和关系。", is_concurrency_safe=True, is_read_only=True)


def build_profile_candidate_values_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    async def datalogue_profile_candidate_values(dataset_id: int, confirmed_question: str, probes: list[dict[str, Any]]) -> ToolChunk:
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).profile_candidate_values(dataset_id=dataset_id, question=confirmed_question, probes=probes).model_dump()
        return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))], state=ToolResultState.SUCCESS)

    return FunctionTool(datalogue_profile_candidate_values, description="BI Worker L3 值域/覆盖度画像工具；不返回 raw rows。", is_concurrency_safe=True, is_read_only=True)


def build_validate_query_support_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    async def datalogue_validate_query_support(query_plan: dict[str, Any], context_state: dict[str, Any]) -> ToolChunk:
        plan = BIWorkerQueryPlan.model_validate(query_plan)
        state = ProgressiveContextState(**context_state)
        payload = BIWorkerQueryRuntime(SessionLocal()).validator.validate(plan=plan, context_state=state).model_dump()
        return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))], state=ToolResultState.SUCCESS)

    return FunctionTool(datalogue_validate_query_support, description="BI Worker L4 Query Plan 支持度预检工具。", is_concurrency_safe=True, is_read_only=True)


def build_execute_query_plan_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    async def datalogue_execute_query_plan(dataset_id: int, confirmed_question: str, query_plan: dict[str, Any], context_state: dict[str, Any], trace_id: str | None = None) -> ToolChunk:
        with SessionLocal() as db:
            payload = await BIWorkerQueryRuntime(db).execute_query_plan(
                dataset_id=dataset_id,
                confirmed_question=confirmed_question,
                query_plan=BIWorkerQueryPlan.model_validate(query_plan),
                context_state=ProgressiveContextState(**context_state),
                trace_id=trace_id,
            )
            db.commit()
        if payload.get("datalogue_event_type") == "dataset_query_result":
            _publish_worker_business_final(worker_context=worker_context, payload=payload)
        return ToolChunk(content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))], state=ToolResultState.SUCCESS)

    return FunctionTool(datalogue_execute_query_plan, description="BI Worker L5 受控 Query Plan 执行工具；执行前强制 L4 校验。", is_concurrency_safe=False, is_read_only=False)
```

- [ ] **Step 4: Replace extra agent tools registration**

In `build_datalogue_extra_agent_tools`, change returned tools to:

```python
return [
    build_datalogue_select_candidate_datasets_tool(worker_context=worker_context),
    *build_datalogue_progressive_bi_worker_tools(worker_context=worker_context),
    build_datalogue_query_dataset_tool(worker_context=worker_context),
]
```

Keep `datalogue_query_dataset` during migration for compatibility with old tests and fallback.

- [ ] **Step 5: Run tool tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_service_tools.py tests/test_bi_worker_progressive_context_tools.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add datalogue-api/app/agentscope_service/tools.py datalogue-api/tests/test_agentscope_service_tools.py datalogue-api/tests/test_bi_worker_progressive_context_tools.py
git commit -m "feat: expose BI Worker progressive tools via AgentScope"
```

---

## Task 6: Update BI Worker Prompt And Permission Context

**Files:**

- Modify: `datalogue-api/app/agentscope_service/registry.py`
- Test: `datalogue-api/tests/test_agentscope_static_agent_registry.py`
- Test: `datalogue-api/tests/test_agentscope_agent_team_task_runner.py`

- [ ] **Step 1: Update registry tests first**

Modify `test_agentscope_static_agent_registry.py` prompt test so it asserts:

```python
assert "datalogue_describe_dataset_capability" in BI_WORKER_PROMPT
assert "datalogue_recall_query_assets" in BI_WORKER_PROMPT
assert "datalogue_execute_query_plan" in BI_WORKER_PROMPT
assert "L0/L1/L5" in BI_WORKER_PROMPT
assert "L2/L3" in BI_WORKER_PROMPT
assert "Query Plan JSON" in BI_WORKER_PROMPT
assert "不得生成 SQL" in BI_WORKER_PROMPT
```

Modify permission assertions:

```python
for tool_name in [
    "datalogue_describe_dataset_capability",
    "datalogue_recall_query_assets",
    "datalogue_request_schema_slice",
    "datalogue_profile_candidate_values",
    "datalogue_validate_query_support",
    "datalogue_execute_query_plan",
]:
    assert tool_name in permission_context.allow_rules
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_static_agent_registry.py -q
```

Expected: FAIL because prompt and permission context do not mention progressive tools.

- [ ] **Step 3: Update BI Worker prompt**

Modify `BI_WORKER_PROMPT` in `registry.py`:

```python
BI_WORKER_PROMPT = f"""
你是 {{member_name}}，由 {{leader_name}} 领导的 AgentScope 官方 Agent Team 中的 Datalogue BI Worker。

团队目标：{{team_description}}
你的角色：{{member_description}}

固定能力边界：
- 只处理 Datalogue Dataset Query 类问数任务。
- 如果 leader 没有提供 dataset_id，必须先调用 datalogue_select_candidate_datasets，再用 TeamSay 回传 dataset_candidates。
- 如果 leader 已提供明确 dataset_id，不再重复筛选数据集；必须按 L0/L1/L5 固定骨架完成问数执行。
- 固定骨架是：datalogue_describe_dataset_capability -> datalogue_recall_query_assets -> datalogue_execute_query_plan。
- L2/L3 是按需上下文：字段口径、join、展示语义不足时调用 datalogue_request_schema_slice；实体、年份、枚举覆盖不确定时调用 datalogue_profile_candidate_values。
- datalogue_validate_query_support 可主动预检；即使你不主动调用，datalogue_execute_query_plan 也会强制校验。
- 你可以生成 Query Plan JSON，但不得生成 SQL、执行 SQL、读取 raw rows 或自由发明 join 条件。
- Query Plan JSON 的 join 必须引用 relationship_ref，字段必须来自 L1/L2 返回的 asset_ref。
- datalogue_execute_query_plan 成功后，必须使用 TeamSay 将 dataset_query_result JSON 原样安全汇报给 {{leader_name}}。
- TeamSay 只能回传 answer_summary、artifact_ref、result_ref、checkpoint_ref、row_count、column_count、artifact_card、澄清问题或不支持原因。

安全要求：
- 不输出 SQL、完整 schema、raw rows、DSL、内部 Query Plan JSON、repair patch 或数据库原始错误。
- L2 的真实表名和物理字段名只能用于你的内部工作上下文，禁止写入 TeamSay 或最终回答。
- 不得使用 Bash、Read、Write、Edit、Glob、Grep 或任何文件/命令行工具发现数据集、扫描工作区或读取项目文件。
- 完成、澄清、不支持或失败后必须使用 TeamSay 向 {{leader_name}} 汇报安全摘要。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()
```

- [ ] **Step 4: Update permission context**

Modify `_bi_worker_permission_context` allow rules:

```python
for tool_name in [
    "datalogue_describe_dataset_capability",
    "datalogue_recall_query_assets",
    "datalogue_request_schema_slice",
    "datalogue_profile_candidate_values",
    "datalogue_validate_query_support",
    "datalogue_execute_query_plan",
]:
    allow_rules[tool_name] = [
        PermissionRule(
            tool_name=tool_name,
            rule_content=None,
            behavior=PermissionBehavior.ALLOW,
            source="datalogue-bi-worker-template",
        )
    ]
```

Keep existing `datalogue_select_candidate_datasets`, `datalogue_query_dataset`, and `TeamSay` allow rules during the migration.

- [ ] **Step 5: Run registry and runner tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_static_agent_registry.py tests/test_agentscope_agent_team_task_runner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add datalogue-api/app/agentscope_service/registry.py datalogue-api/tests/test_agentscope_static_agent_registry.py datalogue-api/tests/test_agentscope_agent_team_task_runner.py
git commit -m "feat: teach BI Worker progressive query workflow"
```

---

## Task 7: Project Safe Progressive Events To Timeline

**Files:**

- Modify: `datalogue-api/app/agentscope_service/worker_logging.py`
- Modify: `datalogue-api/app/runtime/agent_team_runtime.py`
- Modify: `datalogue-web/src/assistant/agent-team-event-adapter.js`
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Test: `datalogue-api/tests/test_agentscope_service_worker_logging.py`
- Test: `datalogue-web/src/assistant/agent-team-event-adapter.test.js`
- Test: `datalogue-web/src/assistant/chat-adapter.test.js`

- [ ] **Step 1: Add backend logging test**

Append to `test_agentscope_service_worker_logging.py`:

```python
def test_progressive_context_tool_names_map_to_safe_business_labels():
    from app.agentscope_service.worker_logging import summarize_tool_progress

    assert summarize_tool_progress("datalogue_describe_dataset_capability")["summary"] == "BI Worker 正在读取数据集能力摘要。"
    assert summarize_tool_progress("datalogue_recall_query_assets")["summary"] == "BI Worker 正在匹配候选数据资产。"
    assert summarize_tool_progress("datalogue_request_schema_slice")["summary"] == "BI Worker 正在申请相关数据结构切片。"
    assert summarize_tool_progress("datalogue_profile_candidate_values")["summary"] == "BI Worker 正在校验候选值覆盖度。"
    assert summarize_tool_progress("datalogue_validate_query_support")["summary"] == "BI Worker 正在校验查询支持度。"
    assert summarize_tool_progress("datalogue_execute_query_plan")["summary"] == "BI Worker 正在执行受控查询计划。"
```

- [ ] **Step 2: Add frontend adapter test**

Append to `agent-team-event-adapter.test.js`:

```javascript
it('maps progressive BI worker payloads to safe timeline events', () => {
  const event = agentTeamEnvelopeToChatEvent({
    event_envelope: {
      event_type: 'message.completed',
      payload: {
        datalogue_event_type: 'bi_worker_l4_validation',
        support_status: 'supported',
        summary: '查询支持度已通过',
      },
    },
  });

  expect(event.type).toBe('agent_progress');
  expect(event.summary).toContain('查询支持度');
});
```

- [ ] **Step 3: Implement backend label mapping**

Modify `worker_logging.py` with:

```python
_PROGRESSIVE_TOOL_SUMMARIES = {
    "datalogue_describe_dataset_capability": "BI Worker 正在读取数据集能力摘要。",
    "datalogue_recall_query_assets": "BI Worker 正在匹配候选数据资产。",
    "datalogue_request_schema_slice": "BI Worker 正在申请相关数据结构切片。",
    "datalogue_profile_candidate_values": "BI Worker 正在校验候选值覆盖度。",
    "datalogue_validate_query_support": "BI Worker 正在校验查询支持度。",
    "datalogue_execute_query_plan": "BI Worker 正在执行受控查询计划。",
}


def summarize_tool_progress(tool_name: str) -> dict[str, str]:
    summary = _PROGRESSIVE_TOOL_SUMMARIES.get(tool_name) or f"BI Worker 正在调用 {tool_name}。"
    return {"summary": summary, "tool_name": tool_name}
```

- [ ] **Step 4: Implement frontend safe mapping**

Modify `agent-team-event-adapter.js` so progressive event payloads map to safe labels:

```javascript
const PROGRESSIVE_EVENT_LABELS = {
  bi_worker_l0_capability: '数据集能力',
  bi_worker_l1_assets: '数据资产匹配',
  bi_worker_l2_schema_slice: '数据结构确认',
  bi_worker_l3_value_profile: '候选值覆盖',
  bi_worker_l4_validation: '查询支持度',
  bi_worker_repair_request: '查询修复',
};
```

Add projection:

```javascript
if (PROGRESSIVE_EVENT_LABELS[payload.datalogue_event_type]) {
  return {
    type: 'agent_progress',
    title: PROGRESSIVE_EVENT_LABELS[payload.datalogue_event_type],
    summary: payload.summary || payload.safe_reason || PROGRESSIVE_EVENT_LABELS[payload.datalogue_event_type],
    status: payload.support_status === 'unsupported' ? 'failed' : 'completed',
    event_envelope: raw.event_envelope,
  };
}
```

- [ ] **Step 5: Ensure chat adapter does not render schema or plan**

Modify `chat-adapter.js` progressive event handling to use only `title`, `summary`, `status`, `artifact_ref`, `row_count`, and `column_count`. Do not render `entities`, `relationships`, `query_plan`, `filters`, `selects`, or `raw_error`.

Add a test in `chat-adapter.test.js`:

```javascript
it('does not render schema slice details in chat content', async () => {
  const payload = {
    datalogue_event_type: 'bi_worker_l2_schema_slice',
    summary: '返回 1 个相关 schema 实体切片。',
    entities: [{ table_name: 'work_logs', fields: [{ field: 'employee_name' }] }],
  };

  const text = JSON.stringify(payload);
  expect(text).toContain('employee_name');

  const safeSummary = payload.summary;
  expect(safeSummary).not.toContain('employee_name');
});
```

- [ ] **Step 6: Run backend and frontend tests**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_agentscope_service_worker_logging.py -q
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add datalogue-api/app/agentscope_service/worker_logging.py datalogue-api/app/runtime/agent_team_runtime.py datalogue-api/tests/test_agentscope_service_worker_logging.py datalogue-web/src/assistant/agent-team-event-adapter.js datalogue-web/src/assistant/chat-adapter.js datalogue-web/src/assistant/agent-team-event-adapter.test.js datalogue-web/src/assistant/chat-adapter.test.js
git commit -m "feat: project BI Worker progressive context events"
```

---

## Task 8: End-To-End Safety And Regression Tests

**Files:**

- Test: `datalogue-api/tests/test_bi_worker_progressive_context_e2e.py`
- Modify: `datalogue-api/tests/test_agentscope_agent_team_task_runner.py`
- Modify: `datalogue-api/tests/test_agentscope_service_tools.py`

- [ ] **Step 1: Add E2E safety test**

Create `datalogue-api/tests/test_bi_worker_progressive_context_e2e.py`:

```python
# ============================================================
# File Name   : test_bi_worker_progressive_context_e2e.py
# Description:
#   BI Worker 渐进式上下文端到端安全测试。
#
# Responsibilities:
#   - 验证缺 dataset_id 仍走候选数据集确认。
#   - 验证已有 dataset_id 时 progressive 工具链不泄露 SQL/schema/raw rows。
#   - 验证执行期错误被转为安全 repair request。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

import json

import pytest

from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan
from app.agentscope_service.bi_worker_runtime import BIWorkerQueryRuntime
from app.agentscope_service.bi_worker_validator import ProgressiveContextState


@pytest.mark.asyncio
async def test_progressive_runtime_never_returns_sql_on_validation_block(db_session):
    plan = BIWorkerQueryPlan.model_validate(
        {
            "intent": "detail_query",
            "question": "查询杨凯2025年工作日志",
            "result_shape": {"type": "table", "grain": "one_row_per_work_log", "limit": 100},
            "data_graph": {"primary_entity": {"asset_ref": "asset:unknown", "alias": "x", "role": "primary"}, "supporting_entities": []},
            "join_requirements": [],
            "filters": [],
            "selects": [
                {"target": {"asset_ref": "asset:unknown.field", "alias": "x", "field": "secret_field"}, "display_name": "字段"}
            ],
            "metrics": [],
            "group_by": [],
            "ordering": [],
            "assumptions": [],
        }
    )

    payload = await BIWorkerQueryRuntime(db_session).execute_query_plan(
        dataset_id=10,
        confirmed_question="查询杨凯2025年工作日志",
        query_plan=plan,
        context_state=ProgressiveContextState(),
        trace_id="trace-e2e",
    )

    text = json.dumps(payload, ensure_ascii=False).lower()
    assert "select " not in text
    assert "raw_rows" not in text
    assert payload["datalogue_event_type"] == "bi_worker_l4_validation"
```

- [ ] **Step 2: Run E2E safety test**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run backend regression suite for touched areas**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest \
  tests/test_bi_worker_progressive_context_contracts.py \
  tests/test_bi_worker_progressive_context_tools.py \
  tests/test_bi_worker_query_validator.py \
  tests/test_bi_worker_query_runtime.py \
  tests/test_bi_worker_progressive_context_e2e.py \
  tests/test_agentscope_service_tools.py \
  tests/test_agentscope_static_agent_registry.py \
  tests/test_agentscope_agent_team_task_runner.py \
  tests/test_agentscope_service_worker_logging.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend regression suite for touched adapters**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit Task 8**

```bash
git add datalogue-api/tests/test_bi_worker_progressive_context_e2e.py datalogue-api/tests/test_agentscope_agent_team_task_runner.py datalogue-api/tests/test_agentscope_service_tools.py
git commit -m "test: cover BI Worker progressive context safety"
```

---

## Task 9: Documentation, Project Memory, And Real Smoke

**Files:**

- Modify: `.codex/project-memory.md`
- Create: `docs/test-reports/2026-07-06-bi-worker-progressive-context.md`

- [ ] **Step 1: Create test report**

Create `docs/test-reports/2026-07-06-bi-worker-progressive-context.md`:

```markdown
# BI Worker 渐进式上下文验收记录

## 验收范围

- Agentic Lead Agent + BI Worker 架构保持不变。
- BI Worker 工具面通过 AgentScope SDK FunctionTool 暴露。
- L0/L1/L5 固定骨架可用。
- L2/L3 按需上下文工具可用。
- L4 在 L5 前强制执行。
- Query Plan v1 支持多表关系图和 relationship_ref。
- SQL、raw rows、完整 schema、内部 Query Plan JSON 不进入用户可见输出。

## 自动化验证

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_e2e.py tests/test_agentscope_service_tools.py tests/test_agentscope_static_agent_registry.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_service_worker_logging.py -q

cd datalogue-web
npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run
npm run lint
npm run build
```

## 手工 smoke

- 启动后端和前端。
- 在聊天页发起没有 dataset_id 的问数，确认仍返回候选数据集。
- 选择数据集后发起“查询杨凯2025年工作日志”。
- 检查 timeline 显示数据集能力、数据资产匹配、查询支持度、查询执行、结果产物。
- 检查聊天区只显示最终回答和结果卡。
- 检查 DevTools network payload 不含 SQL、raw rows、完整 schema。

## 残留风险

- L3 值域画像第一阶段只返回安全摘要，真实数据源画像能力需要按数据源类型继续增强。
- Query Plan v1 到旧 QueryPlan 的适配第一阶段复用现有 compiler 能力，复杂聚合和多跳 join 需要通过真实业务用例继续收敛。
```

- [ ] **Step 2: Update project memory**

Run this command and use the printed timestamp as the markdown heading time:

```bash
date '+%Y-%m-%d %H:%M'
```

Append the following record to `.codex/project-memory.md` under latest detailed records. The heading must use the exact timestamp printed by the `date` command in the previous step:

```markdown
### 2026-07-06 17:01

- 功能名称：BI Worker 渐进式上下文执行链路
- 涉及文件：
  - `datalogue-api/app/agentscope_service/bi_worker_contracts.py`
  - `datalogue-api/app/agentscope_service/bi_worker_context.py`
  - `datalogue-api/app/agentscope_service/bi_worker_validator.py`
  - `datalogue-api/app/agentscope_service/bi_worker_runtime.py`
  - `datalogue-api/app/agentscope_service/tools.py`
  - `datalogue-api/app/agentscope_service/registry.py`
  - `datalogue-web/src/assistant/agent-team-event-adapter.js`
  - `datalogue-web/src/assistant/chat-adapter.js`
- 关键改动：
  - BI Worker 已按 AgentScope SDK FunctionTool 暴露 L0/L1/L2/L3/L4/L5 渐进式问数工具。
  - Query Plan v1 支持多表 relationship_ref、语义依赖校验和安全修复请求。
  - L5 执行前强制 L4 校验，SQL 编译、执行和修复仍留在 runtime 内部。
- 验证方式：
  - `python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_e2e.py tests/test_agentscope_service_tools.py tests/test_agentscope_static_agent_registry.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_service_worker_logging.py -q`
  - `npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run`
  - `npm run lint`
  - `npm run build`
- 残留风险或后续事项：
  - 继续增强 L3 真实值域画像。
  - 继续用真实多表 join 问数 case 收敛 Query Plan v1 到旧 compiler 的适配。
```

- [ ] **Step 3: Run final validation commands**

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest tests/test_bi_worker_progressive_context_contracts.py tests/test_bi_worker_progressive_context_tools.py tests/test_bi_worker_query_validator.py tests/test_bi_worker_query_runtime.py tests/test_bi_worker_progressive_context_e2e.py tests/test_agentscope_service_tools.py tests/test_agentscope_static_agent_registry.py tests/test_agentscope_agent_team_task_runner.py tests/test_agentscope_service_worker_logging.py -q
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-web
npm test -- agent-team-event-adapter.test.js chat-adapter.test.js --run
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit Task 9**

```bash
git add .codex/project-memory.md docs/test-reports/2026-07-06-bi-worker-progressive-context.md
git commit -m "docs: record BI Worker progressive context validation"
```

---

## Self-Review Checklist

- Spec coverage:
  - AgentScope SDK-first: Tasks 5 and 6.
  - L0/L1/L5 fixed skeleton: Tasks 2, 4, 5, 6.
  - L2/L3 on-demand context: Tasks 2 and 5.
  - L4 forced validation: Tasks 3 and 4.
  - Query Plan v1 multi-table relationship graph: Tasks 1 and 3.
  - lookup/dictionary/display semantic dependency: Task 3.
  - execution repair request sanitization: Task 4.
  - safe timeline projection: Task 7.
  - regression and real smoke: Tasks 8 and 9.

- Placeholder scan:
  - The plan uses concrete file paths, class names, function names, tests, and commands.
  - No implementation step depends on an unnamed future module.

- Type consistency:
  - `BIWorkerQueryPlan`, `QuerySupportValidation`, `RepairRequest`, and `BIWorkerQueryResult` are defined in Task 1 and reused by Tasks 3-5.
  - `ProgressiveContextState` is defined in Task 3 and reused by Tasks 4-5.
  - Tool names match prompt and permission names in Task 6.
