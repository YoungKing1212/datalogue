# ============================================================
# File Name   : test_bi_worker_progressive_context_contracts.py
# Description:
#   BI Worker 渐进式上下文契约的单元测试。
#
# Responsibilities:
#   - 验证查询计划、上下文缺口、修复请求和安全结果 payload 的边界。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
    BIWorkerQueryResult,
    QuerySupportValidation,
    RepairRequest,
)


def test_query_plan_accepts_data_graph_and_relationship_refs() -> None:
    plan = BIWorkerQueryPlan(
        intent="detail_query",
        entities=[
            {
                "entity_ref": "orders",
                "display_name": "订单",
                "role": "fact",
                "table_ref": "table:orders",
            },
            {
                "entity_ref": "customers",
                "display_name": "客户",
                "role": "dimension",
                "table_ref": "table:customers",
            },
        ],
        data_graph={
            "nodes": [
                {"entity_ref": "orders", "table_ref": "table:orders"},
                {"entity_ref": "customers", "table_ref": "table:customers"},
            ],
            "relationships": [
                {
                    "relationship_ref": "rel:orders.customer_id=customers.id",
                    "from_entity_ref": "orders",
                    "to_entity_ref": "customers",
                    "join_type": "left",
                    "description": "订单归属客户",
                }
            ],
        },
        selects=[
            {
                "target": {"entity_ref": "customers", "field_ref": "field:customers.name"},
                "alias": "客户名称",
            }
        ],
        filters=[],
        metrics=[],
        orderings=[],
        join_requirements=[
            {
                "relationship_ref": "rel:orders.customer_id=customers.id",
                "join_type": "left",
                "required": True,
            }
        ],
        result_shape={"kind": "table", "limit": 100},
    )

    assert plan.data_graph.relationships[0].relationship_ref == "rel:orders.customer_id=customers.id"
    assert plan.join_requirements[0].relationship_ref == "rel:orders.customer_id=customers.id"


def test_query_plan_rejects_free_join_conditions_and_empty_relationship_ref() -> None:
    base_plan = {
        "intent": "detail_query",
        "entities": [{"entity_ref": "orders", "display_name": "订单", "role": "fact"}],
        "data_graph": {"nodes": [{"entity_ref": "orders"}], "relationships": []},
        "selects": [{"target": {"field_ref": "field:orders.id"}}],
        "filters": [],
        "metrics": [],
        "orderings": [],
        "result_shape": {"kind": "table"},
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BIWorkerQueryPlan(
            **base_plan,
            join_requirements=[
                {
                    "relationship_ref": "rel:orders.customer_id=customers.id",
                    "join_type": "inner",
                    "raw_condition": "orders.customer_id = customers.id",
                }
            ],
        )

    with pytest.raises(ValidationError, match="at least 1 character"):
        BIWorkerQueryPlan(
            **base_plan,
            join_requirements=[{"relationship_ref": "", "join_type": "inner"}],
        )


def test_query_support_validation_expresses_lookup_dependency_missing_context() -> None:
    validation = QuerySupportValidation(
        status="needs_more_context",
        missing_context=[
            {
                "context_level": "L2_schema_slice",
                "dependency_type": "lookup_dependency",
                "entity_ref": "orders",
                "field_ref": "field:orders.customer_id",
                "reason": "需要客户维表字段确认展示名称。",
            }
        ],
        safe_reason="需要补充客户维表字段映射。",
    )

    assert validation.status == "needs_more_context"
    assert validation.missing_context[0].dependency_type == "lookup_dependency"


@pytest.mark.parametrize(
    "unsafe_reason",
    [
        "select *",
        " from orders",
        " where id = 1",
        "relation orders does not exist",
        "table orders missing",
        "column customer_id missing",
    ],
)
def test_repair_request_safe_reason_rejects_sql_and_database_error_fragments(unsafe_reason: str) -> None:
    with pytest.raises(ValidationError, match="safe_reason"):
        RepairRequest(
            status="needs_plan_revision",
            failure_stage="execute",
            safe_reason=unsafe_reason,
        )


def test_query_result_tool_payload_is_safe_artifact_card_without_sql_or_raw_rows() -> None:
    result = BIWorkerQueryResult(
        answer_summary="查询已完成，共 3 行、2 列。",
        artifact_ref="artifact:result-1",
        checkpoint_ref="checkpoint:abc",
        row_count=3,
        column_count=2,
    )

    payload = result.to_tool_payload()

    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["summary"] == "查询已完成，共 3 行、2 列。"
    assert payload["result_ref"] == "artifact:result-1"
    assert payload["artifact_card"] == {
        "artifact_type": "bi_answer",
        "title": "查询结果",
        "status": "completed",
        "summary_for_chat": "查询已完成，共 3 行、2 列。",
        "preview_payload": {"row_count": 3, "column_count": 2},
        "primary_ref": {
            "ref_id": "artifact:result-1",
            "ref_type": "result",
            "label": "查询结果",
        },
        "related_refs": [],
        "actions": [
            {
                "action_type": "view",
                "label": "查看详情",
                "ref": "artifact:result-1",
                "disabled": False,
            },
            {
                "action_type": "export",
                "label": "导出",
                "ref": "artifact:result-1",
                "disabled": True,
            },
        ],
    }
    assert "sql" not in payload
    assert "raw_rows" not in payload
    assert "sql" not in str(payload).lower()
    assert "raw_rows" not in str(payload)
