# ============================================================
# File Name   : test_bi_worker_query_validator.py
# Description:
#   BI Worker Query Support Validator 的单元测试。
#
# Responsibilities:
#   - 验证 L4 校验器对资产、关系、字段和 lookup 依赖的支持度判断。
#   - 确保缺失上下文响应只包含安全引用信息，不暴露底层 SQL 或数据细节。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
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
from app.agentscope_service.bi_worker_validator import (
    BIWorkerQueryValidator,
    ProgressiveContextState,
)


def _target(ref: str, field: str, alias: str = "o") -> FieldTarget:
    return FieldTarget(asset_ref=ref, alias=alias, field=field)


def _plan(
    *,
    relationship_ref: str = "relationship:orders.department",
    department_select: QuerySelect | None = None,
    filter_target_ref: str = "field:orders.order_date",
) -> BIWorkerQueryPlan:
    selects = [
        QuerySelect(
            target=_target("field:orders.order_id", "order_id"),
            display_name="订单号",
        )
    ]
    if department_select is not None:
        selects.append(department_select)

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
                target=_target(filter_target_ref, "order_date"),
                operator=">=",
                value="2026-01-01",
                reason="限定查询时间范围",
            )
        ],
        selects=selects,
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


def test_known_fields_and_relationships_are_supported():
    result = BIWorkerQueryValidator().validate(_plan(), _known_context())

    assert result.support_status == "supported"
    assert result.missing_context == []
    assert result.recommended_next_tool is None


def test_unknown_relationship_needs_more_context():
    result = BIWorkerQueryValidator().validate(
        _plan(relationship_ref="relationship:orders.region"),
        _known_context(),
    )

    assert result.support_status == "needs_more_context"
    assert result.missing_context[0]["type"] == "missing_relationship"
    assert result.missing_context[0]["ref"] == "relationship:orders.region"
    assert result.recommended_next_tool == "datalogue_request_schema_slice"


def test_decoding_select_without_lookup_dependency_needs_more_context():
    result = BIWorkerQueryValidator().validate(
        _plan(
            department_select=QuerySelect(
                target=_target("field:departments.name", "name", alias="d"),
                display_name="部门名称",
                display_semantic="department_name",
                requires_decoding=True,
            )
        ),
        _known_context(lookup_dependencies={}),
    )

    assert result.support_status == "needs_more_context"
    assert result.missing_context[0]["type"] == "lookup_dependency"
    assert result.missing_context[0]["ref"] == "field:departments.name"
    assert result.recommended_next_tool == "datalogue_profile_candidate_values"


def test_missing_relationship_after_context_limit_stops_auto_expansion():
    result = BIWorkerQueryValidator().validate(
        _plan(relationship_ref="relationship:orders.region"),
        _known_context(validation_more_context_count=2),
    )

    assert result.support_status in {"needs_clarification", "unsupported"}
    assert result.missing_context[0]["type"] == "missing_relationship"
    assert result.auto_context_expansions == []


def test_unknown_asset_and_field_are_reported_as_safe_missing_context():
    result = BIWorkerQueryValidator().validate(
        _plan(filter_target_ref="field:orders.unknown_flag"),
        _known_context(asset_refs={"asset:orders"}),
    )

    missing_types = {item["type"] for item in result.missing_context}
    assert result.support_status == "needs_more_context"
    assert {"missing_asset", "missing_field"}.issubset(missing_types)
    for item in result.missing_context:
        assert set(item).issubset({"type", "ref", "recommended_next_tool", "focus"})
