# ============================================================
# File Name   : test_repair_plan_contract.py
# Description:
#   RepairPlan v1 契约与工具校验测试。
#
# Responsibilities:
#   - 验证 RepairPlan schema 只把业务摘要暴露给用户可见面。
#   - 验证 SQL 失败分类和 RepairPlan 工具校验的 fail-closed 行为。
#   - 验证脱敏摘要可安全写入 artifact/query_artifact。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.repair_plan import (
    RepairAction,
    RepairFailureClass,
    RepairPlan,
    RepairStatus,
)
from app.services.repair_plan import (
    RepairPlanValidationError,
    classify_sql_failure,
    repair_attempt_limit,
    sanitize_repair_plan_for_artifact,
    validate_repair_plan,
)


def _field_plan(**overrides) -> RepairPlan:
    payload = {
        "dataset_id": 12,
        "failure_class": "FIELD_NOT_FOUND",
        "status": "plan_created",
        "business_summary": "字段口径不匹配，准备替换为工作日期口径。",
        "actions": [
            {
                "action_type": "replace_field",
                "business_summary": "将不存在的工作日志日期口径替换为已发布的工作日期口径。",
                "target": {"dataset_id": 12, "table": "work_log", "field": "bad_col"},
                "replacement": {"dataset_id": 12, "table": "work_log", "field": "work_date"},
                "confidence": 0.92,
            }
        ],
    }
    payload.update(overrides)
    return RepairPlan(**payload)


def test_repair_plan_schema_accepts_internal_action_but_summary_is_safe():
    plan = _field_plan()

    assert plan.schema_version == "repair_plan.v1"
    assert plan.failure_class == "FIELD_NOT_FOUND"
    assert plan.status == "plan_created"
    assert plan.actions[0].replacement["field"] == "work_date"
    visible = sanitize_repair_plan_for_artifact(
        plan,
        repair_plan_ref="artifact:repair-1",
        checkpoint_ref="checkpoint://conv-1-msg-2/repair",
        trace_id="trace-1",
        attempts=1,
    )
    rendered = json.dumps(visible, ensure_ascii=False).lower()
    assert visible["repair_plan_ref"] == "artifact:repair-1"
    assert visible["failure_class"] == "FIELD_NOT_FOUND"
    assert visible["business_summary"] == "字段口径不匹配，准备替换为工作日期口径。"
    assert "bad_col" not in rendered
    assert "work_log" not in rendered
    assert "replacement" not in rendered
    assert "select" not in rendered


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("column bad_col does not exist", "FIELD_NOT_FOUND"),
        ("no such column: bad_col", "FIELD_NOT_FOUND"),
        ("relation work_log_missing does not exist", "TABLE_NOT_FOUND"),
        ("no such table: work_log_missing", "TABLE_NOT_FOUND"),
        ("function date_trunc(text, integer) does not exist", "DIALECT_FUNCTION_UNSUPPORTED"),
        ("invalid input syntax for type date", "TYPE_ERROR"),
        ("permission denied for table work_log", "PERMISSION_DENIED"),
        ("connection refused", "CONNECTION_ERROR"),
        ("statement timeout", "TIMEOUT"),
        ("result size exceeds configured limit", "RESULT_TOO_LARGE"),
        ("SQL Guard 拦截：只允许只读 SELECT", "SECURITY_RISK"),
    ],
)
def test_classify_sql_failure(message, expected):
    assert classify_sql_failure(message) == expected
    assert classify_sql_failure(message) in RepairFailureClass.__args__


def test_repair_attempt_limit_matches_c1_policy():
    assert repair_attempt_limit("FIELD_NOT_FOUND") == 1
    assert repair_attempt_limit("TABLE_NOT_FOUND") == 1
    assert repair_attempt_limit("DIALECT_FUNCTION_UNSUPPORTED") == 2
    assert repair_attempt_limit("TYPE_ERROR") == 1
    assert repair_attempt_limit("PERMISSION_DENIED") == 0
    assert repair_attempt_limit("SECURITY_RISK") == 0


def test_validate_repair_plan_blocks_cross_dataset_raw_sql_and_attempt_overrun():
    plan = _field_plan()
    validated = validate_repair_plan(plan, dataset_id=12, attempt_count=0)
    assert validated.status == "plan_created"

    with pytest.raises(RepairPlanValidationError):
        validate_repair_plan(_field_plan(dataset_id=99), dataset_id=12, attempt_count=0)

    with pytest.raises(RepairPlanValidationError):
        validate_repair_plan(_field_plan(), dataset_id=12, attempt_count=1)

    with pytest.raises(ValidationError):
        RepairAction(
            action_type="replace_field",
            business_summary="执行这段 SQL: select * from work_log",
            target={"dataset_id": 12},
            replacement={"dataset_id": 12},
        )
