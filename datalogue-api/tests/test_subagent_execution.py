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
    assert "SELECT * FROM daily_report" not in context
    assert "SQL 参考模板" not in context
    assert "person_name" in context


def test_build_blueprint_reference_context_skips_non_reference_strategy():
    blueprint = CandidateAsset(
        asset_type="blueprint",
        asset_id=12,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.92,
        metadata={"sql_template": "SELECT * FROM daily_report"},
        usage="reference",
    )
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.86,
        reference_assets=[blueprint],
    )

    context = build_blueprint_reference_context(plan)

    assert context == ""


def test_build_blueprint_reference_context_truncates_large_blueprint_values():
    long_sql = "SELECT * FROM daily_report WHERE note = '" + ("很长" * 400) + "'"
    long_description = "说明" * 500
    long_parameters = [
        {
            "name": "person_name",
            "description": "人员参数" * 300,
            "required": True,
        }
    ]
    blueprint = CandidateAsset(
        asset_type="blueprint",
        asset_id=13,
        name="长模板蓝图",
        display_name="长模板蓝图",
        source="analysis_blueprint",
        confidence=0.88,
        metadata={
            "description": long_description,
            "parameters": long_parameters,
            "sql_template": long_sql,
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

    assert "只能作为参考证据" in context
    assert "不能原样执行" in context
    assert "SELECT * FROM daily_report" not in context
    assert long_sql not in context
    assert long_description not in context
    assert "人员参数" * 300 not in context
    assert "...[已截断]" in context


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
    assert "assets" in result.candidate_assets
    assert "summary" in result.candidate_assets
    assert result.candidate_assets["summary"]["total_count"] == 0


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
    assert result.final_state["error"] is None
    assert result.final_state["route_payload"]["kind"] == "query_plan_reject"
    assert "assets" in result.candidate_assets
    assert "summary" in result.candidate_assets


def test_build_results_candidate_assets_use_recall_contract_shape():
    selected = CandidateAsset(
        asset_type="field",
        asset_id="user_logs.id",
        name="id",
        display_name="ID",
        source="schema",
        confidence=0.81,
        usage="selected",
    )
    reference = CandidateAsset(
        asset_type="blueprint",
        asset_id=12,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.72,
        usage="reference",
    )
    rejected = CandidateAsset(
        asset_type="metric",
        asset_id=8,
        name="日志总数",
        display_name="日志总数",
        source="semantic_metric",
        confidence=0.22,
        usage="rejected",
    )
    plan = QueryPlan(
        query_type="ambiguous",
        execution_strategy="clarify",
        confidence=0.64,
        selected_assets=[selected],
        reference_assets=[reference],
        rejected_assets=[rejected],
        clarification={"message": "请补充筛选条件。"},
    )

    clarify_result = build_clarify_result(plan)
    reject_result = build_reject_result(
        QueryPlan(
            query_type="unsupported",
            execution_strategy="reject",
            confidence=0.31,
            selected_assets=[selected],
            reference_assets=[reference],
            rejected_assets=[rejected],
        )
    )

    assert set(clarify_result.candidate_assets) == {"assets", "summary"}
    assert set(reject_result.candidate_assets) == {"assets", "summary"}
    assert len(clarify_result.candidate_assets["assets"]) == 3
    assert clarify_result.candidate_assets["summary"]["total_count"] == 3
    assert clarify_result.candidate_assets["summary"]["by_usage"] == {
        "selected": 1,
        "reference": 1,
        "rejected": 1,
    }
