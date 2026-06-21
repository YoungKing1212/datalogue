# SubAgent Planner Asset Detail Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a gated SubAgent planner detail loop that starts from lightweight asset catalogs, lets the planner request asset details for in-scope assets, handles wide-table field search safely, and refuses SQL generation when required context remains incomplete.

**Architecture:** Keep the change inside the SubAgent planning layer. Add focused contracts and services for asset detail requests, table/field detail hydration, planner loop orchestration, and SQL generation context assembly. Wire the loop behind `SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED=false` so the current `plan_query()` behavior remains the default path.

**Tech Stack:** Python 3, FastAPI service layer, SQLAlchemy session, Pydantic settings, pytest, existing Datalogue `subagent_planning` contracts and `DatasetSubAgent` runner.

---

## File Structure

- Create: `datalogue-api/app/services/subagent_planning/asset_catalog.py`
  - Projects raw `candidate_assets` into the lightweight planner catalog.
  - Keeps only `metric`, `dimension`, `table`, and `blueprint` assets.
  - Builds the allowed asset scope used by detail request validation.

- Create: `datalogue-api/app/services/subagent_planning/asset_detail.py`
  - Defines `AssetDetailRequest`, `AssetDetailResult`, and `AssetDetailService`.
  - Implements `table.full_schema`, `table.field_search`, `metric.detail`, `dimension.detail`, and `blueprint.detail`.
  - Enforces `top_k=30` default, `top_k<=50`, wide table `too_large`, and explainable field boost.

- Create: `datalogue-api/app/services/subagent_planning/detail_loop.py`
  - Runs at most 3 planner detail rounds.
  - Validates each request against the first-stage lightweight catalog.
  - Calls the existing planner LLM prompt through a new helper in `planner.py`.
  - Returns final `QueryPlan`, hydrated details, attempted requests, warnings, and `sql_generation_context`.

- Create: `datalogue-api/app/services/subagent_planning/sql_context.py`
  - Assembles `sql_generation_context` from final `QueryPlan` and fetched asset details.
  - Keeps complete field schemas out of `QueryPlan`, SSE final payload, and `last_success_task`.

- Modify: `datalogue-api/app/services/subagent_planning/contracts.py`
  - Extend `QueryPlan` with audit fields:
    `detail_rounds`, `attempted_detail_requests`, `asset_detail_coverage`,
    `missing_context`, `why_not_generate_sql`, `risk_flags`.
  - Extend `normalize_query_plan()` to accept those fields.

- Modify: `datalogue-api/app/services/subagent_planning/planner.py`
  - Add a prompt helper for the detail-loop planner call.
  - Add parsing helpers for `asset_detail_requests`.
  - Keep existing `plan_query()` behavior when the feature flag is off.

- Modify: `datalogue-api/app/services/dataset_subagent.py`
  - Use the detail loop only when the feature flag is enabled.
  - Emit `subagent.asset_detail` events with summaries only.
  - Add `sql_generation_context` to internal final state for downstream execution.

- Modify: `datalogue-api/app/core/config.py`
  - Add settings:
    `SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED`,
    `SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS`,
    `SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND`,
    `SUBAGENT_PLANNER_FIELD_SEARCH_DEFAULT_TOP_K`,
    `SUBAGENT_PLANNER_FIELD_SEARCH_MAX_TOP_K`,
    `SUBAGENT_PLANNER_TABLE_FULL_FIELD_LIMIT`,
    `SUBAGENT_PLANNER_TABLE_COMPACT_FIELD_LIMIT`.

- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`
  - Export the new catalog, detail, loop, and SQL context helpers used by tests and callers.

- Test: `datalogue-api/tests/test_subagent_asset_catalog.py`
- Test: `datalogue-api/tests/test_subagent_asset_detail.py`
- Test: `datalogue-api/tests/test_subagent_detail_loop.py`
- Modify: `datalogue-api/tests/test_subagent_query_planner.py`
- Modify: `datalogue-api/tests/test_subagent_run.py`

## Task 1: Lightweight Asset Catalog

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/asset_catalog.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`
- Test: `datalogue-api/tests/test_subagent_asset_catalog.py`

- [ ] **Step 1: Write failing tests for lightweight catalog projection**

Create `datalogue-api/tests/test_subagent_asset_catalog.py`:

```python
from app.services.subagent_planning.asset_catalog import (
    ALLOWED_CATALOG_ASSET_TYPES,
    build_allowed_asset_scope,
    project_lightweight_asset_catalog,
)


def _asset(asset_type, asset_id, *, metadata=None, confidence=0.8):
    return {
        "asset_type": asset_type,
        "asset_id": asset_id,
        "name": str(asset_id),
        "display_name": f"{asset_id} 展示名",
        "source": "schema",
        "confidence": confidence,
        "match_signals": [
            {"type": "exact", "value": str(asset_id), "score": confidence},
            {"type": "contains", "value": "额外信号", "score": 0.1},
        ],
        "metadata": metadata or {},
    }


def test_project_lightweight_asset_catalog_keeps_only_planner_catalog_types():
    raw = {
        "dataset_id": 10,
        "assets": [
            _asset("table", "plan_task_daily_record", metadata={"comment": "任务日报表", "fields": [{"name": "id"}]}),
            _asset("metric", "task_count", metadata={"description": "任务数", "expr": "count(*)"}),
            _asset("dimension", "department", metadata={"description": "部门"}),
            _asset("blueprint", "daily_report", metadata={"description": "日报分析", "sql": "select 1"}),
            _asset("field", "table:t.column:id", metadata={"column_comment": "主键"}),
            _asset("term", "用户", metadata={"description": "业务术语"}),
        ],
        "recall_debug": {"manifest_version": "manifest-v1", "bound_schema_version": "schema-v1"},
    }

    projected = project_lightweight_asset_catalog(raw)

    assert [asset["asset_type"] for asset in projected["assets"]] == [
        "table",
        "metric",
        "dimension",
        "blueprint",
    ]
    table_asset = projected["assets"][0]
    assert table_asset["description"] == "任务日报表"
    assert table_asset["schema_version"] == "schema-v1"
    assert table_asset["manifest_version"] == "manifest-v1"
    assert "fields" not in table_asset
    assert "metadata" not in table_asset
    assert len(table_asset["match_signals"]) == 2


def test_project_lightweight_asset_catalog_limits_match_signals():
    raw = {
        "assets": [
            _asset(
                "table",
                "wide_table",
                metadata={"comment": "宽表"},
                confidence=0.9,
            )
        ]
    }
    raw["assets"][0]["match_signals"] = [
        {"type": "exact", "value": "a", "score": 0.9},
        {"type": "contains", "value": "b", "score": 0.7},
        {"type": "synonym", "value": "c", "score": 0.6},
        {"type": "table_context", "value": "d", "score": 0.5},
    ]

    projected = project_lightweight_asset_catalog(raw, max_signals_per_asset=3)

    assert len(projected["assets"][0]["match_signals"]) == 3


def test_build_allowed_asset_scope_uses_type_and_asset_id():
    catalog = {
        "assets": [
            {"asset_type": "table", "asset_id": "plan_task_daily_record"},
            {"asset_type": "metric", "asset_id": 12},
        ]
    }

    scope = build_allowed_asset_scope(catalog)

    assert scope == {("table", "plan_task_daily_record"), ("metric", "12")}
    assert ALLOWED_CATALOG_ASSET_TYPES == {"metric", "dimension", "table", "blueprint"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_asset_catalog.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.subagent_planning.asset_catalog`.

- [ ] **Step 3: Implement `asset_catalog.py`**

Create `datalogue-api/app/services/subagent_planning/asset_catalog.py`:

```python
# ============================================================
# File Name   : asset_catalog.py
# Description:
#   SubAgent 查询规划使用的轻量资产目录投影。
#
# Responsibilities:
#   - 将候选资产召回结果压缩为 planner 首轮可消费的资产目录。
#   - 构建资产详情请求的允许范围，避免 planner 越过本轮召回边界。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from typing import Any

ALLOWED_CATALOG_ASSET_TYPES = {"metric", "dimension", "table", "blueprint"}


def _asset_description(asset: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    for key in ("description", "comment", "semantic", "business_desc", "expr", "when_to_use"):
        value = metadata.get(key) or asset.get(key)
        if value:
            return str(value)
    return None


def _schema_version(raw_assets: dict[str, Any]) -> str | None:
    recall_debug = raw_assets.get("recall_debug") or {}
    value = recall_debug.get("bound_schema_version") or raw_assets.get("bound_schema_version")
    return str(value) if value else None


def _manifest_version(raw_assets: dict[str, Any]) -> str | None:
    recall_debug = raw_assets.get("recall_debug") or {}
    value = recall_debug.get("manifest_version") or raw_assets.get("manifest_version")
    return str(value) if value else None


def project_lightweight_asset_catalog(
    candidate_assets: dict[str, Any],
    *,
    max_signals_per_asset: int = 3,
) -> dict[str, Any]:
    """把召回结果投影成不含完整 schema 的 planner 资产目录。"""

    schema_version = _schema_version(candidate_assets or {})
    manifest_version = _manifest_version(candidate_assets or {})
    projected: list[dict[str, Any]] = []
    for asset in list((candidate_assets or {}).get("assets") or []):
        if not isinstance(asset, dict):
            continue
        asset_type = str(asset.get("asset_type") or "")
        if asset_type not in ALLOWED_CATALOG_ASSET_TYPES:
            continue
        metadata = dict(asset.get("metadata") or {})
        asset_id = asset.get("asset_id")
        if asset_id is None or str(asset_id) == "":
            continue
        projected.append(
            {
                "asset_type": asset_type,
                "asset_id": asset_id,
                "name": str(asset.get("name") or asset_id),
                "display_name": asset.get("display_name") or asset.get("name") or str(asset_id),
                "description": _asset_description(asset, metadata),
                "confidence": round(float(asset.get("confidence") or 0), 4),
                "match_signals": list(asset.get("match_signals") or [])[:max_signals_per_asset],
                "schema_version": schema_version,
                "manifest_version": manifest_version,
            }
        )

    projected.sort(key=lambda item: float(item.get("confidence") or 0), reverse=True)
    return {
        "dataset_id": (candidate_assets or {}).get("dataset_id"),
        "question": (candidate_assets or {}).get("question"),
        "assets": projected,
        "summary": {
            "asset_count": len(projected),
            "asset_types": sorted({asset["asset_type"] for asset in projected}),
            "schema_version": schema_version,
            "manifest_version": manifest_version,
        },
    }


def build_allowed_asset_scope(lightweight_catalog: dict[str, Any]) -> set[tuple[str, str]]:
    """构建本轮允许展开详情的资产集合。"""

    scope: set[tuple[str, str]] = set()
    for asset in list((lightweight_catalog or {}).get("assets") or []):
        if not isinstance(asset, dict):
            continue
        asset_type = str(asset.get("asset_type") or "")
        asset_id = asset.get("asset_id")
        if asset_type and asset_id is not None:
            scope.add((asset_type, str(asset_id)))
    return scope
```

- [ ] **Step 4: Export catalog helpers**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from .asset_catalog import (
    ALLOWED_CATALOG_ASSET_TYPES,
    build_allowed_asset_scope,
    project_lightweight_asset_catalog,
)
```

Keep existing exports in the file. Add these imports without removing current imports.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_asset_catalog.py -q
```

Expected: `3 passed`.

Commit:

```bash
git add datalogue-api/app/services/subagent_planning/asset_catalog.py datalogue-api/app/services/subagent_planning/__init__.py datalogue-api/tests/test_subagent_asset_catalog.py
git commit -m "feat: add subagent lightweight asset catalog"
```

## Task 2: Asset Detail Contracts and Service

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/asset_detail.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`
- Test: `datalogue-api/tests/test_subagent_asset_detail.py`

- [ ] **Step 1: Write failing tests for detail request validation and table coverage**

Create `datalogue-api/tests/test_subagent_asset_detail.py`:

```python
from app.services.subagent_planning.asset_detail import (
    AssetDetailRequest,
    AssetDetailService,
    validate_asset_detail_requests,
)


def _table_asset(field_count):
    fields = [
        {
            "table_name": "wide_table",
            "column_name": f"field_{index}",
            "data_type": "varchar",
            "column_comment": f"字段 {index}",
        }
        for index in range(field_count)
    ]
    fields[0]["column_name"] = "created_at"
    fields[0]["data_type"] = "datetime"
    fields[0]["column_comment"] = "创建时间"
    fields[1]["column_name"] = "user_id"
    fields[1]["column_comment"] = "用户ID"
    return {
        "asset_type": "table",
        "asset_id": "wide_table",
        "name": "wide_table",
        "metadata": {"table_name": "wide_table", "comment": "测试宽表"},
        "confidence": 0.9,
    }, fields


def test_validate_asset_detail_requests_rejects_assets_outside_scope():
    requests = [
        AssetDetailRequest(
            asset_type="table",
            asset_id="not_recalled",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="需要看字段",
        )
    ]

    results = validate_asset_detail_requests(
        requests,
        allowed_scope={("table", "wide_table")},
        max_requests=5,
    )

    assert results.valid_requests == []
    assert results.errors[0].error_code == "asset_not_in_recall_scope"


def test_table_full_schema_returns_full_for_normal_table():
    table_asset, fields = _table_asset(12)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        full_field_limit=120,
        compact_field_limit=300,
    )

    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="生成 SQL",
        )
    )

    assert result.coverage == "full"
    assert result.payload["field_count"] == 12
    assert result.payload["returned_field_count"] == 12
    assert len(result.payload["fields"]) == 12


def test_table_full_schema_returns_too_large_without_fields_for_wide_table():
    table_asset, fields = _table_asset(301)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        full_field_limit=120,
        compact_field_limit=300,
    )

    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="生成 SQL",
        )
    )

    assert result.coverage == "too_large"
    assert result.payload["field_count"] == 301
    assert result.payload["returned_field_count"] == 0
    assert result.payload["fields"] == []
    assert result.payload["available_detail_requests"] == ["field_search"]


def test_field_search_defaults_top_k_and_caps_to_maximum_with_boost():
    table_asset, fields = _table_asset(80)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        field_search_default_top_k=30,
        field_search_max_top_k=50,
    )

    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="field_search",
            purpose="sql_generation",
            reason="搜索字段",
            query="用户 时间 状态",
            top_k=99,
        )
    )

    assert result.coverage == "partial"
    assert result.payload["requested_top_k"] == 99
    assert result.payload["capped_top_k"] == 50
    assert result.payload["returned_count"] <= 50
    created_at = next(item for item in result.payload["fields"] if item["name"] == "created_at")
    assert created_at["boosted"] is True
    assert created_at["boost_reason"] == "time_field_candidate"
    assert "text_score" in created_at
    assert "final_score" in created_at
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_asset_detail.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.subagent_planning.asset_detail`.

- [ ] **Step 3: Implement `asset_detail.py`**

Create `datalogue-api/app/services/subagent_planning/asset_detail.py`:

```python
# ============================================================
# File Name   : asset_detail.py
# Description:
#   SubAgent Planner 按需获取资产详情的服务和契约。
#
# Responsibilities:
#   - 校验 planner 资产详情请求是否位于本轮召回范围内。
#   - 返回表、字段搜索、指标、维度和蓝图的 SQL 生成详情。
#   - 对超宽表、字段搜索 top-k 和关键字段 boost 做显式约束。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .asset_recall import _match_factor, _norm

VALID_DETAIL_LEVELS = {
    "table": {"full_schema", "field_search"},
    "metric": {"detail"},
    "dimension": {"detail"},
    "blueprint": {"detail"},
}


@dataclass
class AssetDetailRequest:
    asset_type: str
    asset_id: str
    detail_level: str
    purpose: str
    reason: str | None = None
    query: str | None = None
    top_k: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AssetDetailRequest":
        return cls(
            asset_type=str(payload.get("asset_type") or ""),
            asset_id=str(payload.get("asset_id") or ""),
            detail_level=str(payload.get("detail_level") or ""),
            purpose=str(payload.get("purpose") or "sql_generation"),
            reason=payload.get("reason"),
            query=payload.get("query"),
            top_k=int(payload["top_k"]) if payload.get("top_k") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "asset_id": self.asset_id,
            "detail_level": self.detail_level,
            "purpose": self.purpose,
            "reason": self.reason,
            "query": self.query,
            "top_k": self.top_k,
        }


@dataclass
class AssetDetailError:
    request: AssetDetailRequest
    error_code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass
class AssetDetailValidationResult:
    valid_requests: list[AssetDetailRequest] = field(default_factory=list)
    errors: list[AssetDetailError] = field(default_factory=list)


@dataclass
class AssetDetailResult:
    request: AssetDetailRequest
    coverage: str
    payload: dict[str, Any]
    risk_flags: list[str] = field(default_factory=list)
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "coverage": self.coverage,
            "payload": self.payload,
            "risk_flags": self.risk_flags,
            "error_code": self.error_code,
        }


def validate_asset_detail_requests(
    requests: list[AssetDetailRequest],
    *,
    allowed_scope: set[tuple[str, str]],
    max_requests: int,
) -> AssetDetailValidationResult:
    result = AssetDetailValidationResult()
    if len(requests) > max_requests:
        for request in requests:
            result.errors.append(
                AssetDetailError(
                    request=request,
                    error_code="request_limit_exceeded",
                    message=f"单轮最多允许 {max_requests} 个资产详情请求。",
                )
            )
        return result

    for request in requests:
        if request.purpose != "sql_generation":
            result.errors.append(
                AssetDetailError(request, "invalid_purpose", "首版只允许 sql_generation 用途。")
            )
            continue
        if (request.asset_type, str(request.asset_id)) not in allowed_scope:
            result.errors.append(
                AssetDetailError(request, "asset_not_in_recall_scope", "资产不在本轮召回目录中。")
            )
            continue
        if request.detail_level not in VALID_DETAIL_LEVELS.get(request.asset_type, set()):
            result.errors.append(
                AssetDetailError(request, "invalid_detail_level", "资产类型不支持该详情级别。")
            )
            continue
        result.valid_requests.append(request)
    return result


class AssetDetailService:
    """从候选资产和原始 schema context 中水合受控资产详情。"""

    def __init__(
        self,
        *,
        candidate_assets: dict[str, Any],
        full_field_limit: int = 120,
        compact_field_limit: int = 300,
        field_search_default_top_k: int = 30,
        field_search_max_top_k: int = 50,
    ) -> None:
        self.candidate_assets = candidate_assets or {}
        self.context = dict(self.candidate_assets.get("context") or {})
        self.structured = dict(self.context.get("schema_structured") or {})
        self.assets = [
            asset for asset in list(self.candidate_assets.get("assets") or []) if isinstance(asset, dict)
        ]
        self.full_field_limit = full_field_limit
        self.compact_field_limit = compact_field_limit
        self.field_search_default_top_k = field_search_default_top_k
        self.field_search_max_top_k = field_search_max_top_k

    def get_detail(self, request: AssetDetailRequest) -> AssetDetailResult:
        if request.asset_type == "table" and request.detail_level == "full_schema":
            return self._table_full_schema(request)
        if request.asset_type == "table" and request.detail_level == "field_search":
            return self._table_field_search(request)
        return self._semantic_asset_detail(request)

    def _find_asset(self, request: AssetDetailRequest) -> dict[str, Any] | None:
        for asset in self.assets:
            if str(asset.get("asset_type")) == request.asset_type and str(asset.get("asset_id")) == str(request.asset_id):
                return asset
        return None

    def _table_fields(self, table_name: str) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        for raw in list(self.structured.get("fields") or []):
            if not isinstance(raw, dict):
                continue
            raw_table = str(raw.get("table_name") or raw.get("table") or "")
            if raw_table == table_name:
                fields.append(dict(raw))
        return fields

    def _table_payload(self, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(asset.get("metadata") or {})
        table_name = str(metadata.get("table_name") or asset.get("name") or asset.get("asset_id"))
        return {
            "name": table_name,
            "display_name": asset.get("display_name") or metadata.get("display_name") or table_name,
            "comment": metadata.get("comment") or metadata.get("description") or metadata.get("semantic"),
            "selected_by_dataset": True,
        }

    def _field_payload(self, field: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
        name = str(field.get("column_name") or field.get("name") or field.get("column") or "")
        payload = {
            "name": name,
            "data_type": field.get("data_type") or field.get("type"),
            "comment": field.get("column_comment") or field.get("comment") or field.get("description"),
            "is_time_candidate": _is_time_field(name, field),
            "is_filter_candidate": _is_filter_field(name, field),
            "is_join_candidate": _is_join_field(name, field),
        }
        if not compact:
            payload["business_desc"] = (
                field.get("business_desc")
                or field.get("semantic")
                or field.get("effective_desc")
                or field.get("description")
            )
        return payload

    def _table_full_schema(self, request: AssetDetailRequest) -> AssetDetailResult:
        asset = self._find_asset(request)
        if asset is None:
            return AssetDetailResult(request, "empty", {}, ["asset_missing"], "asset_missing")
        table_name = str((asset.get("metadata") or {}).get("table_name") or asset.get("name") or request.asset_id)
        fields = self._table_fields(table_name)
        field_count = len(fields)
        table = self._table_payload(asset)
        if field_count > self.compact_field_limit:
            return AssetDetailResult(
                request=request,
                coverage="too_large",
                risk_flags=["wide_table"],
                payload={
                    "asset_type": "table",
                    "asset_id": request.asset_id,
                    "detail_level": "full_schema",
                    "coverage": "too_large",
                    "table": table,
                    "field_count": field_count,
                    "returned_field_count": 0,
                    "fields": [],
                    "available_detail_requests": ["field_search"],
                    "suggested_next_requests": [
                        {
                            "asset_type": "table",
                            "asset_id": request.asset_id,
                            "detail_level": "field_search",
                            "query": table_name,
                            "top_k": self.field_search_default_top_k,
                            "purpose": "sql_generation",
                        }
                    ],
                },
            )
        compact = field_count > self.full_field_limit
        coverage = "full_compacted" if compact else "full"
        return AssetDetailResult(
            request=request,
            coverage=coverage,
            payload={
                "asset_type": "table",
                "asset_id": request.asset_id,
                "detail_level": "full_schema",
                "coverage": coverage,
                "table": table,
                "field_count": field_count,
                "returned_field_count": field_count,
                "fields": [self._field_payload(field, compact=compact) for field in fields],
                "risk_flags": [],
                "suggested_next_requests": [],
            },
        )

    def _table_field_search(self, request: AssetDetailRequest) -> AssetDetailResult:
        asset = self._find_asset(request)
        if asset is None:
            return AssetDetailResult(request, "empty", {}, ["asset_missing"], "asset_missing")
        table_name = str((asset.get("metadata") or {}).get("table_name") or asset.get("name") or request.asset_id)
        fields = self._table_fields(table_name)
        requested_top_k = request.top_k or self.field_search_default_top_k
        capped_top_k = min(max(1, requested_top_k), self.field_search_max_top_k)
        scored = [_score_field_for_search(request.query or "", field) for field in fields]
        scored.sort(key=lambda item: item["final_score"], reverse=True)
        returned = scored[:capped_top_k]
        coverage = "partial" if returned else "empty"
        return AssetDetailResult(
            request=request,
            coverage=coverage,
            payload={
                "coverage": coverage,
                "requested_top_k": requested_top_k,
                "capped_top_k": capped_top_k,
                "returned_count": len(returned),
                "total_matched_estimate": len(scored),
                "fields": returned,
                "suggested_next_queries": [] if returned else [table_name],
            },
        )

    def _semantic_asset_detail(self, request: AssetDetailRequest) -> AssetDetailResult:
        asset = self._find_asset(request)
        if asset is None:
            return AssetDetailResult(request, "empty", {}, ["asset_missing"], "asset_missing")
        metadata = dict(asset.get("metadata") or {})
        return AssetDetailResult(
            request=request,
            coverage="full",
            payload={
                "asset_type": request.asset_type,
                "asset_id": request.asset_id,
                "detail_level": request.detail_level,
                "coverage": "full",
                "name": asset.get("name"),
                "display_name": asset.get("display_name"),
                "metadata": metadata,
            },
        )


def _is_time_field(name: str, field: dict[str, Any]) -> bool:
    text = _norm(" ".join([name, str(field.get("column_comment") or ""), str(field.get("semantic") or "")]))
    return any(token in text for token in ("time", "date", "created", "updated", "时间", "日期"))


def _is_join_field(name: str, field: dict[str, Any]) -> bool:
    text = _norm(" ".join([name, str(field.get("column_comment") or "")]))
    return name.endswith("_id") or any(token in text for token in ("id", "编号", "编码"))


def _is_filter_field(name: str, field: dict[str, Any]) -> bool:
    text = _norm(" ".join([name, str(field.get("column_comment") or ""), str(field.get("semantic") or "")]))
    return _is_time_field(name, field) or any(token in text for token in ("status", "state", "type", "状态", "类型", "部门", "用户"))


def _score_field_for_search(query: str, field: dict[str, Any]) -> dict[str, Any]:
    name = str(field.get("column_name") or field.get("name") or field.get("column") or "")
    searchable = " ".join(
        str(value or "")
        for value in [
            name,
            field.get("column_comment"),
            field.get("comment"),
            field.get("business_desc"),
            field.get("semantic"),
            field.get("effective_desc"),
            field.get("description"),
        ]
    )
    factor, match, fragments = _match_factor(_norm(query), _norm(searchable))
    text_score = round(factor, 4)
    boost_reason = None
    boost = 0.0
    if _is_time_field(name, field):
        boost_reason = "time_field_candidate"
        boost = 0.54
    elif _is_join_field(name, field):
        boost_reason = "join_field_candidate"
        boost = 0.35
    elif _is_filter_field(name, field):
        boost_reason = "filter_field_candidate"
        boost = 0.3
    final_score = round(min(1.0, text_score + boost), 4)
    return {
        "name": name,
        "data_type": field.get("data_type") or field.get("type"),
        "comment": field.get("column_comment") or field.get("comment") or field.get("description"),
        "text_score": text_score,
        "final_score": final_score,
        "boosted": boost > 0,
        "boost_reason": boost_reason,
        "match": match,
        "fragments": fragments,
    }
```

- [ ] **Step 4: Export detail helpers**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from .asset_detail import (
    AssetDetailRequest,
    AssetDetailResult,
    AssetDetailService,
    validate_asset_detail_requests,
)
```

Keep existing exports in the file.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_asset_detail.py -q
```

Expected: `4 passed`.

Commit:

```bash
git add datalogue-api/app/services/subagent_planning/asset_detail.py datalogue-api/app/services/subagent_planning/__init__.py datalogue-api/tests/test_subagent_asset_detail.py
git commit -m "feat: add subagent asset detail service"
```

## Task 3: QueryPlan Audit Fields

**Files:**
- Modify: `datalogue-api/app/services/subagent_planning/contracts.py`
- Modify: `datalogue-api/tests/test_subagent_query_planner.py`

- [ ] **Step 1: Add failing contract tests**

Append to `datalogue-api/tests/test_subagent_query_planner.py`:

```python
from app.services.subagent_planning.contracts import QueryPlan, normalize_query_plan


def test_query_plan_serializes_asset_detail_audit_fields():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="clarify",
        confidence=0.4,
        planner_source="fallback",
        detail_rounds=3,
        attempted_detail_requests=[{"asset_type": "table", "asset_id": "wide_table"}],
        asset_detail_coverage={"wide_table": "too_large"},
        missing_context=["字段无法定位"],
        why_not_generate_sql="3 轮详情请求后仍缺少可用字段。",
        risk_flags=["wide_table"],
    )

    payload = plan.to_dict()

    assert payload["detail_rounds"] == 3
    assert payload["attempted_detail_requests"][0]["asset_id"] == "wide_table"
    assert payload["asset_detail_coverage"] == {"wide_table": "too_large"}
    assert payload["missing_context"] == ["字段无法定位"]
    assert payload["why_not_generate_sql"] == "3 轮详情请求后仍缺少可用字段。"
    assert payload["risk_flags"] == ["wide_table"]


def test_normalize_query_plan_accepts_asset_detail_audit_fields():
    plan = normalize_query_plan(
        {
            "query_type": "detail_query",
            "execution_strategy": "reject",
            "confidence": 0.2,
            "planner_source": "llm",
            "explanation": {"summary": "上下文不足"},
            "detail_rounds": 3,
            "attempted_detail_requests": [{"asset_type": "table", "asset_id": "wide_table"}],
            "asset_detail_coverage": {"wide_table": "too_large"},
            "missing_context": ["缺少时间字段"],
            "why_not_generate_sql": "无法确定时间字段。",
            "risk_flags": ["wide_table"],
        }
    )

    assert plan.detail_rounds == 3
    assert plan.missing_context == ["缺少时间字段"]
    assert plan.execution_strategy == "reject"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_query_plan_serializes_asset_detail_audit_fields tests/test_subagent_query_planner.py::test_normalize_query_plan_accepts_asset_detail_audit_fields -q
```

Expected: FAIL with `TypeError: QueryPlan.__init__() got an unexpected keyword argument 'detail_rounds'`.

- [ ] **Step 3: Extend `QueryPlan` dataclass and serialization**

Modify `datalogue-api/app/services/subagent_planning/contracts.py` in `QueryPlan`:

```python
    detail_rounds: int = 0
    attempted_detail_requests: list[dict[str, Any]] = field(default_factory=list)
    asset_detail_coverage: dict[str, Any] = field(default_factory=dict)
    missing_context: list[str] = field(default_factory=list)
    why_not_generate_sql: str | None = None
    risk_flags: list[str] = field(default_factory=list)
```

Modify `QueryPlan.to_dict()` to include:

```python
                "detail_rounds": self.detail_rounds,
                "attempted_detail_requests": self.attempted_detail_requests,
                "asset_detail_coverage": self.asset_detail_coverage,
                "missing_context": self.missing_context,
                "why_not_generate_sql": self.why_not_generate_sql,
                "risk_flags": self.risk_flags,
```

- [ ] **Step 4: Extend `normalize_query_plan()`**

In `datalogue-api/app/services/subagent_planning/contracts.py`, update the `QueryPlan(...)` constructor call inside `normalize_query_plan()` with:

```python
        detail_rounds=int(payload.get("detail_rounds") or 0),
        attempted_detail_requests=list(payload.get("attempted_detail_requests") or []),
        asset_detail_coverage=dict(payload.get("asset_detail_coverage") or {}),
        missing_context=[str(item) for item in list(payload.get("missing_context") or [])],
        why_not_generate_sql=payload.get("why_not_generate_sql"),
        risk_flags=[str(item) for item in list(payload.get("risk_flags") or [])],
```

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_query_plan_serializes_asset_detail_audit_fields tests/test_subagent_query_planner.py::test_normalize_query_plan_accepts_asset_detail_audit_fields -q
```

Expected: `2 passed`.

Commit:

```bash
git add datalogue-api/app/services/subagent_planning/contracts.py datalogue-api/tests/test_subagent_query_planner.py
git commit -m "feat: add query plan detail audit fields"
```

## Task 4: Planner Detail Loop

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/detail_loop.py`
- Modify: `datalogue-api/app/services/subagent_planning/planner.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`
- Test: `datalogue-api/tests/test_subagent_detail_loop.py`

- [ ] **Step 1: Write failing detail loop tests**

Create `datalogue-api/tests/test_subagent_detail_loop.py`:

```python
from app.services.subagent_planning.asset_detail import AssetDetailRequest
from app.services.subagent_planning.contracts import QueryPlan
from app.services.subagent_planning.detail_loop import PlannerDetailLoop, PlannerLoopResult


class ScriptedPlanner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


def _candidate_assets(field_count=4):
    fields = [
        {
            "table_name": "plan_task_daily_record",
            "column_name": f"field_{index}",
            "column_comment": f"字段 {index}",
            "data_type": "varchar",
        }
        for index in range(field_count)
    ]
    return {
        "dataset_id": 10,
        "question": "查询用户任务日志",
        "assets": [
            {
                "asset_type": "table",
                "asset_id": "plan_task_daily_record",
                "name": "plan_task_daily_record",
                "display_name": "任务日报",
                "confidence": 0.9,
                "metadata": {"table_name": "plan_task_daily_record", "comment": "任务日报"},
            }
        ],
        "context": {"schema_structured": {"fields": fields}},
    }


def test_detail_loop_hydrates_requested_asset_then_returns_final_plan():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "需要字段",
                    }
                ]
            },
            QueryPlan(
                query_type="detail_query",
                execution_strategy="query_graph",
                confidence=0.8,
                planner_source="llm",
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert isinstance(result, PlannerLoopResult)
    assert result.query_plan.execution_strategy == "query_graph"
    assert result.detail_rounds == 1
    assert result.asset_details[0].coverage == "full"
    assert len(planner.calls) == 2


def test_detail_loop_rejects_out_of_scope_request_and_retries_planner():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "not_recalled",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "越界请求",
                    }
                ]
            },
            QueryPlan(
                query_type="unsupported",
                execution_strategy="reject",
                confidence=0.2,
                planner_source="fallback",
                missing_context=["资产不在召回范围"],
                why_not_generate_sql="资产详情请求越界。",
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert result.query_plan.execution_strategy == "reject"
    assert result.warnings[0]["error_code"] == "asset_not_in_recall_scope"


def test_detail_loop_forces_reject_after_max_rounds_when_planner_keeps_requesting():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "第 1 轮",
                    }
                ]
            },
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "第 2 轮",
                    }
                ]
            },
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "第 3 轮",
                    }
                ]
            },
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert result.query_plan.execution_strategy == "reject"
    assert result.query_plan.fallback_reason == "max_detail_rounds_exceeded"
    assert result.query_plan.why_not_generate_sql == "达到 3 轮资产详情请求后仍未形成可执行计划。"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_detail_loop.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.subagent_planning.detail_loop`.

- [ ] **Step 3: Add planner response helpers in `planner.py`**

Modify `datalogue-api/app/services/subagent_planning/planner.py` to add:

```python
def parse_asset_detail_requests(payload: Any) -> list[AssetDetailRequest]:
    if not isinstance(payload, dict):
        return []
    requests = payload.get("asset_detail_requests") or []
    if not isinstance(requests, list):
        return []
    parsed: list[AssetDetailRequest] = []
    for item in requests:
        if isinstance(item, dict):
            parsed.append(AssetDetailRequest.from_dict(item))
    return parsed
```

Add import near existing subagent planning imports:

```python
from app.services.subagent_planning.asset_detail import AssetDetailRequest
```

- [ ] **Step 4: Implement `detail_loop.py`**

Create `datalogue-api/app/services/subagent_planning/detail_loop.py`:

```python
# ============================================================
# File Name   : detail_loop.py
# Description:
#   SubAgent Planner 受控资产详情循环。
#
# Responsibilities:
#   - 管理最多 3 轮 planner 资产详情请求。
#   - 校验请求只命中本轮轻量资产目录。
#   - 汇总详情结果、warning 和最终 QueryPlan。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .asset_catalog import build_allowed_asset_scope, project_lightweight_asset_catalog
from .asset_detail import (
    AssetDetailRequest,
    AssetDetailResult,
    AssetDetailService,
    validate_asset_detail_requests,
)
from .contracts import QueryPlan
from .planner import build_fallback_query_plan, parse_asset_detail_requests


PlannerCall = Callable[..., QueryPlan | dict[str, Any]]


@dataclass
class PlannerLoopResult:
    query_plan: QueryPlan
    lightweight_catalog: dict[str, Any]
    asset_details: list[AssetDetailResult] = field(default_factory=list)
    attempted_detail_requests: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    detail_rounds: int = 0
    sql_generation_context: dict[str, Any] = field(default_factory=dict)


class PlannerDetailLoop:
    """受控执行 planner 详情请求，不开放自由 tool loop。"""

    def __init__(
        self,
        *,
        max_rounds: int = 3,
        max_requests_per_round: int = 5,
        planner_call: PlannerCall,
        detail_service: AssetDetailService | None = None,
    ) -> None:
        self.max_rounds = max_rounds
        self.max_requests_per_round = max_requests_per_round
        self.planner_call = planner_call
        self.detail_service = detail_service

    def run(
        self,
        *,
        db: Any,
        question: str,
        routing: Any,
        candidate_assets: dict[str, Any],
        multiturn_context: Any = None,
        lead_agent_context: Any = None,
    ) -> PlannerLoopResult:
        catalog = project_lightweight_asset_catalog(candidate_assets)
        allowed_scope = build_allowed_asset_scope(catalog)
        detail_service = self.detail_service or AssetDetailService(candidate_assets=candidate_assets)
        asset_details: list[AssetDetailResult] = []
        attempted_requests: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        for round_index in range(1, self.max_rounds + 1):
            response = self.planner_call(
                db=db,
                question=question,
                routing=routing,
                lightweight_catalog=catalog,
                asset_details=[detail.to_dict() for detail in asset_details],
                previous_detail_requests=attempted_requests,
                warnings=warnings,
                multiturn_context=multiturn_context,
                lead_agent_context=lead_agent_context,
            )
            if isinstance(response, QueryPlan):
                _attach_detail_audit(response, round_index - 1, attempted_requests, asset_details, warnings)
                return PlannerLoopResult(
                    query_plan=response,
                    lightweight_catalog=catalog,
                    asset_details=asset_details,
                    attempted_detail_requests=attempted_requests,
                    warnings=warnings,
                    detail_rounds=round_index - 1,
                )

            requests = parse_asset_detail_requests(response)
            if not requests:
                fallback = build_fallback_query_plan(
                    question,
                    candidate_assets=catalog,
                    routing=routing,
                    fallback_reason="planner_detail_loop_invalid_response",
                )
                fallback.execution_strategy = "reject"
                fallback.query_type = "unsupported"
                fallback.missing_context = ["planner 未返回最终计划或资产详情请求。"]
                fallback.why_not_generate_sql = "planner detail loop 返回结构不可执行。"
                _attach_detail_audit(fallback, round_index - 1, attempted_requests, asset_details, warnings)
                return PlannerLoopResult(fallback, catalog, asset_details, attempted_requests, warnings, round_index - 1)

            attempted_requests.extend(request.to_dict() for request in requests)
            validation = validate_asset_detail_requests(
                requests,
                allowed_scope=allowed_scope,
                max_requests=self.max_requests_per_round,
            )
            warnings.extend(error.to_dict() for error in validation.errors)
            for request in validation.valid_requests:
                asset_details.append(detail_service.get_detail(request))

        fallback = QueryPlan(
            query_type="unsupported",
            execution_strategy="reject",
            confidence=0.2,
            fallback_reason="max_detail_rounds_exceeded",
            planner_source="fallback",
            explanation={"summary": "资产详情请求轮次已耗尽，仍未形成可执行计划。"},
            missing_context=["资产详情不足，planner 未在限定轮次内输出最终计划。"],
            why_not_generate_sql=f"达到 {self.max_rounds} 轮资产详情请求后仍未形成可执行计划。",
            risk_flags=["max_detail_rounds_exceeded"],
        )
        _attach_detail_audit(fallback, self.max_rounds, attempted_requests, asset_details, warnings)
        return PlannerLoopResult(fallback, catalog, asset_details, attempted_requests, warnings, self.max_rounds)


def _attach_detail_audit(
    plan: QueryPlan,
    detail_rounds: int,
    attempted_requests: list[dict[str, Any]],
    asset_details: list[AssetDetailResult],
    warnings: list[dict[str, Any]],
) -> None:
    plan.detail_rounds = detail_rounds
    plan.attempted_detail_requests = attempted_requests
    plan.asset_detail_coverage = {
        str(detail.request.asset_id): detail.coverage for detail in asset_details
    }
    existing_flags = list(plan.risk_flags or [])
    warning_flags = [str(warning.get("error_code")) for warning in warnings if warning.get("error_code")]
    detail_flags = [flag for detail in asset_details for flag in detail.risk_flags]
    plan.risk_flags = sorted(set(existing_flags + warning_flags + detail_flags))
```

- [ ] **Step 5: Export loop helpers**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from .detail_loop import PlannerDetailLoop, PlannerLoopResult
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_detail_loop.py tests/test_subagent_query_planner.py::test_query_plan_serializes_asset_detail_audit_fields -q
```

Expected: `4 passed`.

Commit:

```bash
git add datalogue-api/app/services/subagent_planning/detail_loop.py datalogue-api/app/services/subagent_planning/planner.py datalogue-api/app/services/subagent_planning/__init__.py datalogue-api/tests/test_subagent_detail_loop.py
git commit -m "feat: add subagent planner detail loop"
```

## Task 5: SQL Generation Context Assembly

**Files:**
- Create: `datalogue-api/app/services/subagent_planning/sql_context.py`
- Modify: `datalogue-api/app/services/subagent_planning/detail_loop.py`
- Modify: `datalogue-api/app/services/subagent_planning/__init__.py`
- Test: `datalogue-api/tests/test_subagent_detail_loop.py`

- [ ] **Step 1: Add failing test for SQL context assembly**

Append to `datalogue-api/tests/test_subagent_detail_loop.py`:

```python
def test_detail_loop_returns_sql_generation_context_without_embedding_details_in_query_plan():
    planner = ScriptedPlanner(
        [
            {
                "asset_detail_requests": [
                    {
                        "asset_type": "table",
                        "asset_id": "plan_task_daily_record",
                        "detail_level": "full_schema",
                        "purpose": "sql_generation",
                        "reason": "需要字段",
                    }
                ]
            },
            QueryPlan(
                query_type="detail_query",
                execution_strategy="query_graph",
                confidence=0.8,
                planner_source="llm",
                selected_assets=[],
            ),
        ]
    )
    loop = PlannerDetailLoop(max_rounds=3, max_requests_per_round=5, planner_call=planner)

    result = loop.run(
        db=None,
        question="查询用户任务日志",
        routing={"dataset_id": 10},
        candidate_assets=_candidate_assets(),
    )

    assert result.sql_generation_context["table_schemas"][0]["asset_id"] == "plan_task_daily_record"
    assert result.sql_generation_context["coverage"]["plan_task_daily_record"] == "full"
    assert "table_schemas" not in result.query_plan.to_dict()
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_detail_loop.py::test_detail_loop_returns_sql_generation_context_without_embedding_details_in_query_plan -q
```

Expected: FAIL because `sql_generation_context` is `{}`.

- [ ] **Step 3: Implement `sql_context.py`**

Create `datalogue-api/app/services/subagent_planning/sql_context.py`:

```python
# ============================================================
# File Name   : sql_context.py
# Description:
#   SubAgent SQL 生成上下文组装器。
#
# Responsibilities:
#   - 将 planner 选用资产和水合详情整理成下游 SQL/DSL 节点可消费的上下文。
#   - 避免完整字段 schema 混入 QueryPlan、SSE final payload 或跨轮状态。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from typing import Any

from .asset_detail import AssetDetailResult
from .contracts import QueryPlan


def build_sql_generation_context(
    *,
    query_plan: QueryPlan,
    asset_details: list[AssetDetailResult],
    lightweight_catalog: dict[str, Any],
) -> dict[str, Any]:
    table_schemas: list[dict[str, Any]] = []
    field_search_results: list[dict[str, Any]] = []
    metric_definitions: list[dict[str, Any]] = []
    dimension_definitions: list[dict[str, Any]] = []
    blueprint_references: list[dict[str, Any]] = []
    coverage: dict[str, str] = {}
    risk_flags: set[str] = set()

    for detail in asset_details:
        asset_id = str(detail.request.asset_id)
        coverage[asset_id] = detail.coverage
        risk_flags.update(detail.risk_flags)
        payload = dict(detail.payload or {})
        payload["asset_id"] = asset_id
        if detail.request.asset_type == "table" and detail.request.detail_level == "full_schema":
            table_schemas.append(payload)
        elif detail.request.asset_type == "table" and detail.request.detail_level == "field_search":
            field_search_results.append(payload)
        elif detail.request.asset_type == "metric":
            metric_definitions.append(payload)
        elif detail.request.asset_type == "dimension":
            dimension_definitions.append(payload)
        elif detail.request.asset_type == "blueprint":
            blueprint_references.append(payload)

    summary = dict((lightweight_catalog or {}).get("summary") or {})
    return {
        "selected_assets": [asset.to_dict() for asset in query_plan.selected_assets],
        "reference_assets": [asset.to_dict() for asset in query_plan.reference_assets],
        "table_schemas": table_schemas,
        "field_search_results": field_search_results,
        "metric_definitions": metric_definitions,
        "dimension_definitions": dimension_definitions,
        "blueprint_references": blueprint_references,
        "coverage": coverage,
        "risk_flags": sorted(risk_flags),
        "schema_version": summary.get("schema_version"),
        "manifest_version": summary.get("manifest_version"),
    }
```

- [ ] **Step 4: Wire SQL context into detail loop result**

Modify `datalogue-api/app/services/subagent_planning/detail_loop.py`:

Add import:

```python
from .sql_context import build_sql_generation_context
```

Before returning any final `PlannerLoopResult` with a `QueryPlan`, build:

```python
sql_generation_context = build_sql_generation_context(
    query_plan=response,
    asset_details=asset_details,
    lightweight_catalog=catalog,
)
```

Set `sql_generation_context=sql_generation_context` in the returned `PlannerLoopResult`.

For fallback plans, also build SQL context with the fallback plan and current asset details.

- [ ] **Step 5: Export SQL context helper**

Modify `datalogue-api/app/services/subagent_planning/__init__.py`:

```python
from .sql_context import build_sql_generation_context
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_detail_loop.py -q
```

Expected: `4 passed`.

Commit:

```bash
git add datalogue-api/app/services/subagent_planning/sql_context.py datalogue-api/app/services/subagent_planning/detail_loop.py datalogue-api/app/services/subagent_planning/__init__.py datalogue-api/tests/test_subagent_detail_loop.py
git commit -m "feat: build subagent sql generation context"
```

## Task 6: Feature Flag and Runtime Wiring

**Files:**
- Modify: `datalogue-api/app/core/config.py`
- Modify: `datalogue-api/app/services/dataset_subagent.py`
- Modify: `datalogue-api/tests/test_subagent_run.py`

- [ ] **Step 1: Add failing runtime tests**

Append to `datalogue-api/tests/test_subagent_run.py`:

```python
import pytest

from app.services.subagent_planning.contracts import QueryPlan


@pytest.mark.asyncio
async def test_dataset_subagent_uses_detail_loop_when_enabled(monkeypatch):
    from app.services import dataset_subagent as module
    from app.services.subagent_planning.detail_loop import PlannerLoopResult

    async_events = []

    class FakeLoop:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return PlannerLoopResult(
                query_plan=QueryPlan(
                    query_type="detail_query",
                    execution_strategy="clarify",
                    confidence=0.4,
                    planner_source="fallback",
                    clarification={"message": "需要补充信息"},
                ),
                lightweight_catalog={"assets": []},
                detail_rounds=1,
                warnings=[],
                sql_generation_context={"coverage": {}},
            )

    monkeypatch.setattr(module, "SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED", True, raising=False)
    monkeypatch.setattr(module, "PlannerDetailLoop", FakeLoop)
    monkeypatch.setattr(module, "recall_candidate_assets", lambda *args, **kwargs: {"assets": [], "context": {}})

    subagent = DatasetSubAgent(db=None)
    request = _request()

    async for event in subagent.run(request, trace_context=None, graph=None):
        async_events.append(event)

    assert any(event.event_type == "asset_detail" for event in async_events)
    assert async_events[-1].payload["final_state"]["sql_generation_context"] == {"coverage": {}}
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py::test_dataset_subagent_uses_detail_loop_when_enabled -q
```

Expected: FAIL because `SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED` and runtime wiring do not exist.

- [ ] **Step 3: Add settings**

Modify `datalogue-api/app/core/config.py` in `Settings`:

```python
    SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED: bool = False
    SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS: int = 3
    SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND: int = 5
    SUBAGENT_PLANNER_FIELD_SEARCH_DEFAULT_TOP_K: int = 30
    SUBAGENT_PLANNER_FIELD_SEARCH_MAX_TOP_K: int = 50
    SUBAGENT_PLANNER_TABLE_FULL_FIELD_LIMIT: int = 120
    SUBAGENT_PLANNER_TABLE_COMPACT_FIELD_LIMIT: int = 300
```

- [ ] **Step 4: Wire detail loop in `DatasetSubAgent.run()`**

Modify `datalogue-api/app/services/dataset_subagent.py` imports:

```python
from app.core.config import get_settings
from app.services.subagent_planning.detail_loop import PlannerDetailLoop
```

Inside `run()`, after `public_candidate_assets` is built and before existing `plan_query(...)`, add a gated branch:

```python
        settings = get_settings()
        if settings.SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED:
            loop = PlannerDetailLoop(
                max_rounds=settings.SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS,
                max_requests_per_round=settings.SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND,
                planner_call=plan_query_with_detail_context,
            )
            loop_result = loop.run(
                db=self.db,
                question=question,
                routing=routing,
                candidate_assets=candidate_assets,
                multiturn_context=multiturn_context,
                lead_agent_context=request.lead_agent_context,
            )
            query_plan = loop_result.query_plan
            query_plan_payload = query_plan.to_dict()
            yield SubAgentEvent(
                event_type="asset_detail",
                payload={
                    "node": "asset_detail",
                    "display_name": "subagent.asset_detail",
                    "status": "done",
                    "detail_rounds": loop_result.detail_rounds,
                    "requested_count": len(loop_result.attempted_detail_requests),
                    "coverage": query_plan.asset_detail_coverage,
                    "risk_flags": query_plan.risk_flags,
                    "warnings": loop_result.warnings,
                },
            )
            yield SubAgentEvent(
                event_type="query_plan",
                payload={
                    "node": "query_plan",
                    "display_name": "subagent.query_plan",
                    "status": "done",
                    "query_plan": query_plan_payload,
                },
            )
            if query_plan.execution_strategy in {"clarify", "reject"}:
                result = build_clarify_result(query_plan) if query_plan.execution_strategy == "clarify" else build_reject_result(query_plan)
                final_state = dict(result.final_state)
                final_state["candidate_assets"] = public_candidate_assets
                final_state["sql_generation_context"] = loop_result.sql_generation_context
                yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
                return
```

For executable strategies, ensure `_dsa_build_query_graph_state(...)` receives `sql_generation_context`. Add after `query_graph_state` is built:

```python
        query_graph_state["sql_generation_context"] = loop_result.sql_generation_context if settings.SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED else {}
```

- [ ] **Step 5: Add planner callable wrapper**

In `datalogue-api/app/services/subagent_planning/planner.py`, add:

```python
def plan_query_with_detail_context(
    *,
    db: Any,
    question: str,
    routing: Any,
    lightweight_catalog: dict[str, Any],
    asset_details: list[dict[str, Any]],
    previous_detail_requests: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    multiturn_context: Any = None,
    lead_agent_context: Any = None,
) -> QueryPlan | dict[str, Any]:
    return plan_query(
        db=db,
        question=question,
        routing=routing,
        candidate_assets=lightweight_catalog,
        multiturn_context={
            "summary": multiturn_context,
            "asset_details": asset_details,
            "previous_detail_requests": previous_detail_requests,
            "warnings": warnings,
        },
        lead_agent_context=lead_agent_context,
    )
```

Import this wrapper in `dataset_subagent.py`.

- [ ] **Step 6: Run runtime tests and commit**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py::test_dataset_subagent_uses_detail_loop_when_enabled tests/test_subagent_detail_loop.py -q
```

Expected: all selected tests pass.

Commit:

```bash
git add datalogue-api/app/core/config.py datalogue-api/app/services/dataset_subagent.py datalogue-api/app/services/subagent_planning/planner.py datalogue-api/tests/test_subagent_run.py
git commit -m "feat: gate subagent planner detail loop"
```

## Task 7: Planner Prompt and Safety Rules

**Files:**
- Modify: `datalogue-api/app/services/subagent_planning/planner.py`
- Modify: `datalogue-api/tests/test_subagent_query_planner.py`

- [ ] **Step 1: Add prompt tests**

Append to `datalogue-api/tests/test_subagent_query_planner.py`:

```python
from app.services.subagent_planning.planner import _planner_system_prompt


def test_planner_system_prompt_includes_asset_detail_loop_rules():
    prompt = _planner_system_prompt()

    assert "asset_detail_requests" in prompt
    assert "最多 3 轮" in prompt
    assert "不允许硬生成 SQL" in prompt
    assert "目录中的资产" in prompt
```

- [ ] **Step 2: Run prompt test and verify it fails**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_planner_system_prompt_includes_asset_detail_loop_rules -q
```

Expected: FAIL because the prompt does not mention `asset_detail_requests`.

- [ ] **Step 3: Update planner system prompt**

Modify `_planner_system_prompt()` in `datalogue-api/app/services/subagent_planning/planner.py` to add these lines to the joined list:

```python
            "当候选资产目录不足以生成可靠 SQL 时，可以输出 asset_detail_requests，请求目录中的资产详情。",
            "asset_detail_requests 只能请求本轮候选资产目录中的 metric、dimension、table、blueprint。",
            "表详情优先请求 full_schema；如果返回 too_large，再使用 field_search 自然语言搜索字段。",
            "资产详情最多 3 轮；3 轮后仍缺上下文时，不允许硬生成 SQL，必须输出 clarify 或 reject。",
            "如果无法确定时间字段、join 字段、指标口径或业务过滤条件，应在 missing_context 和 why_not_generate_sql 中说明原因。",
```

- [ ] **Step 4: Run prompt and planner tests**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_query_planner.py::test_planner_system_prompt_includes_asset_detail_loop_rules tests/test_subagent_query_planner.py::test_normalize_query_plan_accepts_asset_detail_audit_fields -q
```

Expected: `2 passed`.

Commit:

```bash
git add datalogue-api/app/services/subagent_planning/planner.py datalogue-api/tests/test_subagent_query_planner.py
git commit -m "docs: teach subagent planner detail request rules"
```

## Task 8: Regression Verification and Project Memory

**Files:**
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run Python compile checks**

Run:

```bash
cd datalogue-api && .venv/bin/python -m py_compile app/services/subagent_planning/asset_catalog.py app/services/subagent_planning/asset_detail.py app/services/subagent_planning/detail_loop.py app/services/subagent_planning/sql_context.py app/services/subagent_planning/contracts.py app/services/subagent_planning/planner.py app/services/dataset_subagent.py app/core/config.py
```

Expected: command exits with code 0.

- [ ] **Step 2: Run focused backend test suite**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_asset_catalog.py tests/test_subagent_asset_detail.py tests/test_subagent_detail_loop.py tests/test_subagent_query_planner.py tests/test_subagent_run.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Verify default-off behavior against existing planner path**

Run:

```bash
cd datalogue-api && SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED=false .venv/bin/python -m pytest tests/test_subagent_query_planner.py tests/test_subagent_run.py -q
```

Expected: all selected tests pass, confirming the old path remains active by default.

- [ ] **Step 4: Add project memory entry**

Append this entry to `.codex/project-memory.md` with the current completion time:

```markdown
### 2026-06-17 23:30 · SubAgent Planner 资产详情受控循环

- 涉及文件：`datalogue-api/app/services/subagent_planning/asset_catalog.py`、`datalogue-api/app/services/subagent_planning/asset_detail.py`、`datalogue-api/app/services/subagent_planning/detail_loop.py`、`datalogue-api/app/services/subagent_planning/sql_context.py`、`datalogue-api/app/services/subagent_planning/contracts.py`、`datalogue-api/app/services/subagent_planning/planner.py`、`datalogue-api/app/services/dataset_subagent.py`、`datalogue-api/app/core/config.py`、相关测试文件。
- 关键改动：新增默认关闭的 SubAgent planner 资产详情循环，首轮只给轻量资产目录，planner 最多 3 轮请求目录内资产详情；普通表返回整表 schema，超宽表返回 `coverage=too_large` 并通过自然语言 `field_search` 补齐字段；字段搜索默认 `top_k=30`、最大 50，关键字段 boost 必须带原因；3 轮后仍缺上下文时只能 `clarify/reject`，不允许硬生成 SQL。
- 验证方式：执行 `cd datalogue-api && .venv/bin/python -m py_compile app/services/subagent_planning/asset_catalog.py app/services/subagent_planning/asset_detail.py app/services/subagent_planning/detail_loop.py app/services/subagent_planning/sql_context.py app/services/subagent_planning/contracts.py app/services/subagent_planning/planner.py app/services/dataset_subagent.py app/core/config.py`，通过；执行 `cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_asset_catalog.py tests/test_subagent_asset_detail.py tests/test_subagent_detail_loop.py tests/test_subagent_query_planner.py tests/test_subagent_run.py -q`，通过。
- 残留风险：字段自然语言搜索仍需要真实问数样例评估质量；首版不做字段分页和字段分组；LeadAgent 侧仍保持现有渐进式资产注入。
```

- [ ] **Step 5: Commit verification record**

Run:

```bash
git add .codex/project-memory.md
git commit -m "docs: record subagent planner detail loop"
```

## Self-Review

- Spec coverage:
  - Lightweight catalog: Task 1.
  - Detail request validation and in-scope-only rule: Task 2 and Task 4.
  - Table full schema and wide-table `too_large`: Task 2.
  - Natural-language `field_search` with `top_k=30` and max `50`: Task 2.
  - Explainable boost: Task 2.
  - 3-round planner loop and no hard SQL generation after exhaustion: Task 4.
  - QueryPlan audit fields: Task 3.
  - `sql_generation_context`: Task 5.
  - Runtime feature flag and default-off behavior: Task 6 and Task 8.
  - Prompt safety rules: Task 7.
  - Observability summary event: Task 6.
  - Project memory: Task 8.

- Placeholder scan:
  - The plan contains no unresolved placeholders or unspecified implementation steps.
  - Each code step includes concrete paths, snippets, commands, and expected outcomes.

- Type consistency:
  - `AssetDetailRequest`, `AssetDetailResult`, `PlannerDetailLoop`, `PlannerLoopResult`, and `build_sql_generation_context` are introduced before later tasks use them.
  - `QueryPlan` audit fields match the names used by detail loop and SQL context tasks.
  - Feature flag names match the settings used in runtime wiring.
