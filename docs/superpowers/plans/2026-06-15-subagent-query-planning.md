# SubAgent Query Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first version of the full DatasetSubAgent planning architecture so blueprints, semantic assets, schema fields, and tables become candidates before a machine-readable query plan chooses the execution strategy.

**Architecture:** LeadAgent remains the control plane for session, permissions, Manifest routing, dataset selection, and time context. DatasetSubAgent becomes the single-dataset planning and execution unit with context assembly, candidate recall, query planning, strategy dispatch, and existing QueryGraph/blueprint executors underneath. QueryGraph stays as the DSL/SQL execution engine and is not rewritten in this version.

**Tech Stack:** FastAPI, SQLAlchemy, LangGraph, LangChain ChatOpenAI-compatible LLM, existing Datalogue `DatasetSubAgent`, `build_dataset_query_context`, `execute_analysis_blueprint`, `InProcessDatasetSubAgentRunner`, pytest.

---

## Scope Check

The design spans planning, candidate recall, SubAgent orchestration, chat streaming, and observability. These are not independent products: they are one execution chain and each task below produces a working checkpoint. Do not start second-version planning-quality features such as historical successful queries, multi-blueprint comparison UI, or multi-dataset SubAgent orchestration in this implementation pass.

## File Structure

- Create `datalogue-api/app/services/subagent_planning/contracts.py`
  - Owns dataclasses, enums, JSON-safe helpers, and validation for candidate assets, query plans, planning events, and SubAgent results.
- Create `datalogue-api/app/services/subagent_planning/asset_recall.py`
  - Owns lightweight schema/context recall and converts dataset context structures into six candidate asset types.
- Create `datalogue-api/app/services/subagent_planning/planner.py`
  - Owns hard rules, LLM planner invocation, output validation, and rule fallback.
- Create `datalogue-api/app/services/subagent_planning/execution.py`
  - Owns strategy-specific adapters for blueprint execution, QueryGraph execution setup, clarify/reject result creation, and reference-context formatting.
- Create `datalogue-api/app/services/subagent_planning/__init__.py`
  - Re-exports the public planning contracts and helpers used by `DatasetSubAgent`.
- Modify `datalogue-api/app/services/dataset_subagent.py`
  - Upgrade from tool facade to `DatasetSubAgent.run(...)` orchestration while keeping existing `resolve_*` methods during migration.
- Modify `datalogue-api/app/services/runner.py`
  - Add optional query-plan fields to `DatasetSubAgentRequest` only if needed by the execution adapter.
- Modify `datalogue-api/app/graph/state.py`
  - Add `candidate_assets`, `query_plan`, and `query_plan_debug` fields to `AgentState`.
- Modify `datalogue-api/app/graph/nodes.py`
  - Let `schema_recall_node` consume `query_plan` and blueprint reference context when present.
  - Let `dsl_generate_node` include query-plan and reference-only blueprint instructions in the prompt.
- Modify `datalogue-api/app/api/chat.py`
  - Replace scattered SubAgent pre-Graph calls with `DatasetSubAgent.run(...)` event forwarding.
  - Persist `candidate_assets` and `query_plan` to final payload, response metadata, and trace metadata.
- Modify `datalogue-web/src/assistant/chat-adapter.js`
  - Preserve the new `query_plan` and `candidate_assets` fields in assistant metadata.
- Modify frontend step rendering files if needed after inspection, likely `datalogue-web/src/assistant/agent-panel.jsx` or `datalogue-web/src/assistant/message-content.jsx`
  - Render the simplified “查询规划” step if the existing step panel does not already render generic step payloads.
- Tests:
  - Create `datalogue-api/tests/test_subagent_planning_contracts.py`
  - Create `datalogue-api/tests/test_subagent_candidate_assets.py`
  - Create `datalogue-api/tests/test_subagent_query_planner.py`
  - Create `datalogue-api/tests/test_subagent_run.py`
  - Modify `datalogue-api/tests/test_chat.py`
  - Modify or extend `datalogue-api/tests/test_dataset_subagent.py`

## Task 1: Planning Contracts

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/__init__.py`
- Create: `datalogue-api/app/services/subagent_planning/contracts.py`
- Create: `datalogue-api/tests/test_subagent_planning_contracts.py`
- Modify: `datalogue-api/app/graph/state.py`

- [ ] **Step 1: Write contract tests**

Create `datalogue-api/tests/test_subagent_planning_contracts.py`:

```python
from app.services.subagent_planning.contracts import (
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    normalize_query_plan,
)


def test_candidate_asset_serializes_reference_usage():
    asset = CandidateAsset(
        asset_type="blueprint",
        asset_id=12,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.78,
        match_signals=[{"type": "keyword", "value": "日报", "score": 0.78}],
        metadata={"sql_template": "select * from daily where user_name = :user_name"},
        usage="reference",
        match_reason="关键词命中：日报",
    )

    payload = asset.to_dict()

    assert payload["asset_type"] == "blueprint"
    assert payload["usage"] == "reference"
    assert payload["metadata"]["sql_template"].startswith("select")


def test_query_plan_rejects_invalid_execution_strategy():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "unknown",
        "confidence": 0.5,
        "selected_assets": [],
        "reference_assets": [],
        "rejected_assets": [],
        "required_inputs": [],
        "clarification": None,
        "fallback_reason": None,
        "planner_source": "llm",
        "explanation": {"summary": "非法策略"},
    }

    try:
        normalize_query_plan(raw)
    except QueryPlanValidationError as exc:
        assert "execution_strategy" in str(exc)
    else:
        raise AssertionError("invalid execution_strategy should fail validation")


def test_query_plan_serializes_selected_reference_and_rejected_assets():
    selected = CandidateAsset(
        asset_type="field",
        asset_id="table:user_logs.column:id",
        name="id",
        display_name="日志ID",
        source="schema",
        confidence=0.9,
        match_signals=[],
        metadata={"table_name": "user_logs", "column_name": "id"},
        usage="selected",
    )
    reference = CandidateAsset(
        asset_type="blueprint",
        asset_id=3,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.7,
        match_signals=[],
        metadata={"implementation_type": "sql_template"},
        usage="reference",
    )
    rejected = CandidateAsset(
        asset_type="metric",
        asset_id=8,
        name="日志总数",
        display_name="日志总数",
        source="semantic_metric",
        confidence=0.2,
        match_signals=[],
        metadata={},
        usage="rejected",
        reject_reason="用户要求明细列表，不需要聚合指标",
    )

    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="blueprint_as_reference",
        confidence=0.86,
        selected_assets=[selected],
        reference_assets=[reference],
        rejected_assets=[rejected],
        required_inputs=[],
        clarification=None,
        fallback_reason=None,
        planner_source="llm",
        explanation={
            "summary": "识别为明细查询",
            "why_not_blueprint_execute": "用户要求查询10条日志，不是个人日报固定分析。",
        },
    )

    payload = plan.to_dict()

    assert payload["execution_strategy"] == "blueprint_as_reference"
    assert payload["selected_assets"][0]["asset_type"] == "field"
    assert payload["reference_assets"][0]["asset_type"] == "blueprint"
    assert payload["rejected_assets"][0]["reject_reason"] == "用户要求明细列表，不需要聚合指标"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_planning_contracts.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.subagent_planning'`.

- [ ] **Step 3: Implement contracts**

Create `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
# ============================================================
# File Name   : __init__.py
# Description:
#   SubAgent 查询规划包的公共导出入口。
#
# Responsibilities:
#   - 暴露候选资产、查询计划和执行结果等稳定契约。
#   - 隔离 DatasetSubAgent 编排层与底层规划实现细节。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from app.services.subagent_planning.contracts import (
    CANDIDATE_ASSET_TYPES,
    EXECUTION_STRATEGIES,
    QUERY_TYPES,
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    SubAgentEvent,
    SubAgentResult,
    normalize_query_plan,
)

__all__ = [
    "CANDIDATE_ASSET_TYPES",
    "EXECUTION_STRATEGIES",
    "QUERY_TYPES",
    "CandidateAsset",
    "QueryPlan",
    "QueryPlanValidationError",
    "SubAgentEvent",
    "SubAgentResult",
    "normalize_query_plan",
]
```

Create `datalogue-api/app/services/subagent_planning/contracts.py`:

```python
# ============================================================
# File Name   : contracts.py
# Description:
#   DatasetSubAgent 查询规划的数据契约。
#
# Responsibilities:
#   - 定义候选资产、查询计划、流式事件和最终结果结构。
#   - 提供 JSON 安全序列化和查询计划枚举校验。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder

CandidateAssetType = Literal["blueprint", "metric", "dimension", "term", "field", "table"]
QueryType = Literal[
    "detail_query",
    "metric_query",
    "blueprint_query",
    "knowledge_qa",
    "ambiguous",
    "unsupported",
]
ExecutionStrategy = Literal[
    "blueprint_execute",
    "blueprint_as_reference",
    "query_graph",
    "clarify",
    "reject",
]
AssetUsage = Literal["selected", "reference", "rejected", "candidate"]
PlannerSource = Literal["llm", "fallback", "rules"]

CANDIDATE_ASSET_TYPES = {"blueprint", "metric", "dimension", "term", "field", "table"}
QUERY_TYPES = {
    "detail_query",
    "metric_query",
    "blueprint_query",
    "knowledge_qa",
    "ambiguous",
    "unsupported",
}
EXECUTION_STRATEGIES = {
    "blueprint_execute",
    "blueprint_as_reference",
    "query_graph",
    "clarify",
    "reject",
}
ASSET_USAGES = {"selected", "reference", "rejected", "candidate"}
PLANNER_SOURCES = {"llm", "fallback", "rules"}


class QueryPlanValidationError(ValueError):
    """查询计划结构不合法时抛出，调用方应进入规则 fallback。"""


@dataclass
class CandidateAsset:
    asset_type: str
    asset_id: str | int
    name: str
    display_name: str | None
    source: str
    confidence: float
    match_signals: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: str = "candidate"
    match_reason: str | None = None
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return jsonable_encoder(
            {
                "asset_type": self.asset_type,
                "asset_id": self.asset_id,
                "name": self.name,
                "display_name": self.display_name,
                "source": self.source,
                "confidence": round(float(self.confidence), 4),
                "match_signals": self.match_signals,
                "metadata": self.metadata,
                "usage": self.usage,
                "match_reason": self.match_reason,
                "reject_reason": self.reject_reason,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateAsset":
        asset_type = str(payload.get("asset_type") or "")
        usage = str(payload.get("usage") or "candidate")
        if asset_type not in CANDIDATE_ASSET_TYPES:
            raise QueryPlanValidationError(f"asset_type invalid: {asset_type}")
        if usage not in ASSET_USAGES:
            raise QueryPlanValidationError(f"asset usage invalid: {usage}")
        return cls(
            asset_type=asset_type,
            asset_id=payload.get("asset_id") or payload.get("id") or "",
            name=str(payload.get("name") or ""),
            display_name=payload.get("display_name"),
            source=str(payload.get("source") or ""),
            confidence=float(payload.get("confidence") or 0),
            match_signals=list(payload.get("match_signals") or []),
            metadata=dict(payload.get("metadata") or {}),
            usage=usage,
            match_reason=payload.get("match_reason"),
            reject_reason=payload.get("reject_reason"),
        )


@dataclass
class QueryPlan:
    query_type: str
    execution_strategy: str
    confidence: float
    selected_assets: list[CandidateAsset] = field(default_factory=list)
    reference_assets: list[CandidateAsset] = field(default_factory=list)
    rejected_assets: list[CandidateAsset] = field(default_factory=list)
    required_inputs: list[dict[str, Any]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    fallback_reason: str | None = None
    planner_source: str = "rules"
    explanation: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable_encoder(
            {
                "query_type": self.query_type,
                "execution_strategy": self.execution_strategy,
                "confidence": round(float(self.confidence), 4),
                "selected_assets": [asset.to_dict() for asset in self.selected_assets],
                "reference_assets": [asset.to_dict() for asset in self.reference_assets],
                "rejected_assets": [asset.to_dict() for asset in self.rejected_assets],
                "required_inputs": self.required_inputs,
                "clarification": self.clarification,
                "fallback_reason": self.fallback_reason,
                "planner_source": self.planner_source,
                "explanation": self.explanation,
                "debug": self.debug,
            }
        )


@dataclass
class SubAgentEvent:
    event_type: str
    payload: dict[str, Any]

    def to_sse_payload(self) -> dict[str, Any]:
        return jsonable_encoder({"type": self.event_type, **self.payload})


@dataclass
class SubAgentResult:
    final_state: dict[str, Any]
    query_plan: QueryPlan
    candidate_assets: dict[str, Any]
    step_traces: list[dict[str, Any]] = field(default_factory=list)


def _assets_from_payload(items: Any, usage: str) -> list[CandidateAsset]:
    assets: list[CandidateAsset] = []
    for item in items or []:
        if not isinstance(item, dict):
            raise QueryPlanValidationError(f"{usage} asset must be object")
        normalized = dict(item)
        normalized["usage"] = normalized.get("usage") or usage
        assets.append(CandidateAsset.from_dict(normalized))
    return assets


def normalize_query_plan(payload: dict[str, Any]) -> QueryPlan:
    query_type = str(payload.get("query_type") or "")
    execution_strategy = str(payload.get("execution_strategy") or "")
    planner_source = str(payload.get("planner_source") or "rules")
    if query_type not in QUERY_TYPES:
        raise QueryPlanValidationError(f"query_type invalid: {query_type}")
    if execution_strategy not in EXECUTION_STRATEGIES:
        raise QueryPlanValidationError(f"execution_strategy invalid: {execution_strategy}")
    if planner_source not in PLANNER_SOURCES:
        raise QueryPlanValidationError(f"planner_source invalid: {planner_source}")
    return QueryPlan(
        query_type=query_type,
        execution_strategy=execution_strategy,
        confidence=float(payload.get("confidence") or 0),
        selected_assets=_assets_from_payload(payload.get("selected_assets"), "selected"),
        reference_assets=_assets_from_payload(payload.get("reference_assets"), "reference"),
        rejected_assets=_assets_from_payload(payload.get("rejected_assets"), "rejected"),
        required_inputs=list(payload.get("required_inputs") or []),
        clarification=payload.get("clarification") if isinstance(payload.get("clarification"), dict) else None,
        fallback_reason=payload.get("fallback_reason"),
        planner_source=planner_source,
        explanation=dict(payload.get("explanation") or {}),
        debug=dict(payload.get("debug") or {}),
    )
```

- [ ] **Step 4: Add state fields**

Modify `datalogue-api/app/graph/state.py` after `metric_resolution`:

```python
    candidate_assets: Optional[dict]  # SubAgent 统一候选资产召回结果，含 blueprint/metric/dimension/term/field/table
    query_plan: Optional[dict]  # SubAgent 查询规划结果，决定 blueprint_execute/query_graph/clarify 等执行策略
    query_plan_debug: Optional[dict]  # 查询规划调试信息，供 trace 和审计页使用
```

- [ ] **Step 5: Run contract tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_planning_contracts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add datalogue-api/app/services/subagent_planning/__init__.py \
  datalogue-api/app/services/subagent_planning/contracts.py \
  datalogue-api/app/graph/state.py \
  datalogue-api/tests/test_subagent_planning_contracts.py
git commit -m "feat: add subagent planning contracts"
```

## Task 2: Lightweight Candidate Asset Recall

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/asset_recall.py`
- Create: `datalogue-api/tests/test_subagent_candidate_assets.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`

- [ ] **Step 1: Write candidate recall tests**

Create `datalogue-api/tests/test_subagent_candidate_assets.py`:

```python
from app.services.subagent_planning.asset_recall import (
    build_candidate_assets_from_context,
    recall_candidate_assets,
)


def test_build_candidate_assets_from_structured_context_keeps_six_types():
    context = {
        "schema_structured": {
            "dataset_name": "生产日志",
            "metrics": [{"id": 1, "name": "日志数量", "description": "日志总数"}],
            "dimensions": [{"id": 2, "name": "用户", "expr": "user_name"}],
            "terms": [{"id": 3, "name": "失败日志", "display_name": "失败日志", "aliases": ["异常日志"]}],
            "blueprints": [
                {
                    "id": 4,
                    "name": "个人日报查询",
                    "description": "查询个人日报",
                    "when_to_use": "用户询问个人日报时使用",
                    "implementation_type": "sql_template",
                    "parameters": [{"name": "user_name", "required": True}],
                    "sql_template": "select * from daily_report where user_name = :user_name",
                }
            ],
            "fields": [
                {
                    "table_name": "user_logs",
                    "column_name": "created_at",
                    "name": "created_at",
                    "data_type": "datetime",
                    "semantic": "日志创建时间",
                }
            ],
            "tables_json": {
                "selected_tables": [
                    {"name": "user_logs", "description": "用户日志表"},
                ]
            },
        },
        "dataset_context_debug": {"dataset_id": 10},
    }

    assets = build_candidate_assets_from_context(
        question="查询10条用户日志",
        dataset_id=10,
        context=context,
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    types = {asset["asset_type"] for asset in assets["assets"]}

    assert {"blueprint", "metric", "dimension", "term", "field", "table"}.issubset(types)
    assert assets["summary"]["blueprint_count"] == 1
    assert assets["summary"]["field_count"] == 1
    assert assets["recall_debug"]["schema_source"] == "lightweight_schema_recall"


def test_recall_candidate_assets_uses_lightweight_token_budget(db_session, monkeypatch):
    captured = {}

    def fake_build_context(db, dataset_id, *, question, token_budget, blueprint_context="", matched_assets=None):
        captured["dataset_id"] = dataset_id
        captured["question"] = question
        captured["token_budget"] = token_budget
        return {
            "schema_structured": {
                "dataset_name": "生产日志",
                "metrics": [],
                "dimensions": [],
                "terms": [],
                "blueprints": [],
                "fields": [],
                "tables_json": {},
            },
            "dataset_context_debug": {"dataset_id": dataset_id},
        }

    monkeypatch.setattr(
        "app.services.subagent_planning.asset_recall.build_dataset_query_context",
        fake_build_context,
    )

    result = recall_candidate_assets(
        db_session,
        dataset_id=10,
        question="查询10条用户日志",
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    assert captured == {"dataset_id": 10, "question": "查询10条用户日志", "token_budget": 2500}
    assert result["summary"]["blueprint_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_candidate_assets.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `asset_recall`.

- [ ] **Step 3: Implement candidate recall service**

Create `datalogue-api/app/services/subagent_planning/asset_recall.py`:

```python
# ============================================================
# File Name   : asset_recall.py
# Description:
#   SubAgent 轻量候选资产召回服务。
#
# Responsibilities:
#   - 前移轻量 Schema 召回，获得规划所需的结构化上下文。
#   - 统一输出 blueprint/metric/dimension/term/field/table 六类候选资产。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.dataset_context import build_dataset_query_context
from app.services.subagent_planning.contracts import CandidateAsset

LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET = 2500


def _norm(text: Any) -> str:
    return re.sub(r"[\s_`'\".]+", "", str(text or "").strip().lower())


def _score(question: str, *texts: Any) -> tuple[float, list[dict[str, Any]]]:
    q = _norm(question)
    signals: list[dict[str, Any]] = []
    best = 0.0
    for raw in texts:
        text = str(raw or "").strip()
        normalized = _norm(text)
        if not normalized:
            continue
        if normalized == q:
            best = max(best, 0.98)
            signals.append({"type": "exact", "value": text, "score": 0.98})
        elif normalized in q or q in normalized:
            best = max(best, 0.82)
            signals.append({"type": "contains", "value": text, "score": 0.82})
    return best, signals


def _asset(asset_type: str, asset_id: str | int, name: str, source: str, confidence: float, signals: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    return CandidateAsset(
        asset_type=asset_type,
        asset_id=asset_id,
        name=name,
        display_name=metadata.get("display_name") or metadata.get("semantic") or name,
        source=source,
        confidence=confidence,
        match_signals=signals,
        metadata=metadata,
        usage="candidate",
        match_reason=signals[0]["type"] if signals else "context_candidate",
    ).to_dict()


def _table_assets(structured: dict[str, Any], question: str) -> list[dict[str, Any]]:
    tables_json = structured.get("tables_json") or {}
    selected = tables_json.get("selected_tables") or tables_json.get("tables") or []
    assets: list[dict[str, Any]] = []
    for item in selected:
        if isinstance(item, str):
            name = item
            metadata = {"table_name": item}
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("table_name") or "")
            metadata = dict(item)
            metadata["table_name"] = name
        else:
            continue
        if not name:
            continue
        confidence, signals = _score(question, name, metadata.get("description"))
        assets.append(_asset("table", name, name, "schema", confidence, signals, metadata))
    return assets


def build_candidate_assets_from_context(
    *,
    question: str,
    dataset_id: int,
    context: dict[str, Any],
    manifest_version: str | None,
    bound_schema_version: str | None,
) -> dict[str, Any]:
    structured = context.get("schema_structured") or {}
    assets: list[dict[str, Any]] = []
    for blueprint in structured.get("blueprints") or []:
        confidence, signals = _score(
            question,
            blueprint.get("name"),
            blueprint.get("description"),
            blueprint.get("when_to_use"),
            " ".join(blueprint.get("trigger_keywords") or []),
        )
        metadata = dict(blueprint)
        assets.append(_asset("blueprint", blueprint.get("id") or blueprint.get("name"), str(blueprint.get("name") or ""), "analysis_blueprint", confidence, signals, metadata))
    for metric in structured.get("metrics") or []:
        confidence, signals = _score(question, metric.get("name"), metric.get("description"), metric.get("expr"))
        assets.append(_asset("metric", metric.get("id") or metric.get("name"), str(metric.get("name") or ""), "semantic_metric", confidence, signals, dict(metric)))
    for dimension in structured.get("dimensions") or []:
        confidence, signals = _score(question, dimension.get("name"), dimension.get("description"), dimension.get("expr"))
        assets.append(_asset("dimension", dimension.get("id") or dimension.get("name"), str(dimension.get("name") or ""), "semantic_dimension", confidence, signals, dict(dimension)))
    for term in structured.get("terms") or []:
        aliases = term.get("aliases") or []
        confidence, signals = _score(question, term.get("name"), term.get("display_name"), " ".join(map(str, aliases)))
        assets.append(_asset("term", term.get("id") or term.get("name"), str(term.get("name") or term.get("display_name") or ""), "business_term", confidence, signals, dict(term)))
    for field in structured.get("fields") or []:
        table_name = field.get("table_name") or field.get("table")
        column_name = field.get("column_name") or field.get("name") or field.get("column")
        asset_id = f"table:{table_name}.column:{column_name}"
        confidence, signals = _score(question, column_name, field.get("semantic"), field.get("description"), table_name)
        assets.append(_asset("field", asset_id, str(column_name or ""), "schema", confidence, signals, dict(field)))
    assets.extend(_table_assets(structured, question))
    summary = {
        "blueprint_count": sum(1 for asset in assets if asset["asset_type"] == "blueprint"),
        "metric_count": sum(1 for asset in assets if asset["asset_type"] == "metric"),
        "dimension_count": sum(1 for asset in assets if asset["asset_type"] == "dimension"),
        "term_count": sum(1 for asset in assets if asset["asset_type"] == "term"),
        "field_count": sum(1 for asset in assets if asset["asset_type"] == "field"),
        "table_count": sum(1 for asset in assets if asset["asset_type"] == "table"),
    }
    assets.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return {
        "dataset_id": dataset_id,
        "question": question,
        "assets": assets,
        "summary": summary,
        "recall_debug": {
            "schema_source": "lightweight_schema_recall",
            "manifest_version": manifest_version,
            "bound_schema_version": bound_schema_version,
            "dataset_context_debug": context.get("dataset_context_debug") or {},
        },
        "context": context,
    }


def recall_candidate_assets(
    db: Session,
    *,
    dataset_id: int,
    question: str,
    manifest_version: str | None,
    bound_schema_version: str | None,
) -> dict[str, Any]:
    context = build_dataset_query_context(
        db,
        dataset_id,
        question=question,
        token_budget=LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET,
    )
    return build_candidate_assets_from_context(
        question=question,
        dataset_id=dataset_id,
        context=context,
        manifest_version=manifest_version,
        bound_schema_version=bound_schema_version,
    )
```

- [ ] **Step 4: Export candidate recall helpers**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from app.services.subagent_planning.asset_recall import (
    build_candidate_assets_from_context,
    recall_candidate_assets,
)
```

Add these two names to `__all__`.

- [ ] **Step 5: Run candidate tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_candidate_assets.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add datalogue-api/app/services/subagent_planning/__init__.py \
  datalogue-api/app/services/subagent_planning/asset_recall.py \
  datalogue-api/tests/test_subagent_candidate_assets.py
git commit -m "feat: recall subagent candidate assets"
```

## Task 3: Rule Fallback Planner

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/planner.py`
- Create: `datalogue-api/tests/test_subagent_query_planner.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`

- [ ] **Step 1: Write fallback planner tests**

Create the first part of `datalogue-api/tests/test_subagent_query_planner.py`:

```python
from app.services.subagent_planning.planner import build_rule_based_query_plan


def _candidate(asset_type, asset_id, name, confidence=0.8, metadata=None):
    return {
        "asset_type": asset_type,
        "asset_id": asset_id,
        "name": name,
        "display_name": name,
        "source": "test",
        "confidence": confidence,
        "match_signals": [],
        "metadata": metadata or {},
        "usage": "candidate",
    }


def test_fallback_detail_query_uses_query_graph_without_metrics():
    candidate_assets = {
        "assets": [
            _candidate("field", "table:user_logs.column:id", "id", metadata={"table_name": "user_logs"}),
            _candidate("table", "user_logs", "user_logs"),
        ],
        "summary": {"field_count": 1, "table_count": 1, "blueprint_count": 0},
    }

    plan = build_rule_based_query_plan(
        question="查询10条用户日志",
        routing={"entry_route": "query_graph", "entry_intent": "detail_query"},
        candidate_assets=candidate_assets,
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "query_graph"
    assert plan.explanation["why_continue_without_metric"] == "明细查询不要求必须命中指标或维度。"


def test_fallback_blueprint_hit_detail_query_becomes_reference():
    candidate_assets = {
        "assets": [
            _candidate(
                "blueprint",
                3,
                "个人日报查询",
                metadata={
                    "parameters": [{"name": "user_name", "required": True}],
                    "sql_template": "select * from daily_report where user_name = :user_name",
                },
            ),
            _candidate("field", "table:user_logs.column:id", "id"),
        ],
        "summary": {"field_count": 1, "table_count": 1, "blueprint_count": 1},
    }

    plan = build_rule_based_query_plan(
        question="查询10条用户日志",
        routing={"entry_route": "analysis_blueprint", "entry_intent": "analysis_blueprint", "blueprint_id": 3},
        candidate_assets=candidate_assets,
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "blueprint_as_reference"
    assert plan.reference_assets[0].asset_type == "blueprint"
    assert "不是固定蓝图分析" in plan.explanation["why_not_blueprint_execute"]


def test_fallback_blueprint_query_missing_required_input_clarifies():
    candidate_assets = {
        "assets": [
            _candidate(
                "blueprint",
                3,
                "个人日报查询",
                metadata={
                    "parameters": [
                        {"name": "user_name", "required": True},
                        {"name": "start_date", "required": True, "type": "date"},
                    ]
                },
            )
        ],
        "summary": {"field_count": 0, "table_count": 0, "blueprint_count": 1},
    }

    plan = build_rule_based_query_plan(
        question="查一下日报",
        routing={"entry_route": "analysis_blueprint", "entry_intent": "analysis_blueprint", "blueprint_id": 3},
        candidate_assets=candidate_assets,
    )

    assert plan.query_type == "blueprint_query"
    assert plan.execution_strategy == "clarify"
    assert {item["name"] for item in plan.required_inputs} == {"user_name", "start_date"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_query_planner.py -q
```

Expected: FAIL with missing `planner` module.

- [ ] **Step 3: Implement rule fallback planner**

Create `datalogue-api/app/services/subagent_planning/planner.py` with this initial implementation:

```python
# ============================================================
# File Name   : planner.py
# Description:
#   SubAgent 查询规划器。
#
# Responsibilities:
#   - 使用规则硬约束和 LLM 输出生成稳定 QueryPlan。
#   - 在 LLM 不可用或输出不可信时提供规则 fallback。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.graph.llm import get_llm
from app.services.subagent_planning.contracts import (
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    normalize_query_plan,
)

DETAIL_PATTERNS = ("明细", "列表", "日志", "记录", "最近", "前", "条", "limit")
METRIC_PATTERNS = ("统计", "数量", "总数", "平均", "占比", "汇总", "趋势")
BLUEPRINT_PATTERNS = ("日报", "周报", "月报", "分析", "报告")


def _contains_any(question: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in (question or "") for pattern in patterns)


def _assets(candidate_assets: dict[str, Any], asset_type: str | None = None) -> list[CandidateAsset]:
    result: list[CandidateAsset] = []
    for raw in candidate_assets.get("assets") or []:
        if asset_type and raw.get("asset_type") != asset_type:
            continue
        result.append(CandidateAsset.from_dict(raw))
    return result


def _required_inputs(blueprint: CandidateAsset | None) -> list[dict[str, Any]]:
    if not blueprint:
        return []
    inputs: list[dict[str, Any]] = []
    for spec in blueprint.metadata.get("parameters") or []:
        if isinstance(spec, dict) and spec.get("required") and spec.get("name"):
            inputs.append({"name": spec["name"], "type": spec.get("type"), "source": "blueprint_parameter"})
    return inputs


def _with_usage(asset: CandidateAsset, usage: str, reject_reason: str | None = None) -> CandidateAsset:
    return CandidateAsset(
        asset_type=asset.asset_type,
        asset_id=asset.asset_id,
        name=asset.name,
        display_name=asset.display_name,
        source=asset.source,
        confidence=asset.confidence,
        match_signals=asset.match_signals,
        metadata=asset.metadata,
        usage=usage,
        match_reason=asset.match_reason,
        reject_reason=reject_reason,
    )


def build_rule_based_query_plan(
    *,
    question: str,
    routing: dict[str, Any],
    candidate_assets: dict[str, Any],
    fallback_reason: str | None = None,
) -> QueryPlan:
    blueprints = _assets(candidate_assets, "blueprint")
    fields = _assets(candidate_assets, "field")
    tables = _assets(candidate_assets, "table")
    top_blueprint = blueprints[0] if blueprints else None
    is_detail = routing.get("entry_intent") == "detail_query" or _contains_any(question, DETAIL_PATTERNS)
    is_metric = routing.get("entry_intent") == "metric_query" or _contains_any(question, METRIC_PATTERNS)
    is_blueprint_like = routing.get("entry_route") == "analysis_blueprint" or _contains_any(question, BLUEPRINT_PATTERNS)
    if is_detail and (fields or tables):
        references = [_with_usage(top_blueprint, "reference")] if top_blueprint and is_blueprint_like else []
        strategy = "blueprint_as_reference" if references else "query_graph"
        return QueryPlan(
            query_type="detail_query",
            execution_strategy=strategy,
            confidence=0.78,
            selected_assets=[_with_usage(asset, "selected") for asset in [*fields[:5], *tables[:3]]],
            reference_assets=references,
            rejected_assets=[],
            required_inputs=[],
            clarification=None,
            fallback_reason=fallback_reason,
            planner_source="fallback",
            explanation={
                "summary": "识别为明细查询，优先基于字段和表结构生成查询。",
                "why_not_blueprint_execute": "用户问题不是固定蓝图分析，蓝图最多作为参考证据。" if references else "",
                "why_continue_without_metric": "明细查询不要求必须命中指标或维度。",
            },
        )
    if is_blueprint_like and top_blueprint:
        required = _required_inputs(top_blueprint)
        if required:
            return QueryPlan(
                query_type="blueprint_query",
                execution_strategy="clarify",
                confidence=0.72,
                selected_assets=[],
                reference_assets=[],
                rejected_assets=[],
                required_inputs=required,
                clarification={
                    "message": "这个问题像固定蓝图分析，但还缺少必要参数。",
                    "required_inputs": required,
                },
                fallback_reason=fallback_reason,
                planner_source="fallback",
                explanation={"summary": "蓝图固定分析缺少必要参数，需要澄清。"},
            )
        return QueryPlan(
            query_type="blueprint_query",
            execution_strategy="blueprint_execute",
            confidence=0.75,
            selected_assets=[_with_usage(top_blueprint, "selected")],
            reference_assets=[],
            rejected_assets=[],
            required_inputs=[],
            clarification=None,
            fallback_reason=fallback_reason,
            planner_source="fallback",
            explanation={"summary": "蓝图命中且没有缺失必填参数，直接执行蓝图。"},
        )
    if is_metric:
        return QueryPlan(
            query_type="metric_query",
            execution_strategy="query_graph",
            confidence=0.65,
            selected_assets=[_with_usage(asset, "selected") for asset in [*fields[:5], *tables[:3]]],
            reference_assets=[],
            rejected_assets=[],
            required_inputs=[],
            clarification=None,
            fallback_reason=fallback_reason,
            planner_source="fallback",
            explanation={"summary": "识别为指标统计查询，进入 QueryGraph。"},
        )
    return QueryPlan(
        query_type="ambiguous",
        execution_strategy="clarify",
        confidence=0.5,
        selected_assets=[],
        reference_assets=[],
        rejected_assets=[],
        required_inputs=[{"name": "query_target", "type": "text", "source": "question"}],
        clarification={"message": "请补充要查询的对象、范围或业务术语。"},
        fallback_reason=fallback_reason,
        planner_source="fallback",
        explanation={"summary": "问题缺少明确查询对象。"},
    )
```

- [ ] **Step 4: Export planner helpers**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from app.services.subagent_planning.planner import build_rule_based_query_plan
```

Add `build_rule_based_query_plan` to `__all__`.

- [ ] **Step 5: Run fallback planner tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_query_planner.py -q
```

Expected: PASS for the three fallback tests.

- [ ] **Step 6: Commit Task 3**

```bash
git add datalogue-api/app/services/subagent_planning/__init__.py \
  datalogue-api/app/services/subagent_planning/planner.py \
  datalogue-api/tests/test_subagent_query_planner.py
git commit -m "feat: add subagent query plan fallback"
```

## Task 4: LLM Planner and Output Validation

**Files:**
- Modify: `datalogue-api/app/services/subagent_planning/planner.py`
- Modify: `datalogue-api/tests/test_subagent_query_planner.py`

- [ ] **Step 1: Add LLM planner tests**

Append to `datalogue-api/tests/test_subagent_query_planner.py`:

```python
class FakeLLMResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    model_name = "fake"

    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error

    def invoke(self, messages):
        if self.error:
            raise self.error
        return FakeLLMResponse(self.content)


def test_plan_query_with_llm_validates_and_returns_llm_plan(monkeypatch):
    from app.services.subagent_planning.planner import plan_query

    candidate_assets = {
        "assets": [
            _candidate("blueprint", 3, "个人日报查询", metadata={"parameters": []}),
            _candidate("field", "table:user_logs.column:id", "id"),
        ],
        "summary": {"field_count": 1, "table_count": 0, "blueprint_count": 1},
    }
    llm_payload = {
        "query_type": "detail_query",
        "execution_strategy": "blueprint_as_reference",
        "confidence": 0.88,
        "selected_assets": [candidate_assets["assets"][1]],
        "reference_assets": [candidate_assets["assets"][0]],
        "rejected_assets": [],
        "required_inputs": [],
        "clarification": None,
        "fallback_reason": None,
        "planner_source": "llm",
        "explanation": {"summary": "蓝图仅参考，重新生成 SQL。"},
    }
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, role="planner", db=None: FakeLLM(__import__("json").dumps(llm_payload, ensure_ascii=False)),
    )

    plan = plan_query(
        db=None,
        question="查询10条用户日志",
        routing={"entry_route": "analysis_blueprint", "entry_intent": "analysis_blueprint"},
        candidate_assets=candidate_assets,
    )

    assert plan.planner_source == "llm"
    assert plan.execution_strategy == "blueprint_as_reference"


def test_plan_query_falls_back_when_llm_raises(monkeypatch):
    from app.services.subagent_planning.planner import plan_query

    candidate_assets = {
        "assets": [_candidate("field", "table:user_logs.column:id", "id")],
        "summary": {"field_count": 1, "table_count": 0, "blueprint_count": 0},
    }
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, role="planner", db=None: FakeLLM(error=RuntimeError("planner down")),
    )

    plan = plan_query(
        db=None,
        question="查询10条用户日志",
        routing={"entry_route": "query_graph", "entry_intent": "detail_query"},
        candidate_assets=candidate_assets,
    )

    assert plan.planner_source == "fallback"
    assert plan.fallback_reason == "planner down"
    assert plan.execution_strategy == "query_graph"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_query_planner.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `plan_query`.

- [ ] **Step 3: Implement LLM planner**

Append these functions to `datalogue-api/app/services/subagent_planning/planner.py`:

```python
def _planner_system_prompt() -> str:
    return (
        "你是数语 DatasetSubAgent 的查询规划器。"
        "你只能输出严格 JSON，不能输出 Markdown。"
        "必须在 blueprint_execute、blueprint_as_reference、query_graph、clarify、reject 中选择一种执行策略。"
        "蓝图 SQL 在 blueprint_as_reference 下只能作为参考，不能原样执行。"
        "明细查询不要求必须命中指标或维度。"
    )


def _planner_human_prompt(
    *,
    question: str,
    routing: dict[str, Any],
    candidate_assets: dict[str, Any],
    multiturn_context: dict[str, Any] | None = None,
    lead_agent_context: dict[str, Any] | None = None,
) -> str:
    payload = {
        "question": question,
        "routing": routing,
        "candidate_assets": {
            "summary": candidate_assets.get("summary") or {},
            "assets": (candidate_assets.get("assets") or [])[:40],
        },
        "multiturn_context": multiturn_context or {},
        "lead_agent_context_summary": {
            "time_context": (lead_agent_context or {}).get("time_context"),
            "schema_status": (lead_agent_context or {}).get("schema_status"),
        },
        "output_schema": {
            "query_type": "detail_query|metric_query|blueprint_query|knowledge_qa|ambiguous|unsupported",
            "execution_strategy": "blueprint_execute|blueprint_as_reference|query_graph|clarify|reject",
            "confidence": 0.0,
            "selected_assets": [],
            "reference_assets": [],
            "rejected_assets": [],
            "required_inputs": [],
            "clarification": None,
            "fallback_reason": None,
            "planner_source": "llm",
            "explanation": {"summary": "中文解释"},
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _safe_json_parse(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise QueryPlanValidationError("planner output must be object")
    return parsed


def _validate_hard_rules(plan: QueryPlan, *, question: str, candidate_assets: dict[str, Any]) -> QueryPlan:
    if plan.execution_strategy == "blueprint_execute" and plan.required_inputs:
        raise QueryPlanValidationError("blueprint_execute cannot have required_inputs")
    if plan.execution_strategy == "blueprint_as_reference" and not plan.reference_assets:
        raise QueryPlanValidationError("blueprint_as_reference requires reference_assets")
    if plan.execution_strategy == "reject" and not plan.explanation.get("summary"):
        raise QueryPlanValidationError("reject requires explanation")
    if plan.query_type == "detail_query" and plan.execution_strategy == "clarify":
        has_field_or_table = any(
            asset.get("asset_type") in {"field", "table"}
            for asset in candidate_assets.get("assets") or []
        )
        if has_field_or_table:
            raise QueryPlanValidationError("detail_query with field/table candidates should continue")
    return plan


def plan_query(
    *,
    db: Session | None,
    question: str,
    routing: dict[str, Any],
    candidate_assets: dict[str, Any],
    multiturn_context: dict[str, Any] | None = None,
    lead_agent_context: dict[str, Any] | None = None,
) -> QueryPlan:
    try:
        llm = get_llm(temperature=0.0, role="planner", db=db)
        messages = [
            SystemMessage(content=_planner_system_prompt()),
            HumanMessage(
                content=_planner_human_prompt(
                    question=question,
                    routing=routing,
                    candidate_assets=candidate_assets,
                    multiturn_context=multiturn_context,
                    lead_agent_context=lead_agent_context,
                )
            ),
        ]
        response = llm.invoke(messages)
        raw_plan = _safe_json_parse(str(getattr(response, "content", "") or ""))
        raw_plan["planner_source"] = "llm"
        plan = normalize_query_plan(raw_plan)
        return _validate_hard_rules(plan, question=question, candidate_assets=candidate_assets)
    except Exception as exc:  # noqa: BLE001
        return build_rule_based_query_plan(
            question=question,
            routing=routing,
            candidate_assets=candidate_assets,
            fallback_reason=str(exc),
        )
```

- [ ] **Step 4: Export `plan_query`**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from app.services.subagent_planning.planner import build_rule_based_query_plan, plan_query
```

Add `plan_query` to `__all__`.

- [ ] **Step 5: Run planner tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_query_planner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add datalogue-api/app/services/subagent_planning/__init__.py \
  datalogue-api/app/services/subagent_planning/planner.py \
  datalogue-api/tests/test_subagent_query_planner.py
git commit -m "feat: add subagent llm planner"
```

## Task 5: Execution Strategy Helpers

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/execution.py`
- Create: `datalogue-api/tests/test_subagent_execution.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`

- [ ] **Step 1: Write execution helper tests**

Create `datalogue-api/tests/test_subagent_execution.py`:

```python
from app.services.subagent_planning.contracts import CandidateAsset, QueryPlan
from app.services.subagent_planning.execution import (
    build_blueprint_reference_context,
    build_clarify_result,
    build_reject_result,
)


def test_build_blueprint_reference_context_marks_sql_reference_only():
    blueprint = CandidateAsset(
        asset_type="blueprint",
        asset_id=3,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.8,
        metadata={
            "description": "查询个人日报",
            "parameters": [{"name": "user_name", "required": True}],
            "sql_template": "select * from daily_report where user_name = :user_name",
        },
        usage="reference",
    )
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="blueprint_as_reference",
        confidence=0.8,
        reference_assets=[blueprint],
        planner_source="llm",
        explanation={"summary": "参考蓝图，但重新生成 SQL。"},
    )

    context = build_blueprint_reference_context(plan)

    assert "只能作为参考证据" in context
    assert "不能原样执行" in context
    assert "select * from daily_report" in context


def test_build_clarify_result_uses_plan_message():
    plan = QueryPlan(
        query_type="blueprint_query",
        execution_strategy="clarify",
        confidence=0.7,
        required_inputs=[{"name": "user_name"}],
        clarification={"message": "请补充人员。"},
        planner_source="fallback",
        explanation={"summary": "缺少人员"},
    )

    result = build_clarify_result(plan)

    assert result.final_state["answer"] == "请补充人员。"
    assert result.final_state["entry_route"] == "clarify"


def test_build_reject_result_uses_explanation_summary():
    plan = QueryPlan(
        query_type="unsupported",
        execution_strategy="reject",
        confidence=0.7,
        planner_source="rules",
        explanation={"summary": "当前入口不支持导出操作。"},
    )

    result = build_reject_result(plan)

    assert result.final_state["answer"] == "当前入口不支持导出操作。"
    assert result.final_state["entry_route"] == "reject"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_execution.py -q
```

Expected: FAIL with missing `execution` module.

- [ ] **Step 3: Implement execution helpers**

Create `datalogue-api/app/services/subagent_planning/execution.py`:

```python
# ============================================================
# File Name   : execution.py
# Description:
#   SubAgent 查询计划执行策略辅助函数。
#
# Responsibilities:
#   - 生成蓝图参考上下文，保证 SQL 模板不会被误当作可直接执行 SQL。
#   - 生成 clarify/reject 的统一 SubAgentResult。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import json
from typing import Any

from app.services.subagent_planning.contracts import QueryPlan, SubAgentResult


def build_blueprint_reference_context(plan: QueryPlan) -> str:
    lines = [
        "【参考蓝图（非直接执行）】",
        "硬性要求: 以下蓝图 SQL 只能作为参考证据，不能原样执行；必须按用户真实问题重新生成 DSL/SQL；不得强行补蓝图必填参数。",
    ]
    for asset in plan.reference_assets:
        if asset.asset_type != "blueprint":
            continue
        metadata = asset.metadata or {}
        lines.append(f"蓝图名称: {asset.display_name or asset.name}")
        if metadata.get("description"):
            lines.append(f"蓝图描述: {metadata['description']}")
        if metadata.get("when_to_use"):
            lines.append(f"适用场景: {metadata['when_to_use']}")
        if metadata.get("parameters"):
            lines.append(f"参数定义: {json.dumps(metadata['parameters'], ensure_ascii=False)}")
        sql_template = metadata.get("sql_template") or metadata.get("call_template") or metadata.get("raw_sql")
        if sql_template:
            lines.append("参考 SQL 模板:")
            lines.append(str(sql_template))
    return "\n".join(lines)


def build_clarify_result(plan: QueryPlan) -> SubAgentResult:
    answer = (
        (plan.clarification or {}).get("message")
        or plan.explanation.get("summary")
        or "请补充要查询的对象、时间范围或业务口径。"
    )
    final_state = {
        "answer": answer,
        "entry_intent": "clarification",
        "entry_route": "clarify",
        "route_payload": {
            "kind": "query_plan_clarification",
            "required_inputs": plan.required_inputs,
            "query_plan": plan.to_dict(),
        },
        "query_plan": plan.to_dict(),
        "candidate_assets": None,
        "sql": None,
        "sql_list": [],
        "sql_result": None,
        "error": None,
        "should_retry": False,
    }
    return SubAgentResult(final_state=final_state, query_plan=plan, candidate_assets={}, step_traces=[])


def build_reject_result(plan: QueryPlan) -> SubAgentResult:
    answer = plan.explanation.get("summary") or "当前请求不适合通过问数入口处理。"
    final_state = {
        "answer": answer,
        "entry_intent": "rejection",
        "entry_route": "reject",
        "route_payload": {"kind": "query_plan_reject", "query_plan": plan.to_dict()},
        "query_plan": plan.to_dict(),
        "candidate_assets": None,
        "sql": None,
        "sql_list": [],
        "sql_result": None,
        "error": None,
        "should_retry": False,
    }
    return SubAgentResult(final_state=final_state, query_plan=plan, candidate_assets={}, step_traces=[])
```

- [ ] **Step 4: Export execution helpers**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from app.services.subagent_planning.execution import (
    build_blueprint_reference_context,
    build_clarify_result,
    build_reject_result,
)
```

Add these names to `__all__`.

- [ ] **Step 5: Run execution tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_execution.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add datalogue-api/app/services/subagent_planning/__init__.py \
  datalogue-api/app/services/subagent_planning/execution.py \
  datalogue-api/tests/test_subagent_execution.py
git commit -m "feat: add subagent execution helpers"
```

## Task 6: DatasetSubAgent.run Orchestration

**Files:**
- Modify: `datalogue-api/app/services/dataset_subagent.py`
- Modify: `datalogue-api/tests/test_subagent_run.py`

- [ ] **Step 1: Write `DatasetSubAgent.run` tests**

Create `datalogue-api/tests/test_subagent_run.py`:

```python
import pytest

from app.services.dataset_subagent import DatasetSubAgent
from app.services.subagent_planning.contracts import CandidateAsset, QueryPlan


class FakeTraceContext:
    trace_id = "trace-1"


def _request():
    from app.services.runner import DatasetSubAgentRequest

    return DatasetSubAgentRequest(
        question="查询10条用户日志",
        dataset_id=10,
        manifest_version="v1",
        bound_schema_version="schema-1",
        thread_id="thread-1",
        time_context={},
        thread_context={},
        route_decision={"decision": "selected", "dataset_name": "生产日志"},
        schema_status={},
        lead_agent_context={"time_context": {}, "schema_status": {}},
    )


@pytest.mark.asyncio
async def test_subagent_run_emits_candidate_assets_and_query_plan(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda db, dataset_id, question, manifest_version, bound_schema_version: {
            "dataset_id": dataset_id,
            "question": question,
            "assets": [],
            "summary": {"field_count": 0, "table_count": 0, "blueprint_count": 0},
            "recall_debug": {},
            "context": {"schema_context": "", "schema_structured": {}, "ddl_context": ""},
        },
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="ambiguous",
            execution_strategy="clarify",
            confidence=0.5,
            clarification={"message": "请补充查询对象。"},
            planner_source="fallback",
            explanation={"summary": "问题不明确"},
        ),
    )

    subagent = DatasetSubAgent(db=db_session, dataset_id=10)
    events = [event async for event in subagent.run(_request(), FakeTraceContext(), graph=None)]

    assert events[0].event_type == "candidate_assets"
    assert events[1].event_type == "query_plan"
    assert events[-1].event_type == "result"
    assert events[-1].payload["final_state"]["entry_route"] == "clarify"


@pytest.mark.asyncio
async def test_subagent_run_blueprint_reference_marks_context_and_query_graph(db_session, monkeypatch):
    seen_initial_state = {}

    class FakeRunner:
        async def run(self, request, trace_context, initial_state, **kwargs):
            seen_initial_state.update(initial_state)
            yield {
                "event": "on_chain_end",
                "metadata": {},
                "data": {"output": {"answer": "完成", "sql": "select 1", "sql_list": ["select 1"]}},
            }

    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda db, dataset_id, question, manifest_version, bound_schema_version: {
            "dataset_id": dataset_id,
            "question": question,
            "assets": [
                {
                    "asset_type": "blueprint",
                    "asset_id": 3,
                    "name": "个人日报查询",
                    "display_name": "个人日报查询",
                    "source": "analysis_blueprint",
                    "confidence": 0.8,
                    "match_signals": [],
                    "metadata": {"sql_template": "select * from daily_report"},
                    "usage": "candidate",
                }
            ],
            "summary": {"field_count": 1, "table_count": 1, "blueprint_count": 1},
            "recall_debug": {},
            "context": {
                "schema_context": "【语义层】",
                "schema_structured": {},
                "ddl_context": "create table user_logs(id int)",
                "query_constraints": {},
                "dataset_prompt_instructions": "",
                "dataset_context_debug": {},
                "datasource_context": {},
            },
        },
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="blueprint_as_reference",
            confidence=0.8,
            reference_assets=[
                CandidateAsset(
                    asset_type="blueprint",
                    asset_id=3,
                    name="个人日报查询",
                    display_name="个人日报查询",
                    source="analysis_blueprint",
                    confidence=0.8,
                    match_signals=[],
                    metadata={"sql_template": "select * from daily_report"},
                    usage="reference",
                )
            ],
            planner_source="llm",
            explanation={"summary": "参考蓝图"},
        ),
    )
    monkeypatch.setattr("app.services.dataset_subagent.InProcessDatasetSubAgentRunner", lambda graph, db: FakeRunner())

    subagent = DatasetSubAgent(db=db_session, dataset_id=10)
    events = [event async for event in subagent.run(_request(), FakeTraceContext(), graph=object())]

    assert events[-1].event_type == "result"
    assert seen_initial_state["query_plan"]["execution_strategy"] == "blueprint_as_reference"
    assert seen_initial_state["candidate_assets"]["summary"]["blueprint_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_run.py -q
```

Expected: FAIL because `DatasetSubAgent.run` does not exist.

- [ ] **Step 3: Add imports to `dataset_subagent.py`**

Modify `datalogue-api/app/services/dataset_subagent.py` imports:

```python
from collections.abc import AsyncGenerator

from app.services.runner import DatasetSubAgentRequest, InProcessDatasetSubAgentRunner
from app.services.subagent_planning import (
    QueryPlan,
    SubAgentEvent,
    build_blueprint_reference_context,
    build_clarify_result,
    build_reject_result,
    plan_query,
    recall_candidate_assets,
)
```

- [ ] **Step 4: Implement `DatasetSubAgent.run` skeleton**

Add this method inside `DatasetSubAgent` after the dataclass fields and before existing Phase 5 methods:

```python
    async def run(
        self,
        request: DatasetSubAgentRequest,
        trace_context: Any | None,
        *,
        graph: Any,
        initial_state: dict[str, Any] | None = None,
        graph_kwargs: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SubAgentEvent, None]:
        """统一编排单数据集 SubAgent：候选资产 -> 查询规划 -> 执行策略。"""
        base_state = dict(initial_state or {})
        question = base_state.get("question") or request.question
        routing = {
            "entry_route": base_state.get("entry_route"),
            "entry_intent": base_state.get("entry_intent"),
            "entry_reason": base_state.get("entry_reason"),
            "blueprint_id": base_state.get("blueprint_id"),
            "blueprint_match": base_state.get("blueprint_match"),
            "entities": base_state.get("entities") or {},
        }
        candidate_assets = recall_candidate_assets(
            self.db,
            dataset_id=request.dataset_id,
            question=question,
            manifest_version=request.manifest_version,
            bound_schema_version=request.bound_schema_version,
        )
        yield SubAgentEvent(
            event_type="candidate_assets",
            payload={
                "node": "candidate_assets",
                "display_name": "候选资产召回",
                "status": "done",
                "candidate_assets": {
                    key: value for key, value in candidate_assets.items() if key != "context"
                },
            },
        )
        query_plan = plan_query(
            db=self.db,
            question=question,
            routing=routing,
            candidate_assets=candidate_assets,
            multiturn_context=base_state.get("multiturn_context"),
            lead_agent_context=request.lead_agent_context,
        )
        yield SubAgentEvent(
            event_type="query_plan",
            payload={
                "node": "query_plan",
                "display_name": "查询规划",
                "status": "done",
                "query_plan": query_plan.to_dict(),
            },
        )
        if query_plan.execution_strategy == "clarify":
            result = build_clarify_result(query_plan)
            result.candidate_assets = {key: value for key, value in candidate_assets.items() if key != "context"}
            result.final_state["candidate_assets"] = result.candidate_assets
            yield SubAgentEvent(event_type="result", payload={"final_state": result.final_state})
            return
        if query_plan.execution_strategy == "reject":
            result = build_reject_result(query_plan)
            result.candidate_assets = {key: value for key, value in candidate_assets.items() if key != "context"}
            result.final_state["candidate_assets"] = result.candidate_assets
            yield SubAgentEvent(event_type="result", payload={"final_state": result.final_state})
            return
        if query_plan.execution_strategy == "blueprint_execute":
            blueprint_outcome = self.resolve_analysis_blueprint(
                blueprint_id=base_state.get("blueprint_id"),
                question=question,
                entry_route="analysis_blueprint",
                original_question=base_state.get("original_question") or question,
                resolved_question=base_state.get("resolved_question") or question,
                time_context=request.time_context,
            )
            final_state = {
                **base_state,
                "query_plan": query_plan.to_dict(),
                "candidate_assets": {key: value for key, value in candidate_assets.items() if key != "context"},
                "route_payload": blueprint_outcome.get("route_payload") or {},
                "answer": blueprint_outcome.get("answer"),
                "sql": blueprint_outcome.get("sql"),
                "sql_list": blueprint_outcome.get("sql_list") or [],
                "sql_result": blueprint_outcome.get("sql_result"),
                "error": blueprint_outcome.get("error"),
                "generation_mode": blueprint_outcome.get("generation_mode"),
                "should_retry": False,
            }
            yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
            return
        context = candidate_assets.get("context") or {}
        blueprint_reference = (
            build_blueprint_reference_context(query_plan)
            if query_plan.execution_strategy == "blueprint_as_reference"
            else ""
        )
        query_graph_state = {
            **base_state,
            **{key: value for key, value in context.items() if key != "context"},
            "question": question,
            "candidate_assets": {key: value for key, value in candidate_assets.items() if key != "context"},
            "query_plan": query_plan.to_dict(),
            "query_plan_debug": {
                "planner_source": query_plan.planner_source,
                "fallback_reason": query_plan.fallback_reason,
            },
        }
        if blueprint_reference:
            existing_blueprint_context = query_graph_state.get("blueprint_context") or ""
            query_graph_state["blueprint_context"] = (
                f"{existing_blueprint_context}\n\n{blueprint_reference}".strip()
            )
            query_graph_state["dataset_prompt_instructions"] = (
                f"{query_graph_state.get('dataset_prompt_instructions') or ''}\n\n{blueprint_reference}".strip()
            )
        runner = InProcessDatasetSubAgentRunner(graph, self.db)
        final_state = dict(query_graph_state)
        async for event in runner.run(
            request,
            trace_context,
            query_graph_state,
            **(graph_kwargs or {}),
        ):
            output = ((event.get("data") or {}).get("output") or {})
            if isinstance(output, dict):
                final_state.update(output)
            yield SubAgentEvent(event_type="graph_event", payload={"event": event})
        final_state["query_plan"] = query_plan.to_dict()
        final_state["candidate_assets"] = {key: value for key, value in candidate_assets.items() if key != "context"}
        yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
```

- [ ] **Step 5: Run SubAgent run tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_run.py -q
```

Expected: PASS.

- [ ] **Step 6: Run existing DatasetSubAgent tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_dataset_subagent.py tests/test_phase5_equivalence.py tests/test_phase6_equivalence.py tests/test_phase7_equivalence.py -q
```

Expected: PASS. Existing `resolve_*` methods must remain compatible.

- [ ] **Step 7: Commit Task 6**

```bash
git add datalogue-api/app/services/dataset_subagent.py \
  datalogue-api/tests/test_subagent_run.py
git commit -m "feat: orchestrate dataset subagent run"
```

## Task 7: QueryGraph Prompt Integration

**Files:**
- Modify: `datalogue-api/app/graph/nodes.py`
- Modify: `datalogue-api/tests/test_chat.py` or create `datalogue-api/tests/test_query_plan_prompting.py`

- [ ] **Step 1: Write prompt integration test**

Create `datalogue-api/tests/test_query_plan_prompting.py`:

```python
from app.graph.nodes import dsl_generate_node


class FakeResponse:
    content = '{"sql": "select id from user_logs limit 10"}'


class FakeLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return FakeResponse()


def test_dsl_generate_includes_query_plan_and_reference_blueprint(monkeypatch):
    fake_llm = FakeLLM()
    monkeypatch.setattr("app.graph.nodes.get_llm", lambda temperature=0.1, role="dsl", db=None: fake_llm)
    state = {
        "question": "查询10条用户日志",
        "schema_context": "【数据源真实表结构】\n表: user_logs | 列: id (int), content (text)",
        "query_constraints": {"enabled": False},
        "multiturn_context": None,
        "error": None,
        "query_plan": {
            "query_type": "detail_query",
            "execution_strategy": "blueprint_as_reference",
            "explanation": {"summary": "蓝图仅参考"},
        },
        "blueprint_context": "【参考蓝图（非直接执行）】\n不能原样执行\nselect * from daily_report",
    }

    result = dsl_generate_node(state, db=None)

    human_text = fake_llm.messages[1].content
    assert result["sql"] == "select id from user_logs limit 10"
    assert "查询规划" in human_text
    assert "blueprint_as_reference" in human_text
    assert "参考蓝图" in human_text
    assert "不能原样执行" in human_text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_query_plan_prompting.py -q
```

Expected: FAIL because `dsl_generate_node` does not include query-plan text.

- [ ] **Step 3: Add query-plan prompt formatter**

Modify `datalogue-api/app/graph/nodes.py` near other prompt formatting helpers:

```python
def _format_query_plan_for_prompt(query_plan: dict | None) -> str:
    if not isinstance(query_plan, dict):
        return ""
    lines = [
        "【查询规划】",
        f"查询类型: {query_plan.get('query_type')}",
        f"执行策略: {query_plan.get('execution_strategy')}",
    ]
    explanation = query_plan.get("explanation") or {}
    if explanation.get("summary"):
        lines.append(f"规划说明: {explanation['summary']}")
    if query_plan.get("execution_strategy") == "blueprint_as_reference":
        lines.append("硬性要求: 命中的蓝图只能作为参考证据，不能原样执行蓝图 SQL。")
    return "\n".join(lines)
```

- [ ] **Step 4: Include query-plan text in each DSL path**

Inside `dsl_generate_node`, after `multiturn_prompt = ...`, add:

```python
    query_plan_prompt = _format_query_plan_for_prompt(state.get("query_plan"))
```

In every branch where `human_text` is built, append:

```python
        if query_plan_prompt:
            human_text += f"\n\n{query_plan_prompt}"
        if state.get("blueprint_context"):
            human_text += f"\n\n{state.get('blueprint_context')}"
```

Apply this to the real schema path, inferred semantic path, deterministic semantic path, and no-schema path. Keep the exact existing prompt order otherwise.

- [ ] **Step 5: Run prompt test**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_query_plan_prompting.py -q
```

Expected: PASS.

- [ ] **Step 6: Run existing chat prompt tests**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_chat.py::test_schema_recall_appends_blueprint_context -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add datalogue-api/app/graph/nodes.py \
  datalogue-api/tests/test_query_plan_prompting.py
git commit -m "feat: pass query plan into dsl prompts"
```

## Task 8: Chat Integration and SSE Events

**Files:**
- Modify: `datalogue-api/app/api/chat.py`
- Modify: `datalogue-api/tests/test_chat.py`

- [ ] **Step 1: Add chat integration tests**

Append to `datalogue-api/tests/test_chat.py`:

```python
@pytest.mark.asyncio
async def test_stream_chat_emits_query_plan_step(monkeypatch, db_session):
    from app.api import chat as chat_module

    class FakeSubAgent:
        def __init__(self, db, dataset_id):
            self.db = db
            self.dataset_id = dataset_id

        async def run(self, request, trace_context, *, graph, initial_state=None, graph_kwargs=None):
            from app.services.subagent_planning.contracts import SubAgentEvent

            yield SubAgentEvent(
                event_type="query_plan",
                payload={
                    "node": "query_plan",
                    "display_name": "查询规划",
                    "status": "done",
                    "query_plan": {
                        "query_type": "detail_query",
                        "execution_strategy": "query_graph",
                        "explanation": {"summary": "明细查询"},
                    },
                },
            )
            yield SubAgentEvent(
                event_type="result",
                payload={
                    "final_state": {
                        **(initial_state or {}),
                        "answer": "完成",
                        "sql": "select 1",
                        "sql_list": ["select 1"],
                        "sql_result": {"columns": ["id"], "rows": [{"id": 1}], "row_count": 1},
                        "query_plan": {
                            "query_type": "detail_query",
                            "execution_strategy": "query_graph",
                            "explanation": {"summary": "明细查询"},
                        },
                        "candidate_assets": {"summary": {"field_count": 1}},
                        "error": None,
                    }
                },
            )

    monkeypatch.setattr(chat_module, "DatasetSubAgent", FakeSubAgent)
    monkeypatch.setattr(chat_module, "build_workflow", lambda db: object())
    # Reuse existing test helpers in this file for payload/conversation setup if present.
    payload = schemas.ChatRequest(question="查询10条用户日志", dataset_id=1)

    events = []
    async for event in chat_module._stream_chat_singleturn(payload, db_session):
        parsed = json.loads(event["data"])
        events.append(parsed)
        if parsed.get("type") == "final":
            break

    assert any(event.get("node") == "query_plan" for event in events)
    final = next(event for event in events if event.get("type") == "final")
    assert final["query_plan"]["execution_strategy"] == "query_graph"
    assert final["candidate_assets"]["summary"]["field_count"] == 1
```

If `schemas` or `json` are not imported in `test_chat.py`, add:

```python
import json
from app import schemas
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_chat.py::test_stream_chat_emits_query_plan_step -q
```

Expected: FAIL because `_stream_chat_singleturn` still uses scattered pre-Graph calls and does not forward `SubAgentEvent`.

- [ ] **Step 3: Add node display name and output keys**

Modify `datalogue-api/app/api/chat.py`:

```python
_NODE_DISPLAY_NAMES = {
    ...
    "candidate_assets": "候选资产召回",
    "query_plan": "查询规划",
}
```

Add to `_STATE_OUTPUT_KEYS`:

```python
    "candidate_assets",
    "query_plan",
    "query_plan_debug",
```

- [ ] **Step 4: Replace scattered SubAgent calls with `run`**

In `_stream_chat_singleturn`, keep LeadAgent, history, merge, term pending resolution, and `route_query_intent`. Replace the Phase 6/7/5 scattered block from `sub_agent = DatasetSubAgent(...)` through `blueprint_outcome` early-return handling with:

```python
    sub_agent = DatasetSubAgent(db=db, dataset_id=int(effective_dataset_id) if effective_dataset_id else 0)
```

Then build `initial_state` without `blueprint_outcome`, `term_conflict_outcome`, or `metric_outcome` dependencies:

```python
        "blueprint_context": None,
        "route_payload": _initial_route_payload,
        "generation_mode": None,
        "term_normalization": None,
        "semantic_asset_resolution": None,
        "metric_resolution": None,
        "candidate_assets": None,
        "query_plan": None,
        "query_plan_debug": None,
```

- [ ] **Step 5: Forward SubAgent events**

Replace direct `subagent_runner.run(...)` loop with:

```python
        async for sub_event in sub_agent.run(
            subagent_request,
            trace_context,
            graph=app_graph,
            initial_state=initial_state,
            graph_kwargs={
                "dataset_name": route_decision.get("dataset_name") or "",
                "version": "v2",
            },
        ):
            if sub_event.event_type in {"candidate_assets", "query_plan"}:
                sse_payload = sub_event.to_sse_payload()
                step_traces.append(sse_payload)
                yield _sse_data(sse_payload)
                continue
            if sub_event.event_type == "result":
                final_state.update(sub_event.payload.get("final_state") or {})
                continue
            if sub_event.event_type != "graph_event":
                yield _sse_data(sub_event.to_sse_payload())
                continue
            event = sub_event.payload["event"]
            # Keep the existing LangGraph event handling block below unchanged.
```

Move the existing LangGraph `kind/meta/lg_node` handling block inside this loop after `event = ...`.

- [ ] **Step 6: Include query plan in final payload and metadata**

In final response metadata and final SSE payload, add:

```python
        "candidate_assets": final_state.get("candidate_assets"),
        "query_plan": final_state.get("query_plan"),
        "query_plan_debug": final_state.get("query_plan_debug"),
```

In `trace_metadata`, add the same three fields.

- [ ] **Step 7: Run chat integration test**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_chat.py::test_stream_chat_emits_query_plan_step -q
```

Expected: PASS.

- [ ] **Step 8: Run focused backend regression**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_chat.py tests/test_subagent_run.py tests/test_subagent_query_planner.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 8**

```bash
git add datalogue-api/app/api/chat.py \
  datalogue-api/tests/test_chat.py
git commit -m "feat: route chat through subagent planner"
```

## Task 9: Frontend Metadata and Planning Step Display

**Files:**
- Modify: `datalogue-web/src/assistant/chat-adapter.js`
- Modify: `datalogue-web/src/assistant/agent-panel.jsx` if generic step rendering does not show `query_plan`

- [ ] **Step 1: Inspect current step rendering**

Run:

```bash
rg -n "queryProfile|route_payload|step|node|AgentPanel|display_name" datalogue-web/src/assistant datalogue-web/src/components
```

Expected: locate where SSE step payloads are normalized and rendered.

- [ ] **Step 2: Preserve new metadata fields**

In `datalogue-web/src/assistant/chat-adapter.js`, wherever final custom metadata is built from backend final payload, add:

```javascript
queryPlan: finalData.query_plan || finalData.queryPlan || null,
candidateAssets: finalData.candidate_assets || finalData.candidateAssets || null,
queryPlanDebug: finalData.query_plan_debug || finalData.queryPlanDebug || null,
```

Also preserve snake_case for audit compatibility if existing metadata already stores backend keys:

```javascript
query_plan: finalData.query_plan || null,
candidate_assets: finalData.candidate_assets || null,
query_plan_debug: finalData.query_plan_debug || null,
```

- [ ] **Step 3: Render simplified query planning step**

If generic step rendering already displays `display_name` and payload, do not add special UI. If it hides unknown node-specific fields, add this branch in the step details renderer:

```jsx
{step.node === "query_plan" && step.query_plan ? (
  <div className="space-y-1 text-xs text-muted-foreground">
    <div>查询类型：{step.query_plan.query_type || "未知"}</div>
    <div>执行策略：{step.query_plan.execution_strategy || "未知"}</div>
    {step.query_plan.explanation?.summary ? (
      <div>{step.query_plan.explanation.summary}</div>
    ) : null}
  </div>
) : null}
```

Use existing local class names and component style instead of adding a new design system.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd datalogue-web
npm run lint
npm run build
```

Expected: both PASS.

- [ ] **Step 5: Commit Task 9**

```bash
git add datalogue-web/src/assistant/chat-adapter.js \
  datalogue-web/src/assistant/agent-panel.jsx
git commit -m "feat: show subagent query planning"
```

If `agent-panel.jsx` is not changed because generic rendering already works, omit it from `git add`.

## Task 10: End-to-End Validation and Project Memory

**Files:**
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run full backend planning regression**

Run:

```bash
cd datalogue-api
.venv/bin/pytest tests/test_subagent_planning_contracts.py \
  tests/test_subagent_candidate_assets.py \
  tests/test_subagent_query_planner.py \
  tests/test_subagent_execution.py \
  tests/test_subagent_run.py \
  tests/test_chat.py \
  tests/test_dataset_subagent.py \
  tests/test_phase5_equivalence.py \
  tests/test_phase6_equivalence.py \
  tests/test_phase7_equivalence.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run:

```bash
cd datalogue-web
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 3: Run real chat-chain validation**

Start backend and frontend using the project’s usual local commands. If already running, reuse the active servers.

Run four real questions through `/api/chat/stream` or the local UI:

```text
查询张三昨天的个人日报
查询10条用户日志
最近10条失败日志有哪些
查一下日报
```

Expected checks:

- SSE includes a `node = "query_plan"` step named “查询规划”.
- final payload includes `query_plan`.
- final payload includes `candidate_assets`.
- trace metadata includes `query_plan` and `candidate_assets`.
- “查询10条用户日志” does not use `blueprint_execute`.
- “查询10条用户日志” does not ask for personal daily report time/user parameters.
- “最近10条失败日志有哪些” continues to QueryGraph when fields/tables are available.
- “查一下日报” returns a clarification.

- [ ] **Step 4: Update project memory**

Run:

```bash
date '+%Y-%m-%d %H:%M'
```

Use the command output as the markdown heading timestamp, then append this record body under that heading in `.codex/project-memory.md` in chronological order:

```markdown
- 功能名称：SubAgent 查询规划第一版
- 涉及文件：
  - `datalogue-api/app/services/subagent_planning/contracts.py`
  - `datalogue-api/app/services/subagent_planning/asset_recall.py`
  - `datalogue-api/app/services/subagent_planning/planner.py`
  - `datalogue-api/app/services/subagent_planning/execution.py`
  - `datalogue-api/app/services/dataset_subagent.py`
  - `datalogue-api/app/api/chat.py`
  - `datalogue-api/app/graph/nodes.py`
  - `datalogue-api/app/graph/state.py`
  - `datalogue-web/src/assistant/chat-adapter.js`
- 关键改动：
  - DatasetSubAgent 增加统一 `run` 主入口。
  - 新增六类候选资产召回和 QueryPlan。
  - 蓝图命中后先做适用性规划，再选择直接执行、参考、普通 QueryGraph、澄清或拒答。
  - SSE、final payload、response_metadata 和 trace 写入查询规划结果。
- 验证方式：
  - 后端规划相关 pytest 通过。
  - 前端 `npm run lint` 和 `npm run build` 通过。
  - 四个真实问数案例完成链路验证。
- 残留风险或后续事项：
  - 第二版再增强多候选蓝图对比、历史成功查询候选和审计页完整展示。
```

- [ ] **Step 5: Commit Task 10**

```bash
git add .codex/project-memory.md
git commit -m "docs: record subagent query planning"
```

- [ ] **Step 6: Stop and ask before Version 2**

After Task 10 is complete, send the user exactly this decision point:

```text
第一版已完成并验证通过。是否开始第二版“规划质量增强”？
```

Do not start Version 2 until the user confirms.

## Self-Review

- Spec coverage:
  - Candidate assets: Tasks 1-2.
  - QueryPlan machine contract: Task 1.
  - LLM planner and fallback: Tasks 3-4.
  - Blueprint execute/reference/query_graph/clarify/reject strategies: Tasks 3, 5, 6.
  - DatasetSubAgent as single-dataset orchestration unit: Task 6.
  - QueryGraph as execution engine: Tasks 6-8.
  - Frontend “查询规划” visibility: Task 9.
  - Trace/final metadata and real-chain validation: Tasks 8 and 10.
  - Stop before Version 2: Task 10 Step 6.
- Placeholder scan:
  - No unresolved placeholder words are intentionally left in task instructions.
  - Every code-writing step includes concrete code or exact insertion text.
- Type consistency:
  - `CandidateAsset`, `QueryPlan`, `SubAgentEvent`, `SubAgentResult`, `normalize_query_plan`, `recall_candidate_assets`, `plan_query`, and `DatasetSubAgent.run` are introduced before use.
  - `execution_strategy` values match the design: `blueprint_execute`, `blueprint_as_reference`, `query_graph`, `clarify`, `reject`.
  - State keys match planned metadata: `candidate_assets`, `query_plan`, `query_plan_debug`.
