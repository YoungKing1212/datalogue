# ============================================================
# File Name   : last_success_task.py
# Description:
#   上一轮成功查询的最小跨轮承接快照。
#
# Responsibilities:
#   - 定义 last_success_task 的严格白名单 schema。
#   - 从本轮 QueryPlan/DSL 中抽取可跨轮复用的轻量引用。
#   - 校验跨轮任务是否仍可被下一轮安全继承。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.services.subagent_planning.contracts import (
    EXECUTION_STRATEGIES,
    PLANNER_SOURCES,
    QUERY_TYPES,
)
from app.utils.token import estimate_text_tokens

CAPSULE_VERSION = "last_success_task.v1"
DEFAULT_LAST_SUCCESS_TASK_MAX_TOKENS = 2000
_SQL_FROM_RE = re.compile(r"(?is)\bfrom\s+([`\"\[]?)(?P<table>[\w.]+)\1")


class CapsuleSizeExceededError(ValueError):
    """last_success_task 超过跨轮持久化预算。"""

    def __init__(self, estimated_tokens: int, max_tokens: int) -> None:
        super().__init__(
            f"last_success_task token budget exceeded: {estimated_tokens}>{max_tokens}"
        )
        self.estimated_tokens = estimated_tokens
        self.max_tokens = max_tokens


class FieldRef(BaseModel):
    """字段轻量引用，跨轮只保留定位和角色，不携带字段 metadata。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    table: str
    column: str
    role: Literal["dimension", "metric", "time", "filter", "id", "select_only"] = "select_only"
    alias: str | None = None


class JoinRef(BaseModel):
    """JOIN 拓扑的最小描述。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    left_table: str
    left_column: str
    right_table: str
    right_column: str
    join_type: Literal["INNER", "LEFT", "RIGHT", "FULL"] = "LEFT"
    purpose: str | None = None


class BlueprintHitRef(BaseModel):
    """Blueprint 命中引用，不保存 call_template/raw_sql/trigger_examples。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    asset_id: str | int
    name: str | None = None
    bound_parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class LastSuccessTask(BaseModel):
    """上一轮成功查询的最小承接快照。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    capsule_version: Literal["last_success_task.v1"] = CAPSULE_VERSION
    dataset_id: int | None = None
    schema_version: str = ""
    manifest_version: str = ""
    turn_index: int = 0

    question: str
    query_type: str
    execution_strategy: str | None = None
    planner_source: str | None = None
    blueprint_hit: BlueprintHitRef | None = None

    main_table: str | None = None
    selected_field_refs: list[FieldRef] = Field(default_factory=list)
    join_topology: list[JoinRef] = Field(default_factory=list)
    filters_applied: list[dict[str, Any]] = Field(default_factory=list)
    time_window: dict[str, Any] | None = None
    metrics_applied: list[dict[str, Any]] = Field(default_factory=list)

    sql_hash: str | None = None
    result_ref: str | None = None
    result_digest: dict[str, Any] = Field(default_factory=dict)
    report_id: str | None = None
    display_summary: str | None = None
    result_artifact: dict[str, Any] = Field(default_factory=dict)
    resolved_question: str | None = None

    @field_validator("query_type")
    @classmethod
    def _validate_query_type(cls, value: str) -> str:
        if value not in QUERY_TYPES:
            raise ValueError(f"query_type invalid: {value}")
        return value

    @field_validator("execution_strategy")
    @classmethod
    def _validate_execution_strategy(cls, value: str | None) -> str | None:
        if value and value not in EXECUTION_STRATEGIES:
            raise ValueError(f"execution_strategy invalid: {value}")
        return value

    @field_validator("planner_source")
    @classmethod
    def _validate_planner_source(cls, value: str | None) -> str | None:
        if value and value not in PLANNER_SOURCES:
            raise ValueError(f"planner_source invalid: {value}")
        return value

    def estimated_tokens(self) -> int:
        return estimate_text_tokens(self.model_dump_json(exclude_none=True))

    def ensure_size(self, *, max_tokens: int = DEFAULT_LAST_SUCCESS_TASK_MAX_TOKENS) -> None:
        estimated = self.estimated_tokens()
        if estimated > max_tokens:
            raise CapsuleSizeExceededError(estimated, max_tokens)

    def to_base_query_plan(self) -> dict[str, Any]:
        """转换成 T+1 prior context 可消费的最小 base_query_plan。"""

        join_hints = [
            {
                "left_table": item.left_table,
                "left_column": item.left_column,
                "right_table": item.right_table,
                "right_column": item.right_column,
                "purpose": item.purpose,
            }
            for item in self.join_topology
        ]
        return jsonable_encoder(
            {
                "query_type": self.query_type,
                "execution_strategy": self.execution_strategy,
                "planner_source": self.planner_source,
                "main_table": self.main_table,
                "selected_field_refs": self.selected_field_refs,
                "join_topology": self.join_topology,
                "filters_applied": self.filters_applied,
                "time_window": self.time_window,
                "metrics_applied": self.metrics_applied,
                "blueprint_hit": self.blueprint_hit,
                "result_ref": self.result_ref,
                "report_id": self.report_id,
                "display_summary": self.display_summary,
                "result_artifact": self.result_artifact,
                "debug": {
                    "selected_main_table": self.main_table,
                    "join_hints": join_hints,
                },
            }
        )


def minimal_result_digest(sql_result: dict[str, Any] | None) -> dict[str, Any]:
    """生成跨轮可保留的轻量结果摘要，不保存 sample rows。"""

    if not isinstance(sql_result, dict):
        return {"row_count": 0, "columns": []}
    rows = sql_result.get("rows") or []
    return {
        "row_count": int(sql_result.get("row_count") or len(rows)),
        "columns": jsonable_encoder(sql_result.get("columns") or []),
    }


def build_last_success_task(
    *,
    question: str,
    dataset_id: int | None,
    query_plan: dict[str, Any] | None,
    dsl: dict[str, Any] | None,
    sql: str | None,
    sql_result: dict[str, Any] | None,
    schema_version: str | None = None,
    manifest_version: str | None = None,
    turn_index: int | None = None,
    result_artifact: dict[str, Any] | None = None,
    max_tokens: int = DEFAULT_LAST_SUCCESS_TASK_MAX_TOKENS,
) -> dict[str, Any]:
    """从本轮最终状态抽取严格白名单的 last_success_task。"""

    plan = query_plan if isinstance(query_plan, dict) else {}
    dsl_payload = dsl if isinstance(dsl, dict) else {}
    selected_assets = [
        asset for asset in plan.get("selected_assets") or [] if isinstance(asset, dict)
    ]
    query_type = _resolve_query_type(plan, dsl_payload, selected_assets, sql_result)
    task = LastSuccessTask(
        dataset_id=dataset_id,
        schema_version=str(schema_version or ""),
        manifest_version=str(manifest_version or ""),
        turn_index=int(turn_index or 0),
        question=question,
        query_type=query_type,
        execution_strategy=plan.get("execution_strategy"),
        planner_source=plan.get("planner_source"),
        blueprint_hit=_extract_blueprint_hit(plan, selected_assets),
        main_table=_selected_main_table(plan, dsl_payload, selected_assets, sql),
        selected_field_refs=_extract_field_refs(selected_assets, dsl_payload),
        join_topology=_extract_join_topology(plan),
        filters_applied=_extract_list(dsl_payload, "filters", "where", "filter_clauses"),
        time_window=_extract_time_window(dsl_payload),
        metrics_applied=_extract_list(dsl_payload, "metrics", "metric_clauses"),
        sql_hash=_hash_sql(sql),
        result_digest=minimal_result_digest(sql_result),
        result_ref=_artifact_value(result_artifact, "result_ref"),
        report_id=_artifact_value(result_artifact, "report_id"),
        display_summary=_artifact_value(result_artifact, "display_summary"),
        result_artifact=_safe_artifact_metadata(result_artifact),
        resolved_question=question,
    )
    task.ensure_size(max_tokens=max_tokens)
    return task.model_dump(mode="json", exclude_none=True)


def evaluate_last_success_task(
    raw_task: dict[str, Any] | None,
    *,
    active_dataset_id: int | None,
    current_schema_version: str | None = None,
    current_manifest_version: str | None = None,
) -> tuple[LastSuccessTask | None, dict[str, Any]]:
    """判断 last_success_task 是否可安全继承。"""

    if not isinstance(raw_task, dict) or not raw_task:
        return None, {"status": "missing", "reason": "no_last_success_task"}
    if raw_task.get("capsule_version") != CAPSULE_VERSION:
        return None, {
            "status": "stale",
            "reason": "unsupported_capsule_version",
            "capsule_version": raw_task.get("capsule_version"),
        }
    try:
        task = LastSuccessTask.model_validate(raw_task)
    except ValidationError as exc:
        return None, {
            "status": "invalid",
            "reason": "validation_error",
            "error": str(exc),
        }
    if active_dataset_id is not None and task.dataset_id is not None:
        if int(task.dataset_id) != int(active_dataset_id):
            return None, {
                "status": "not_applicable",
                "reason": "dataset_mismatch",
                "dataset_id": task.dataset_id,
                "active_dataset_id": active_dataset_id,
            }
    if current_schema_version and task.schema_version:
        if str(task.schema_version) != str(current_schema_version):
            return None, {
                "status": "stale",
                "reason": "schema_version_mismatch",
                "capsule_schema_version": task.schema_version,
                "expected_schema_version": current_schema_version,
            }
    if current_manifest_version and task.manifest_version:
        if str(task.manifest_version) != str(current_manifest_version):
            return None, {
                "status": "stale",
                "reason": "manifest_version_mismatch",
                "capsule_manifest_version": task.manifest_version,
                "expected_manifest_version": current_manifest_version,
            }
    if not task_has_query_target(task):
        return None, {"status": "not_applicable", "reason": "no_query_target"}
    return task, {
        "status": "loaded",
        "reason": "last_success_task_matched",
        "dataset_id": task.dataset_id,
        "schema_version": task.schema_version,
        "manifest_version": task.manifest_version,
        "capsule_version": task.capsule_version,
        "result_ref": task.result_ref,
        "report_id": task.report_id,
        "display_summary": task.display_summary,
    }


def task_has_query_target(task: LastSuccessTask | dict[str, Any] | None) -> bool:
    """判断任务是否具备可继续查询的最小目标。"""

    if isinstance(task, LastSuccessTask):
        if task.query_type == "detail_query":
            return bool(task.selected_field_refs or task.main_table)
        return bool(task.metrics_applied or task.selected_field_refs or task.blueprint_hit)
    if not isinstance(task, dict):
        return False
    query_type = task.get("query_type")
    if query_type == "detail_query":
        return bool(
            task.get("selected_field_refs")
            or task.get("fields")
            or task.get("main_table")
            or task.get("query_plan")
            or task.get("dsl")
        )
    return bool(task.get("metrics_applied") or task.get("metrics") or task.get("blueprint_hit"))


def _hash_sql(sql: str | None) -> str | None:
    if not sql:
        return None
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _artifact_value(artifact: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(artifact, dict):
        return None
    value = artifact.get(key)
    return str(value) if value else None


def _safe_artifact_metadata(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    allowed_keys = {
        "version",
        "result_ref",
        "artifact_ref",
        "report_id",
        "cache_backend",
        "ttl_seconds",
        "expires_at",
        "complete",
        "completeness_reason",
        "display_summary",
        "row_count",
        "columns",
    }
    return {
        key: jsonable_encoder(value)
        for key, value in artifact.items()
        if key in allowed_keys and value is not None
    }


def _extract_list(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in jsonable_encoder(value) if isinstance(item, dict)]
    return []


def _extract_time_window(dsl: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("time_window", "time_range", "date_range"):
        value = dsl.get(key)
        if isinstance(value, dict):
            return jsonable_encoder(value)
    return None


def _selected_main_table(
    query_plan: dict[str, Any],
    dsl: dict[str, Any],
    selected_assets: list[dict[str, Any]],
    sql: str | None = None,
) -> str | None:
    debug = query_plan.get("debug") if isinstance(query_plan.get("debug"), dict) else {}
    value = (
        debug.get("selected_main_table")
        or query_plan.get("main_table")
        or dsl.get("main_table")
        or _infer_main_table(selected_assets)
        or _infer_main_table_from_sql(sql)
    )
    return str(value) if value else None


def _resolve_query_type(
    query_plan: dict[str, Any],
    dsl: dict[str, Any],
    selected_assets: list[dict[str, Any]],
    sql_result: dict[str, Any] | None,
) -> str:
    """从可观测产物保守推断 query_type，避免空值导致首轮任务写入失败。"""

    explicit = query_plan.get("query_type") or dsl.get("query_type")
    if explicit:
        return str(explicit)
    if query_plan.get("execution_strategy") == "blueprint_execute":
        return "blueprint_query"
    if _extract_list(dsl, "metrics", "metric_clauses"):
        return "metric_query"
    if any(asset.get("asset_type") == "metric" for asset in selected_assets):
        return "metric_query"
    if _extract_list(dsl, "fields", "field_clauses") or _result_has_columns(sql_result):
        return "detail_query"
    return "detail_query"


def _result_has_columns(sql_result: dict[str, Any] | None) -> bool:
    if not isinstance(sql_result, dict):
        return False
    columns = sql_result.get("columns") or []
    return isinstance(columns, list) and bool(columns)


def _infer_main_table_from_sql(sql: str | None) -> str | None:
    if not sql:
        return None
    match = _SQL_FROM_RE.search(sql)
    if not match:
        return None
    return match.group("table")


def _infer_main_table(selected_assets: list[dict[str, Any]]) -> str | None:
    for asset in selected_assets:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        if metadata.get("main_table_role") == "fact" and metadata.get("table_name"):
            return str(metadata.get("table_name"))
    for asset in selected_assets:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        if metadata.get("table_name"):
            return str(metadata.get("table_name"))
    return None


def _extract_field_refs(
    selected_assets: list[dict[str, Any]],
    dsl: dict[str, Any],
) -> list[FieldRef]:
    refs: list[FieldRef] = []
    seen: set[tuple[str, str, str]] = set()
    for asset in selected_assets:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        table = metadata.get("table_name") or metadata.get("table")
        column = metadata.get("column_name") or metadata.get("column")
        if not table or not column:
            continue
        role = _field_role(asset, metadata)
        key = (str(table), str(column), role)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            FieldRef(
                table=str(table),
                column=str(column),
                role=role,
                alias=asset.get("display_name") or asset.get("name"),
            )
        )
    if refs:
        return refs
    for field in dsl.get("fields") or []:
        if not isinstance(field, dict):
            continue
        table = field.get("table_name") or field.get("table")
        column = field.get("column_name") or field.get("name") or field.get("column")
        if table and column:
            refs.append(FieldRef(table=str(table), column=str(column), role="select_only"))
    return refs


def _field_role(asset: dict[str, Any], metadata: dict[str, Any]) -> str:
    asset_type = str(asset.get("asset_type") or "")
    if asset_type == "metric":
        return "metric"
    if asset_type == "dimension":
        return "dimension"
    semantic_role = str(
        metadata.get("user_semantic_role")
        or metadata.get("ai_semantic_role")
        or metadata.get("semantic_role")
        or ""
    ).lower()
    if semantic_role in {"time", "date", "datetime"}:
        return "time"
    if semantic_role in {"id", "identifier", "primary_key"}:
        return "id"
    return "select_only"


def _extract_join_topology(query_plan: dict[str, Any]) -> list[JoinRef]:
    debug = query_plan.get("debug") if isinstance(query_plan.get("debug"), dict) else {}
    hints = debug.get("join_hints") if isinstance(debug.get("join_hints"), list) else []
    joins: list[JoinRef] = []
    seen: set[tuple[str, str, str, str]] = set()
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        left_table = hint.get("left_table")
        left_column = hint.get("left_column") or hint.get("left_col")
        right_table = hint.get("right_table")
        right_column = hint.get("right_column") or hint.get("right_col")
        key = tuple(
            str(item or "") for item in (left_table, left_column, right_table, right_column)
        )
        if not all(key) or key in seen:
            continue
        seen.add(key)
        join_type = str(hint.get("join_type") or "LEFT").upper()
        if join_type not in {"INNER", "LEFT", "RIGHT", "FULL"}:
            join_type = "LEFT"
        joins.append(
            JoinRef(
                left_table=key[0],
                left_column=key[1],
                right_table=key[2],
                right_column=key[3],
                join_type=join_type,
                purpose=hint.get("purpose"),
            )
        )
    return joins


def _extract_blueprint_hit(
    query_plan: dict[str, Any],
    selected_assets: list[dict[str, Any]],
) -> BlueprintHitRef | None:
    if query_plan.get("execution_strategy") != "blueprint_execute":
        return None
    for asset in selected_assets:
        if asset.get("asset_type") != "blueprint":
            continue
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        asset_id = asset.get("asset_id") or metadata.get("id")
        if asset_id is None:
            continue
        return BlueprintHitRef(
            asset_id=asset_id,
            name=asset.get("display_name") or asset.get("name"),
            bound_parameters=asset.get("bound_parameters") or {},
        )
    return None
