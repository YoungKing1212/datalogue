# ============================================================
# File Name   : test_subagent_execution.py
# Description:
#   SubAgent 查询规划执行策略辅助函数测试。
#
# Responsibilities:
#   - 验证蓝图参考上下文明确标注 SQL 仅供参考。
#   - 验证澄清与拒答执行策略能生成稳定 SubAgentResult。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from app.services.subagent_planning import (
    CandidateAsset,
    QueryPlan,
    build_blueprint_reference_context,
    build_clarify_result,
    build_reject_result,
)


def test_build_blueprint_reference_context_marks_sql_reference_only():
    blueprint = CandidateAsset(
        asset_type="blueprint",
        asset_id=12,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.92,
        metadata={
            "description": "按人员和日期查询日报明细。",
            "when_to_use": "用户明确要看个人日报明细时使用。",
            "parameters": [{"name": "person_name", "required": True}],
            "sql_template": "SELECT * FROM daily_report WHERE person_name = :person_name",
        },
        usage="reference",
    )
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="blueprint_as_reference",
        confidence=0.86,
        reference_assets=[blueprint],
    )

    context = build_blueprint_reference_context(plan)

    assert "个人日报查询" in context
    assert "按人员和日期查询日报明细。" in context
    assert "只能作为参考证据" in context
    assert "不能原样执行" in context
    assert "SELECT * FROM daily_report" in context
    assert "person_name" in context


def test_build_clarify_result_uses_plan_message():
    plan = QueryPlan(
        query_type="ambiguous",
        execution_strategy="clarify",
        confidence=0.64,
        required_inputs=[{"name": "person_name", "required": True}],
        clarification={"message": "请补充人员。"},
    )

    result = build_clarify_result(plan)

    assert result.final_state["answer"] == "请补充人员。"
    assert result.final_state["entry_route"] == "clarify"
    assert result.final_state["entry_intent"] == "clarification"
    assert result.final_state["route_payload"]["kind"] == "query_plan_clarification"
    assert result.final_state["required_inputs"] == [{"name": "person_name", "required": True}]


def test_build_reject_result_uses_explanation_summary():
    plan = QueryPlan(
        query_type="unsupported",
        execution_strategy="reject",
        confidence=0.31,
        explanation={"summary": "当前数据集不支持该类问题。"},
    )

    result = build_reject_result(plan)

    assert result.final_state["answer"] == "当前数据集不支持该类问题。"
    assert result.final_state["entry_route"] == "reject"
    assert result.final_state["entry_intent"] == "rejection"
    assert result.final_state["route_payload"]["kind"] == "query_plan_reject"
