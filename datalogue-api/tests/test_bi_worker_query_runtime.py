# ============================================================
# File Name   : test_bi_worker_query_runtime.py
# Description:
#   BI Worker L5 受控查询 Runtime 的单元测试。
#
# Responsibilities:
#   - 验证 L5 Runtime 先执行 L4 支持度校验，缺上下文时不触发查询执行。
#   - 验证执行失败时只返回安全 Repair Request，不泄露 SQL、原始行或数据库细节。
#   - 验证成功查询 payload 只携带 artifact 引用和用户可见摘要。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import pytest

from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
    BIWorkerQueryResult,
    FieldTarget,
    JoinRequirement,
    QueryDataGraph,
    QueryEntity,
    QueryFilter,
    QueryMetric,
    QueryOrdering,
    QuerySelect,
    ResultShape,
)
from app.agentscope_service.bi_worker_runtime import BIWorkerQueryRuntime
from app.agentscope_service.bi_worker_validator import ProgressiveContextState
from app.agentscope_service.dataset_query_executor import (
    execute_dataset_query_for_agent_team_direct_fallback,
)
from app.services.query_plan_compiler import compile_query_plan_to_sql


def _target(ref: str, field: str, alias: str = "o") -> FieldTarget:
    return FieldTarget(asset_ref=ref, alias=alias, field=field)


def _plan(*, relationship_ref: str = "relationship:orders.department") -> BIWorkerQueryPlan:
    return BIWorkerQueryPlan(
        intent="detail_query",
        question="查看订单所属部门和金额",
        result_shape=ResultShape(type="table", grain="订单", limit=50),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(asset_ref="asset:orders", alias="o", role="fact"),
            supporting_entities=[
                QueryEntity(asset_ref="asset:departments", alias="d", role="dimension"),
            ],
        ),
        join_requirements=[
            JoinRequirement(
                left_alias="o",
                right_alias="d",
                relationship_ref=relationship_ref,
                join_type="left",
                required=True,
                reason="补充订单归属部门",
            )
        ],
        filters=[
            QueryFilter(
                target=_target("field:orders.order_date", "order_date"),
                operator=">=",
                value="2026-01-01",
                reason="限定查询时间范围",
            )
        ],
        selects=[
            QuerySelect(
                target=_target("field:orders.order_id", "order_id"),
                display_name="订单号",
            ),
            QuerySelect(
                target=_target("field:departments.name", "name", alias="d"),
                display_name="部门名称",
            ),
        ],
        metrics=[
            QueryMetric(
                target=_target("field:orders.amount", "amount"),
                aggregation="sum",
                display_name="销售额",
            )
        ],
        group_by=[_target("field:departments.name", "name", alias="d")],
        ordering=[
            QueryOrdering(
                target=_target("field:orders.amount", "amount"),
                direction="desc",
            )
        ],
    )


def _known_context(**overrides) -> ProgressiveContextState:
    state = ProgressiveContextState(
        asset_refs={"asset:orders", "asset:departments"},
        relationship_refs={"relationship:orders.department"},
        field_refs={
            "field:orders.order_id",
            "field:orders.order_date",
            "field:orders.amount",
            "field:departments.name",
        },
        lookup_dependencies={"field:departments.name": {"source": "l3"}},
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


@pytest.mark.asyncio
async def test_validation_needs_more_context_returns_l4_and_does_not_execute(monkeypatch):
    runtime = BIWorkerQueryRuntime(db=None)
    called = False

    async def _fail_if_executed(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("缺上下文时不得执行 L5 查询")

    monkeypatch.setattr(runtime, "_execute_supported_plan", _fail_if_executed)

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看订单所属部门和金额",
        query_plan=_plan(relationship_ref="relationship:orders.region"),
        context_state=_known_context(),
    )

    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["status"] == "failed"
    assert "failure_type" in payload
    assert "safe_diagnosis" in payload
    assert called is False


@pytest.mark.asyncio
async def test_execute_failure_returns_safe_repair_request(monkeypatch):
    runtime = BIWorkerQueryRuntime(db=None)

    async def _raise_raw_database_error(*args, **kwargs):
        raise RuntimeError("SELECT * FROM missing_table raw_rows")

    monkeypatch.setattr(runtime, "_execute_supported_plan", _raise_raw_database_error)

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看订单所属部门和金额",
        query_plan=_plan(),
        context_state=_known_context(),
    )

    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["status"] == "failed"
    assert payload["failure_type"] is not None
    result_text = str(payload).lower()
    assert "select " not in result_text
    assert "missing_table" not in result_text
    assert "raw_rows" not in result_text


@pytest.mark.asyncio
async def test_supported_plan_returns_dataset_query_result_without_private_details(monkeypatch):
    runtime = BIWorkerQueryRuntime(db=None)

    async def _return_safe_result(*args, **kwargs):
        return BIWorkerQueryResult(
            answer_summary="查询已完成，结果已生成。",
            artifact_ref="artifact:query-result-1",
            checkpoint_ref="checkpoint:query-1",
            row_count=3,
            column_count=2,
        )

    monkeypatch.setattr(runtime, "_execute_supported_plan", _return_safe_result)

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看订单所属部门和金额",
        query_plan=_plan(),
        context_state=_known_context(),
    )

    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["artifact_card"]["primary_ref"]["ref_id"] == "artifact:query-result-1"
    result_text = str(payload).lower()
    assert "select " not in result_text
    assert "raw_rows" not in result_text


def test_direct_fallback_helper_exists():
    assert callable(execute_dataset_query_for_agent_team_direct_fallback)


@pytest.mark.asyncio
async def test_empty_filters_with_suggested_filters_returns_filter_missing(monkeypatch):
    runtime = BIWorkerQueryRuntime(db=None)
    called = False

    async def _fail_if_executed(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("缺少 filter 时不得执行 L5 查询")

    monkeypatch.setattr(runtime, "_execute_supported_plan", _fail_if_executed)

    plan_no_filters = BIWorkerQueryPlan(
        intent="detail_query",
        question="查看杨凯的工作日志",
        result_shape=ResultShape(type="table", grain="工作日志", limit=50),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(asset_ref="asset:employee_work_log", alias="e", role="fact"),
            supporting_entities=[],
        ),
        selects=[
            QuerySelect(
                target=_target("field:employee_work_log.log_content", "log_content"),
                display_name="日志内容",
            ),
        ],
    )
    # 构建含 suggested_filters 且 field_refs 匹配计划的上下文
    state = ProgressiveContextState(
        asset_refs={"asset:employee_work_log"},
        field_refs={"field:employee_work_log.log_content"},
        suggested_filters=[
            {"clue_type": "person_name", "value": "杨凯", "reason": "用户输入的人名应从员工姓名字段筛选"},
        ],
    )

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看杨凯的工作日志",
        query_plan=plan_no_filters,
        context_state=state,
    )

    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["status"] == "failed"
    assert payload["failure_type"] == "FILTER_MISSING"
    assert "过滤条件" in payload["safe_diagnosis"]
    assert called is False


@pytest.mark.asyncio
async def test_empty_filters_without_suggested_filters_executes_normally(monkeypatch):
    """确认没有 suggested_filters 时空 filters 不会触发 FILTER_MISSING。"""
    runtime = BIWorkerQueryRuntime(db=None)
    executed = False

    async def _record_execution(*args, **kwargs):
        nonlocal executed
        executed = True
        return BIWorkerQueryResult(
            answer_summary="查询已完成。",
            artifact_ref="artifact:query-result-1",
            checkpoint_ref="checkpoint:query-1",
            row_count=5,
            column_count=2,
        )

    monkeypatch.setattr(runtime, "_execute_supported_plan", _record_execution)

    plan_no_filters = BIWorkerQueryPlan(
        intent="detail_query",
        question="查看工作日志",
        result_shape=ResultShape(type="table", grain="工作日志", limit=50),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(asset_ref="asset:employee_work_log", alias="e", role="fact"),
            supporting_entities=[],
        ),
        selects=[
            QuerySelect(
                target=_target("field:employee_work_log.log_content", "log_content"),
                display_name="日志内容",
            ),
        ],
    )
    # 确保 field_refs 与计划匹配且 suggested_filters 为空
    state = ProgressiveContextState(
        asset_refs={"asset:employee_work_log"},
        field_refs={"field:employee_work_log.log_content"},
        suggested_filters=[],
    )

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看工作日志",
        query_plan=plan_no_filters,
        context_state=state,
    )

    assert payload["status"] == "completed"
    assert executed is True


def test_query_plan_conversion_preserves_table_name_for_detail_sql():
    runtime = BIWorkerQueryRuntime(db=None)

    dsl = runtime._query_plan_to_legacy_query_plan(_plan())
    compiled = compile_query_plan_to_sql(
        query_plan=dsl,
        sql_generation_context={
            "table_schemas": [
                {"table_name": "orders", "fields": [{"column_name": "order_id"}, {"column_name": "order_date"}]},
                {"table_name": "departments", "fields": [{"column_name": "name"}]},
            ],
        },
        dialect="sqlite",
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is True
    assert 'FROM "orders"' in compiled["sql"]
    assert 'FROM "order_id"' not in compiled["sql"]
    assert '"orders"."order_id" AS "订单号"' in compiled["sql"]
    assert '"orders"."order_date" >= ' in compiled["sql"]
    assert 'ORDER BY "orders"."amount" DESC' in compiled["sql"]


def test_metric_query_plan_conversion_compiles_aggregation_and_group_by():
    runtime = BIWorkerQueryRuntime(db=None)
    metric_plan = BIWorkerQueryPlan(
        intent="metric_query",
        question="按部门统计销售额",
        result_shape=ResultShape(type="metric", grain="部门", limit=100),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(asset_ref="asset:orders", alias="o", role="fact"),
            supporting_entities=[
                QueryEntity(asset_ref="asset:departments", alias="d", role="dimension"),
            ],
        ),
        metrics=[
            QueryMetric(
                target=_target("field:orders.amount", "amount"),
                aggregation="sum",
                display_name="销售额",
            )
        ],
        group_by=[_target("field:departments.name", "name", alias="d")],
    )

    dsl = runtime._query_plan_to_legacy_query_plan(metric_plan)
    compiled = compile_query_plan_to_sql(
        query_plan=dsl,
        sql_generation_context={
            "table_schemas": [
                {"table_name": "orders", "fields": [{"column_name": "amount"}]},
                {"table_name": "departments", "fields": [{"column_name": "name"}]},
            ],
        },
        dialect="sqlite",
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is True
    assert 'SUM("orders"."amount") AS "销售额"' in compiled["sql"]
    assert '"departments"."name" AS "name"' in compiled["sql"]
    assert 'GROUP BY "departments"."name"' in compiled["sql"]
