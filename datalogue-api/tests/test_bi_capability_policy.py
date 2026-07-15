# ============================================================
# File Name   : test_bi_capability_policy.py
# Description:
#   BI 四级能力策略的单元测试。
#
# Responsibilities:
#   - 验证单表、多表、指标语义和多智能体能力边界。
#   - 确保能力违规响应不泄露 QueryPlan 内部引用和问题内容。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

from app.domains.bi.capability_policy import (
    BICapabilityLevel,
    BICapabilityViolationCode,
    get_bi_capability_policy,
    validate_bi_query_plan_capability,
)
from app.domains.bi.worker.contracts import (
    BIWorkerQueryPlan,
    FieldTarget,
    JoinKey,
    JoinRequirement,
    QueryDataGraph,
    QueryEntity,
    QueryMetric,
    QuerySelect,
    ResultShape,
)


def _field(asset: str, alias: str, field: str) -> FieldTarget:
    return FieldTarget(asset_ref=asset, alias=alias, field=field)


def _detail_plan(*, supporting_count: int = 0) -> BIWorkerQueryPlan:
    supporting_entities = [
        QueryEntity(asset_ref=f"asset:demo.support_{index}", alias=f"s{index}", role="dimension")
        for index in range(supporting_count)
    ]
    joins = [
        JoinRequirement(
            left_alias="p",
            right_alias=entity.alias,
            relationship_ref=f"relationship:demo.support_{index}",
            join_keys=[JoinKey(left_field="id", right_field="primary_id")],
        )
        for index, entity in enumerate(supporting_entities)
    ]
    return BIWorkerQueryPlan(
        intent="detail_query",
        question="包含敏感业务名称的问题",
        result_shape=ResultShape(type="table", grain="记录"),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(asset_ref="asset:demo.primary", alias="p", role="fact"),
            supporting_entities=supporting_entities,
        ),
        join_requirements=joins,
        selects=[
            QuerySelect(
                target=_field("field:demo.primary.secret_field", "p", "secret_field"),
                display_name="记录",
            )
        ],
    )


def _metric_plan() -> BIWorkerQueryPlan:
    return BIWorkerQueryPlan(
        intent="metric_query",
        question="按部门统计金额",
        result_shape=ResultShape(type="metric", grain="部门"),
        data_graph=QueryDataGraph(
            primary_entity=QueryEntity(asset_ref="asset:demo.primary", alias="p", role="fact")
        ),
        metrics=[
            QueryMetric(
                target=_field("field:demo.primary.amount", "p", "amount"),
                aggregation="sum",
                display_name="总金额",
            )
        ],
        group_by=[_field("field:demo.primary.department", "p", "department")],
    )


def _codes(result) -> set[BICapabilityViolationCode]:
    return {violation.code for violation in result.violations}


def test_single_table_accepts_plain_detail_plan():
    result = validate_bi_query_plan_capability(
        _detail_plan(), get_bi_capability_policy(BICapabilityLevel.SINGLE_TABLE)
    )

    assert result.allowed is True
    assert result.violations == ()


def test_single_table_rejects_supporting_entities_and_joins():
    result = validate_bi_query_plan_capability(
        _detail_plan(supporting_count=1),
        get_bi_capability_policy(BICapabilityLevel.SINGLE_TABLE),
    )

    assert result.allowed is False
    assert _codes(result) == {
        BICapabilityViolationCode.SUPPORTING_ENTITY_NOT_ALLOWED,
        BICapabilityViolationCode.JOIN_NOT_ALLOWED,
        BICapabilityViolationCode.ENTITY_LIMIT_EXCEEDED,
    }


def test_single_table_rejects_metrics_and_group_by():
    result = validate_bi_query_plan_capability(
        _metric_plan(), get_bi_capability_policy(BICapabilityLevel.SINGLE_TABLE)
    )

    assert _codes(result) == {
        BICapabilityViolationCode.METRIC_NOT_ALLOWED,
        BICapabilityViolationCode.GROUP_BY_NOT_ALLOWED,
    }


def test_multi_table_accepts_three_entities_but_rejects_four():
    policy = get_bi_capability_policy(BICapabilityLevel.MULTI_TABLE)

    accepted = validate_bi_query_plan_capability(_detail_plan(supporting_count=2), policy)
    rejected = validate_bi_query_plan_capability(_detail_plan(supporting_count=3), policy)

    assert accepted.allowed is True
    assert _codes(rejected) == {BICapabilityViolationCode.ENTITY_LIMIT_EXCEEDED}


def test_multi_table_rejects_metrics_and_group_by():
    result = validate_bi_query_plan_capability(
        _metric_plan(), get_bi_capability_policy(BICapabilityLevel.MULTI_TABLE)
    )

    assert _codes(result) == {
        BICapabilityViolationCode.METRIC_NOT_ALLOWED,
        BICapabilityViolationCode.GROUP_BY_NOT_ALLOWED,
    }


def test_semantic_metrics_and_agent_team_accept_full_plan_shape():
    plan = _metric_plan()

    for level in (BICapabilityLevel.SEMANTIC_METRICS, BICapabilityLevel.AGENT_TEAM):
        result = validate_bi_query_plan_capability(plan, get_bi_capability_policy(level))
        assert result.allowed is True


def test_violation_payload_does_not_expose_plan_details():
    result = validate_bi_query_plan_capability(
        _detail_plan(supporting_count=1),
        get_bi_capability_policy(BICapabilityLevel.SINGLE_TABLE),
    )
    payload_text = repr(result)

    assert "secret_field" not in payload_text
    assert "demo.primary" not in payload_text
    assert "敏感业务名称" not in payload_text
