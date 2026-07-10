# ============================================================
# File Name   : test_bi_worker_progressive_context_e2e.py
# Description:
#   BI Worker 渐进式上下文端到端安全回归测试。
#
# Responsibilities:
#   - 验证 L5 Runtime 在上下文未披露资产或字段时停在 L4 安全校验层。
#   - 防止 SQL、raw rows、原始 query plan 或底层错误进入 Agent Team payload。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import pytest

from app.domains.bi.worker.contracts import (
    BIWorkerQueryPlan,
    FieldTarget,
    QueryDataGraph,
    QueryEntity,
    QuerySelect,
    ResultShape,
)
from app.domains.bi.worker.runtime import BIWorkerQueryRuntime
from app.domains.bi.worker.validator import ProgressiveContextState


def _undisclosed_field_target() -> FieldTarget:
    return FieldTarget(
        asset_ref="field:orders.secret_amount",
        alias="o",
        field="secret_amount",
    )


def _query_plan_with_undisclosed_asset_and_field() -> BIWorkerQueryPlan:
    return BIWorkerQueryPlan(
        intent="detail_query",
        question="查看订单敏感金额",
        result_shape=ResultShape(type="table", grain="订单", limit=20),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(
                asset_ref="asset:orders_private",
                alias="o",
                role="fact",
            ),
        ),
        selects=[
            QuerySelect(
                target=_undisclosed_field_target(),
                display_name="敏感金额",
            )
        ],
    )


@pytest.mark.asyncio
async def test_execute_query_plan_returns_l4_validation_when_plan_uses_undisclosed_context(
    db_session,
):
    runtime = BIWorkerQueryRuntime(db_session)
    context_state = ProgressiveContextState(
        asset_refs={"asset:orders_public"},
        field_refs={"field:orders_public.order_id"},
    )

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看订单敏感金额",
        query_plan=_query_plan_with_undisclosed_asset_and_field(),
        context_state=context_state,
        trace_id="trace-progressive-context-e2e",
    )

    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["status"] == "failed"
    assert "failure_type" in payload
    assert "safe_diagnosis" in payload
    serialized_payload = str(payload).lower()
    assert "select " not in serialized_payload
    assert "raw_rows" not in serialized_payload
    assert "query_plan" not in serialized_payload
    assert "raw_error" not in serialized_payload
