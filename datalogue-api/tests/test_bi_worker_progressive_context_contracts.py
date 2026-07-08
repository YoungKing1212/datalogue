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
                "primary_entity": {
                    "asset_ref": "asset:work_log",
                    "alias": "log",
                    "role": "fact_or_primary",
                },
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
                    "target": {
                        "asset_ref": "asset:employee.name",
                        "alias": "emp",
                        "field": "employee_name",
                    },
                    "operator": "=",
                    "value": "杨凯",
                    "reason": "用户指定人员",
                }
            ],
            "selects": [
                {
                    "target": {
                        "asset_ref": "asset:work_log.content",
                        "alias": "log",
                        "field": "log_content",
                    },
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
                    "primary_entity": {
                        "asset_ref": "asset:employee",
                        "alias": "emp",
                        "role": "primary",
                    },
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
            "missing_context": [
                {"type": "alternative_lookup_relation", "focus": "department lookup"}
            ],
        }
    )

    payload = request.model_dump()
    assert "select " not in str(payload).lower()
    assert "relation " not in str(payload).lower()


def test_repair_request_rejects_raw_database_error_fragments():
    with pytest.raises(ValidationError):
        RepairRequest.model_validate(
            {
                "repair_status": "needs_plan_revision",
                "failure_stage": "execute",
                "failure_class": "table_not_found",
                "safe_reason": "SELECT * FROM missing_table",
                "recommended_action": "request_schema_slice",
                "missing_context": [],
            }
        )


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


# ---- FieldTarget asset_ref pattern + normalized_field_ref (4 层修复覆盖) ----


@pytest.mark.parametrize(
    "asset_ref",
    [
        "table:pm_tenant.plan_task_daily_record",
        "table:pm_tenant.plan_task_daily_record.rzrq",
        "asset:pm_tenant.plan_task_daily_record",
        "field:pm_tenant.plan_task_daily_record.rzrq",
    ],
)
def test_field_target_accepts_full_field_ref(asset_ref):
    """asset_ref 白名单前缀 + `.` 分隔路径应全部通过。"""
    from app.agentscope_service.bi_worker_contracts import FieldTarget

    target = FieldTarget(asset_ref=asset_ref, alias="main", field="rzrq")
    assert target.asset_ref == asset_ref


@pytest.mark.parametrize(
    "asset_ref",
    [
        "asset:primary",  # 冒号后无 "."
        "log.rzrq",  # 无前缀冒号
        "rzrq",  # 纯字段
        "invalid:pm_tenant.t",  # 前缀非白名单
    ],
)
def test_field_target_rejects_bad_formats(asset_ref):
    """非白名单前缀或缺少 "." 分隔路径的 asset_ref 应被 pydantic 拒绝。"""
    from app.agentscope_service.bi_worker_contracts import FieldTarget

    with pytest.raises(ValidationError):
        FieldTarget(asset_ref=asset_ref, alias="main", field="rzrq")


def test_normalized_field_ref_from_table_ref():
    """表级 ref + field 应组合为字段级 ref,供 L4 命中 field_refs。"""
    from app.agentscope_service.bi_worker_contracts import FieldTarget

    target = FieldTarget(asset_ref="table:pm_tenant.log", alias="main", field="rzrq")
    assert target.normalized_field_ref == "table:pm_tenant.log.rzrq"


def test_normalized_field_ref_from_field_ref():
    """已是字段级 ref 原样返回,避免重复追加 field 段。"""
    from app.agentscope_service.bi_worker_contracts import FieldTarget

    target = FieldTarget(asset_ref="table:pm_tenant.log.rzrq", alias="main", field="rzrq")
    assert target.normalized_field_ref == "table:pm_tenant.log.rzrq"


def test_field_not_found_recommended_action_covers_new_symptoms():
    """FIELD_NOT_FOUND 引导应覆盖 table: 规范格式 + context_state/field_refs 合并。"""
    from app.agentscope_service.bi_worker_contracts import FAILURE_DIAGNOSIS_MAP

    action = FAILURE_DIAGNOSIS_MAP["FIELD_NOT_FOUND"]["recommended_action"]
    assert "table:" in action
    assert "context_state_patch" in action or "field_refs" in action
