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
            {
                "clue_type": "person_name",
                "value": "杨凯",
                "reason": "用户输入的人名应从员工姓名字段筛选",
            },
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
    from app.agentscope_service.bi_worker_contracts import JoinKey

    runtime = BIWorkerQueryRuntime(db=None)

    plan = _plan()
    # 编译器要求 join_requirements 显式声明 join_keys，否则 fail-closed；
    # 本用例聚焦 FROM/SELECT/WHERE/ORDER BY 生成，此处补齐 join_keys 让编译走通。
    plan.join_requirements[0].join_keys = [
        JoinKey(left_field="dept_id", right_field="id"),
    ]

    dsl = runtime._query_plan_to_legacy_query_plan(plan)
    compiled = compile_query_plan_to_sql(
        query_plan=dsl,
        sql_generation_context={
            "table_schemas": [
                {
                    "table_name": "orders",
                    "fields": [
                        {"column_name": "order_id"},
                        {"column_name": "order_date"},
                        {"column_name": "dept_id"},
                    ],
                },
                {
                    "table_name": "departments",
                    "fields": [{"column_name": "id"}, {"column_name": "name"}],
                },
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


# ---- Repair 链路修复：bridge status/code + 空结果映射 + join_keys 契约扩展 ----


@pytest.mark.asyncio
async def test_execute_plan_maps_null_row_count_to_empty_result(monkeypatch):
    """bridge 返回 status=completed 但 artifact_ref=None、row_count=None 时，应兜底为 EMPTY_RESULT。

    修复前 execute_query_plan 空结果映射用 row_count == 0 判定，None 会掉进 completed
    默认分支，导致 LLM 拿不到 failure_type，repair 链路 B 不触发。
    """
    runtime = BIWorkerQueryRuntime(db=None)

    async def _return_null_result(*args, **kwargs):
        return BIWorkerQueryResult(
            answer_summary="查询未完成，未生成可展示结果。",
            artifact_ref=None,
            checkpoint_ref=None,
            row_count=None,
            column_count=None,
        )

    monkeypatch.setattr(runtime, "_execute_supported_plan", _return_null_result)

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看订单所属部门和金额",
        query_plan=_plan(),
        context_state=_known_context(),
    )

    assert payload["status"] == "failed"
    assert payload["failure_type"] == "EMPTY_RESULT"
    assert payload["safe_diagnosis"]
    assert payload["recommended_action"]


@pytest.mark.asyncio
async def test_execute_plan_passes_through_bridge_blocked_failure_type(monkeypatch):
    """_execute_plan 直接写入的 failure_type（bridge blocked）在 execute_query_plan 主链应透传。"""
    runtime = BIWorkerQueryRuntime(db=None)

    async def _return_blocked_result(*args, **kwargs):
        from app.agentscope_service.bi_worker_contracts import FAILURE_DIAGNOSIS_MAP

        diagnosis = FAILURE_DIAGNOSIS_MAP["FIELD_NOT_FOUND"]
        return BIWorkerQueryResult(
            answer_summary="查询执行未完成（FIELD_NOT_FOUND）。",
            artifact_ref=None,
            checkpoint_ref=None,
            row_count=None,
            column_count=None,
            failure_type="FIELD_NOT_FOUND",
            safe_diagnosis=diagnosis["safe_diagnosis"],
            recommended_action=diagnosis["recommended_action"],
        )

    monkeypatch.setattr(runtime, "_execute_supported_plan", _return_blocked_result)

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="查看订单所属部门和金额",
        query_plan=_plan(),
        context_state=_known_context(),
    )
    # 失败结果原样透传，不会被 EMPTY_RESULT 覆盖。
    assert payload["status"] == "failed"
    assert payload["failure_type"] == "FIELD_NOT_FOUND"


def test_map_bridge_code_to_failure_maps_execute_blocked_by_keywords():
    """_map_bridge_code_to_failure 复用 _map_exception 的关键字表；EXECUTE_BLOCKED 默认落回 FIELD_NOT_FOUND。"""
    from app.agentscope_service.bi_worker_runtime import _map_bridge_code_to_failure

    assert (
        _map_bridge_code_to_failure(code="EXECUTE_BLOCKED", error_summary="") == "FIELD_NOT_FOUND"
    )
    assert (
        _map_bridge_code_to_failure(code="EXECUTE_BLOCKED", error_summary="bind parameter")
        == "VALUE_BINDING_FAILED"
    )
    assert (
        _map_bridge_code_to_failure(code="SQL_GUARD_BLOCKED", error_summary="")
        == "SQL_GUARD_BLOCKED"
    )
    assert (
        _map_bridge_code_to_failure(code="TOOL_SEQUENCE_EXHAUSTED", error_summary="")
        == "FIELD_NOT_FOUND"
    )
    assert (
        _map_bridge_code_to_failure(code="RUNTIME_BLOCKED", error_summary="aggregation mismatch")
        == "AGGREGATION_WRONG"
    )


def test_query_plan_supports_join_keys_and_legacy_dsl_includes_join_requirements():
    """JoinRequirement 支持 join_keys 声明字段，legacy DSL 透传给下游编译器。"""
    from app.agentscope_service.bi_worker_contracts import JoinKey

    runtime = BIWorkerQueryRuntime(db=None)
    plan = _plan()
    plan.join_requirements[0].join_keys = [
        JoinKey(left_field="account", right_field="person_card"),
    ]

    dsl = runtime._query_plan_to_legacy_query_plan(plan)
    assert "join_requirements" in dsl
    assert dsl["join_requirements"][0]["join_keys"] == [
        {"left_field": "account", "right_field": "person_card"},
    ]
    assert dsl["join_requirements"][0]["left_alias"] == "o"
    assert dsl["join_requirements"][0]["right_alias"] == "d"


def test_query_plan_join_keys_default_empty_list():
    """未显式声明 join_keys 时，legacy DSL 里应为空列表（不遗漏 key）。"""
    runtime = BIWorkerQueryRuntime(db=None)
    plan = _plan()
    dsl = runtime._query_plan_to_legacy_query_plan(plan)
    assert dsl["join_requirements"][0]["join_keys"] == []


# ---- alias→table 解析与端到端 JOIN 编译（改动 C 新增）----


def test_query_plan_to_legacy_dsl_includes_left_and_right_table_from_alias():
    """legacy DSL 的 join_requirements 元素应通过 _alias_table_names 携带 left/right_table。"""
    runtime = BIWorkerQueryRuntime(db=None)
    # _plan() 里 primary alias="o" -> orders，supporting alias="d" -> departments
    dsl = runtime._query_plan_to_legacy_query_plan(_plan())

    assert dsl["join_requirements"][0]["left_table"] == "orders"
    assert dsl["join_requirements"][0]["right_table"] == "departments"


def test_end_to_end_join_keys_to_sql_via_compiler():
    """端到端：JoinKey → legacy DSL → 编译器 → 生成合法 LEFT JOIN SQL。"""
    from app.agentscope_service.bi_worker_contracts import JoinKey

    runtime = BIWorkerQueryRuntime(db=None)
    plan = _plan()
    # _plan() 默认 join_keys 为空，此处显式补上关联字段声明
    plan.join_requirements[0].join_keys = [
        JoinKey(left_field="dept_id", right_field="id"),
    ]

    dsl = runtime._query_plan_to_legacy_query_plan(plan)
    compiled = compile_query_plan_to_sql(
        query_plan=dsl,
        sql_generation_context={
            "table_schemas": [
                {
                    "table_name": "orders",
                    "fields": [
                        {"column_name": "order_id"},
                        {"column_name": "order_date"},
                        {"column_name": "amount"},
                        {"column_name": "dept_id"},
                    ],
                },
                {
                    "table_name": "departments",
                    "fields": [{"column_name": "id"}, {"column_name": "name"}],
                },
            ],
        },
        dialect="sqlite",
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is True
    assert 'LEFT JOIN "departments" ON "orders"."dept_id" = "departments"."id"' in compiled["sql"]


def test_schema_qualified_table_refs_resolve_alias_tables_for_join_sql():
    """L2 返回 table:schema.table 时，runtime 应能反查 alias→物理表并编译 JOIN。"""
    from app.agentscope_service.bi_worker_contracts import JoinKey

    runtime = BIWorkerQueryRuntime(db=None)
    plan = BIWorkerQueryPlan(
        intent="detail_query",
        question="查询杨凯2024年日志",
        result_shape=ResultShape(type="table", grain="日报", limit=100),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(
                asset_ref="table:pm_tenant.plan_task_daily_record",
                alias="main",
                role="primary",
            ),
            supporting_entities=[
                QueryEntity(
                    asset_ref="table:pm_tenant.eas_personofile",
                    alias="person",
                    role="supporting",
                )
            ],
        ),
        join_requirements=[
            JoinRequirement(
                left_alias="main",
                right_alias="person",
                relationship_ref=(
                    "blueprint_join:1:table:pm_tenant.plan_task_daily_record"
                    "->table:pm_tenant.eas_personofile"
                ),
                join_type="left",
                required=True,
                reason="关联人员档案表获取姓名",
                join_keys=[JoinKey(left_field="account", right_field="person_card")],
            )
        ],
        filters=[
            QueryFilter(
                target=FieldTarget(
                    asset_ref="table:pm_tenant.eas_personofile.person_name",
                    alias="person",
                    field="person_name",
                ),
                operator="=",
                value="杨凯",
                reason="按姓名筛选",
            )
        ],
        selects=[
            QuerySelect(
                target=FieldTarget(
                    asset_ref="table:pm_tenant.plan_task_daily_record.rzrq",
                    alias="main",
                    field="rzrq",
                ),
                display_name="日志日期",
            )
        ],
    )

    dsl = runtime._query_plan_to_legacy_query_plan(plan)
    assert dsl["debug"]["selected_main_table"] == "pm_tenant.plan_task_daily_record"
    assert dsl["join_requirements"][0]["left_table"] == "pm_tenant.plan_task_daily_record"
    assert dsl["join_requirements"][0]["right_table"] == "pm_tenant.eas_personofile"

    compiled = compile_query_plan_to_sql(
        query_plan=dsl,
        sql_generation_context={"table_schemas": []},
        dialect="sqlite",
        allowed_tables=[
            "pm_tenant.plan_task_daily_record",
            "pm_tenant.eas_personofile",
        ],
    )
    assert compiled["ok"] is True
    assert "LEFT JOIN" in compiled["sql"]


def test_table_level_schema_qualified_target_ref_keeps_table_metadata():
    """表级 target.asset_ref=table:schema.table 时，metadata 不能退化为字段名。"""

    runtime = BIWorkerQueryRuntime(db=None)
    plan = BIWorkerQueryPlan(
        intent="detail_query",
        question="查询日志",
        result_shape=ResultShape(type="table", grain="日报", limit=10),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(
                asset_ref="table:pm_tenant.plan_task_daily_record",
                alias="main",
                role="primary",
            )
        ),
        selects=[
            QuerySelect(
                target=FieldTarget(
                    asset_ref="table:pm_tenant.plan_task_daily_record",
                    alias="main",
                    field="rzrq",
                ),
                display_name="日志日期",
            )
        ],
    )

    dsl = runtime._query_plan_to_legacy_query_plan(plan)
    assert dsl["selected_assets"][0]["metadata"] == {
        "column_name": "rzrq",
        "table_name": "pm_tenant.plan_task_daily_record",
    }


# ---- runtime _derive_dataset_field_refs 兜底覆盖(4 层修复) ----


def _mock_dataset(*, tables):
    """构造 SemanticDataset 的最小 duck-typed 替身。

    tables: list of tuples (schema_name, table_name, [column_names], status)
    通过 SimpleNamespace 拼出 dataset.selected_tables[i].source_table.{...}。
    """
    from types import SimpleNamespace

    links = []
    for schema_name, table_name, columns, status in tables:
        table = SimpleNamespace(
            schema_name=schema_name,
            table_name=table_name,
            status=status,
            columns=[SimpleNamespace(column_name=c) for c in columns],
        )
        links.append(SimpleNamespace(source_table=table))
    return SimpleNamespace(selected_tables=links)


@pytest.mark.asyncio
async def test_execute_query_plan_derives_field_refs_from_dataset(monkeypatch):
    """context_state 完全空时,runtime 应从 dataset 元数据补 field_refs,让 L4 通过。"""
    runtime = BIWorkerQueryRuntime(db=None)

    mock_dataset = _mock_dataset(
        tables=[("pm_tenant", "log", ["rzrq"], "active")],
    )
    monkeypatch.setattr(runtime, "_get_dataset", lambda dataset_id: mock_dataset)

    async def _return_safe_result(*args, **kwargs):
        return BIWorkerQueryResult(
            answer_summary="查询已完成。",
            artifact_ref="artifact:query-derived-1",
            checkpoint_ref="checkpoint:query-derived-1",
            row_count=1,
            column_count=1,
        )

    monkeypatch.setattr(runtime, "_execute_supported_plan", _return_safe_result)

    plan = BIWorkerQueryPlan(
        intent="detail_query",
        question="按表级字段查询",
        result_shape=ResultShape(type="table", grain="日报", limit=10),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(
                asset_ref="table:pm_tenant.log",
                alias="main",
                role="primary",
            ),
            supporting_entities=[],
        ),
        selects=[
            QuerySelect(
                target=FieldTarget(
                    asset_ref="table:pm_tenant.log.rzrq",
                    alias="main",
                    field="rzrq",
                ),
                display_name="日志日期",
            )
        ],
    )
    empty_state = ProgressiveContextState()

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="按表级字段查询",
        query_plan=plan,
        context_state=empty_state,
    )

    assert payload["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_query_plan_field_not_in_dataset_still_fails(monkeypatch):
    """dataset 兜底只覆盖真实字段,拼错字段仍应 FIELD_NOT_FOUND。"""
    runtime = BIWorkerQueryRuntime(db=None)

    mock_dataset = _mock_dataset(
        tables=[("pm_tenant", "log", ["rzrq"], "active")],
    )
    monkeypatch.setattr(runtime, "_get_dataset", lambda dataset_id: mock_dataset)

    async def _fail_if_executed(*args, **kwargs):
        raise AssertionError("字段不存在时不应执行 L5 查询")

    monkeypatch.setattr(runtime, "_execute_supported_plan", _fail_if_executed)

    plan = BIWorkerQueryPlan(
        intent="detail_query",
        question="拼错字段应报 FIELD_NOT_FOUND",
        result_shape=ResultShape(type="table", grain="日报", limit=10),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(
                asset_ref="table:pm_tenant.log",
                alias="main",
                role="primary",
            ),
            supporting_entities=[],
        ),
        selects=[
            QuerySelect(
                target=FieldTarget(
                    asset_ref="table:pm_tenant.log.xyz_typo",
                    alias="main",
                    field="xyz_typo",
                ),
                display_name="拼错字段",
            )
        ],
    )

    payload = await runtime.execute_query_plan(
        dataset_id=1,
        confirmed_question="拼错字段应报 FIELD_NOT_FOUND",
        query_plan=plan,
        context_state=ProgressiveContextState(),
    )

    assert payload["status"] == "failed"
    assert payload["failure_type"] == "FIELD_NOT_FOUND"


def test_derive_dataset_field_refs_covers_all_columns_and_table():
    """active 表所有列 + 表级 ref 都在集合内;deleted 表完全排除。"""
    from app.agentscope_service.bi_worker_runtime import _derive_dataset_field_refs

    dataset = _mock_dataset(
        tables=[
            ("pm_tenant", "log", ["rzrq", "content"], "active"),
            ("pm_tenant", "archived", ["a", "b"], "deleted"),
        ],
    )
    refs = _derive_dataset_field_refs(dataset)

    assert "table:pm_tenant.log" in refs
    assert "table:pm_tenant.log.rzrq" in refs
    assert "table:pm_tenant.log.content" in refs
    # deleted 表完全排除
    assert "table:pm_tenant.archived" not in refs
    assert "table:pm_tenant.archived.a" not in refs
    assert "table:pm_tenant.archived.b" not in refs


def test_derive_dataset_field_refs_handles_none_dataset():
    """selected_tables 为 None 或 [] 应返回空集合(fail-closed)。"""
    from types import SimpleNamespace

    from app.agentscope_service.bi_worker_runtime import _derive_dataset_field_refs

    assert _derive_dataset_field_refs(SimpleNamespace(selected_tables=None)) == set()
    assert _derive_dataset_field_refs(SimpleNamespace(selected_tables=[])) == set()
