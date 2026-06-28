# ============================================================
# File Name   : repair_plan.py
# Description:
#   RepairPlan v1 编排与安全校验服务。
#
# Responsibilities:
#   - 将 SQL 执行失败归类为稳定 failure class。
#   - 按 C1 策略限制自动修复重跑次数。
#   - 校验 RepairPlan 不跨数据集、不携带可执行 SQL、不超出修复范围。
#   - 生成可写入 query_artifact / 用户可读 Artifact API 的脱敏摘要。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import re
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.schemas.repair_plan import RepairFailureClass, RepairPlan


class RepairPlanValidationError(ValueError):
    """RepairPlan 未通过 Tool 校验时 fail-closed。"""


_CLASSIFY_PATTERNS: list[tuple[re.Pattern[str], RepairFailureClass]] = [
    (re.compile(r"(column .* does not exist|no such column|unknown column)", re.I), "FIELD_NOT_FOUND"),
    (re.compile(r"(relation .* does not exist|no such table|table .* doesn't exist)", re.I), "TABLE_NOT_FOUND"),
    (re.compile(r"(function .* does not exist|no such function|dialect|syntax error near)", re.I), "DIALECT_FUNCTION_UNSUPPORTED"),
    (re.compile(r"(invalid input syntax|cannot cast|type mismatch|datatype mismatch)", re.I), "TYPE_ERROR"),
    (re.compile(r"(permission denied|access denied|not authorized|not authorised)", re.I), "PERMISSION_DENIED"),
    (re.compile(r"(connection refused|could not connect|connection reset|network is unreachable)", re.I), "CONNECTION_ERROR"),
    (re.compile(r"(statement timeout|query timeout|timed out|deadline exceeded)", re.I), "TIMEOUT"),
    (re.compile(r"(result size|too many rows|exceeds configured limit|payload too large)", re.I), "RESULT_TOO_LARGE"),
    (re.compile(r"(sql guard|readonly|read-only|unsafe sql|只允许只读|安全校验)", re.I), "SECURITY_RISK"),
]

_ATTEMPT_LIMITS: dict[RepairFailureClass, int] = {
    "FIELD_NOT_FOUND": 1,
    "TABLE_NOT_FOUND": 1,
    "DIALECT_FUNCTION_UNSUPPORTED": 2,
    "TYPE_ERROR": 1,
    "PERMISSION_DENIED": 0,
    "CONNECTION_ERROR": 0,
    "TIMEOUT": 0,
    "RESULT_TOO_LARGE": 0,
    "SECURITY_RISK": 0,
    "UNKNOWN": 0,
}

_FORBIDDEN_ACTION_KEYS = {
    "sql",
    "raw_sql",
    "direct_sql",
    "llm_sql",
    "query_sql",
    "raw_result",
    "schema",
    "schema_context",
    "control_plane",
}

_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)


def classify_sql_failure(error: Any) -> RepairFailureClass:
    """把数据库/Guard/执行异常归一为 C1 RepairFailureClass。"""

    text = str(error or "")
    for pattern, failure_class in _CLASSIFY_PATTERNS:
        if pattern.search(text):
            return failure_class
    return "UNKNOWN"


def repair_attempt_limit(failure_class: RepairFailureClass | str) -> int:
    """返回 C1 固定动态重跑次数，避免 LLM 决定重跑预算。"""

    return _ATTEMPT_LIMITS.get(str(failure_class), 0)


def _contains_forbidden_action_payload(value: Any, *, key_name: str = "") -> bool:
    key = key_name.lower()
    if key in _FORBIDDEN_ACTION_KEYS or "sql" in key:
        return True
    if isinstance(value, dict):
        return any(
            _contains_forbidden_action_payload(item, key_name=str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_action_payload(item, key_name=key_name) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return _SQL_TEXT_RE.search(value) is not None or any(
            token in lowered
            for token in ("raw_sql", "raw_result", "schema_context", "control_plane")
        )
    return False


def _assert_dataset_scope(value: dict[str, Any], *, dataset_id: int) -> None:
    scoped_dataset_id = value.get("dataset_id")
    if scoped_dataset_id is not None and int(scoped_dataset_id) != int(dataset_id):
        raise RepairPlanValidationError("repair plan action crosses dataset boundary")


def validate_repair_plan(
    plan: RepairPlan,
    *,
    dataset_id: int,
    attempt_count: int,
) -> RepairPlan:
    """Tool 层校验 RepairPlan；任何越界或超限都直接 fail-closed。"""

    if int(plan.dataset_id) != int(dataset_id):
        raise RepairPlanValidationError("repair plan dataset mismatch")
    limit = repair_attempt_limit(plan.failure_class)
    if attempt_count >= limit:
        raise RepairPlanValidationError("repair plan attempt limit exceeded")
    if not plan.actions:
        raise RepairPlanValidationError("repair plan has no actions")
    for action in plan.actions:
        # action 内部允许字段/表定位，但不能携带可执行 SQL 或完整 schema/raw result。
        payload = action.model_dump(mode="json")
        if _contains_forbidden_action_payload(payload):
            raise RepairPlanValidationError("repair plan action contains forbidden executable detail")
        _assert_dataset_scope(action.target, dataset_id=dataset_id)
        _assert_dataset_scope(action.replacement, dataset_id=dataset_id)
    return plan


def build_repair_plan_from_diagnosis(
    *,
    dataset_id: int,
    failure_class: RepairFailureClass,
    diagnosis: dict[str, Any],
    attempt_count: int,
) -> RepairPlan:
    """根据结构化诊断生成最小 RepairPlan；具体 SQL 仍由后续 Tool/Graph 重编译。"""

    action_type = {
        "FIELD_NOT_FOUND": "replace_field",
        "TABLE_NOT_FOUND": "replace_table",
        "DIALECT_FUNCTION_UNSUPPORTED": "replace_dialect_function",
        "TYPE_ERROR": "cast_type",
    }.get(failure_class, "diagnose_only")
    wrong_field = diagnosis.get("wrong_field") or diagnosis.get("missing_field")
    replacement_field = diagnosis.get("suggested_field") or diagnosis.get("replacement_field")
    target: dict[str, Any] = {"dataset_id": dataset_id}
    replacement: dict[str, Any] = {"dataset_id": dataset_id}
    if wrong_field:
        target["field"] = wrong_field
    if replacement_field:
        replacement["field"] = replacement_field
    plan = RepairPlan(
        dataset_id=dataset_id,
        failure_class=failure_class,
        status="plan_created",
        business_summary="查询执行失败已完成自动修复评估，准备按业务口径重新执行。",
        actions=[
            {
                "action_type": action_type,
                "business_summary": "按已发布的数据集口径生成安全修复动作。",
                "target": target,
                "replacement": replacement,
                "confidence": 0.8,
            }
        ],
        requires_user_confirmation=False,
        confidence=0.8,
        attempts=attempt_count + 1,
    )
    return validate_repair_plan(plan, dataset_id=dataset_id, attempt_count=attempt_count)


def sanitize_repair_plan_for_artifact(
    plan: RepairPlan,
    *,
    repair_plan_ref: str,
    checkpoint_ref: str | None = None,
    trace_id: str | None = None,
    attempts: int | None = None,
) -> dict[str, Any]:
    """生成 Artifact API 可返回的 RepairPlan 脱敏摘要，不包含字段级 patch 主体。"""

    safe: dict[str, Any] = {
        "schema_version": plan.schema_version,
        "failure_class": plan.failure_class,
        "status": plan.status,
        "business_summary": plan.business_summary,
        "attempts": plan.attempts if attempts is None else attempts,
        "requires_user_confirmation": plan.requires_user_confirmation,
        "repair_plan_ref": repair_plan_ref,
    }
    if checkpoint_ref:
        safe["checkpoint_ref"] = checkpoint_ref
    if trace_id:
        safe["trace_ref"] = f"trace:{trace_id}" if not str(trace_id).startswith("trace:") else trace_id
    return jsonable_encoder(safe)


def sanitize_repair_plan_artifact_payload(payload: Any) -> dict[str, Any]:
    """Artifact API 读取 repair_plan 时的兜底脱敏，兼容直接存入 dict 的场景。"""

    source = payload if isinstance(payload, dict) else {}
    allowed = {
        "schema_version",
        "failure_class",
        "status",
        "business_summary",
        "attempts",
        "requires_user_confirmation",
        "repair_plan_ref",
        "checkpoint_ref",
        "trace_ref",
    }
    return jsonable_encoder({key: source[key] for key in allowed if key in source})
