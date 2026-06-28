import pytest

from app.services.subagent_planning.contracts import (
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    SubAgentEvent,
    SubAgentResult,
    normalize_query_plan,
)


def test_candidate_asset_serializes_reference_usage():
    asset = CandidateAsset(
        asset_type="blueprint",
        asset_id=12,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.78,
        match_signals=[{"type": "keyword", "value": "日报", "score": 0.78}],
        metadata={"sql_template": "select * from daily where user_name = :user_name"},
        usage="reference",
        match_reason="关键词命中：日报",
    )

    payload = asset.to_dict()

    assert payload["asset_type"] == "blueprint"
    assert payload["usage"] == "reference"
    assert payload["metadata"]["sql_template"].startswith("select")


def test_query_plan_rejects_invalid_execution_strategy():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "unknown",
        "confidence": 0.5,
        "selected_assets": [],
        "reference_assets": [],
        "rejected_assets": [],
        "required_inputs": [],
        "clarification": None,
        "fallback_reason": None,
        "planner_source": "llm",
        "explanation": {"summary": "非法策略"},
    }

    try:
        normalize_query_plan(raw)
    except QueryPlanValidationError as exc:
        assert "execution_strategy" in str(exc)
    else:
        raise AssertionError("invalid execution_strategy should fail validation")


def test_normalize_query_plan_accepts_wrapped_asset_lists():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "blueprint_as_reference",
        "confidence": 0.82,
        "selected_assets": {
            "assets": [
                {
                    "asset_type": "field",
                    "asset_id": "table:user_logs.column:id",
                    "name": "id",
                    "display_name": "日志ID",
                    "source": "schema",
                    "confidence": 0.9,
                    "metadata": {"table_name": "user_logs", "column_name": "id"},
                }
            ]
        },
        "reference_assets": {
            "assets": [
                {
                    "asset_type": "blueprint",
                    "asset_id": 7,
                    "name": "个人日报查询",
                    "display_name": "个人日报查询",
                    "source": "analysis_blueprint",
                    "confidence": 0.8,
                    "metadata": {"implementation_type": "sql_template"},
                }
            ]
        },
        "rejected_assets": {"assets": []},
        "planner_source": "llm",
        "explanation": {"summary": "蓝图作为参考。"},
    }

    plan = normalize_query_plan(raw)

    assert plan.selected_assets[0].asset_type == "field"
    assert plan.selected_assets[0].usage == "selected"
    assert plan.reference_assets[0].asset_type == "blueprint"
    assert plan.reference_assets[0].usage == "reference"


def test_normalize_query_plan_accepts_template_reference_usage_alias():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "blueprint_as_reference",
        "confidence": 0.9,
        "reference_assets": [
            {
                "asset_type": "blueprint",
                "asset_id": 1,
                "name": "个人计划任务日报查询",
                "source": "analysis_blueprint",
                "confidence": 0.99,
                "usage": "template_reference",
            }
        ],
        "planner_source": "llm",
        "explanation": {"summary": "蓝图只作为模板参考。"},
    }

    plan = normalize_query_plan(raw)

    assert plan.reference_assets[0].usage == "reference"


def test_normalize_query_plan_rejects_malformed_asset_wrapper():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "query_graph",
        "confidence": 0.82,
        "selected_assets": {"items": []},
        "planner_source": "llm",
        "explanation": {"summary": "字段查询。"},
    }

    try:
        normalize_query_plan(raw)
    except QueryPlanValidationError as exc:
        assert "selected assets" in str(exc)
    else:
        raise AssertionError("malformed selected_assets wrapper should fail validation")


def test_normalize_query_plan_accepts_required_inputs_dict():
    raw = {
        "query_type": "blueprint_query",
        "execution_strategy": "clarify",
        "confidence": 0.7,
        "required_inputs": {
            "user_name": {"required": True, "display_name": "用户"},
            "start_date": {"required": True},
        },
        "planner_source": "llm",
        "explanation": {"summary": "缺少蓝图参数。"},
    }

    plan = normalize_query_plan(raw)

    assert plan.required_inputs == [
        {"required": True, "display_name": "用户", "name": "user_name"},
        {"required": True, "name": "start_date"},
    ]


def test_normalize_query_plan_rejects_unstable_required_inputs():
    raw = {
        "query_type": "blueprint_query",
        "execution_strategy": "clarify",
        "confidence": 0.7,
        "required_inputs": ["user_name", "start_date"],
        "planner_source": "llm",
        "explanation": {"summary": "缺少蓝图参数。"},
    }

    try:
        normalize_query_plan(raw)
    except QueryPlanValidationError as exc:
        assert "required_inputs" in str(exc)
    else:
        raise AssertionError("list[str] required_inputs should fail validation")


def test_query_plan_constructor_rejects_invalid_strategy():
    try:
        QueryPlan(query_type="detail_query", execution_strategy="unknown", confidence=0.1)
    except QueryPlanValidationError as exc:
        assert "execution_strategy" in str(exc)
    else:
        raise AssertionError("QueryPlan constructor should validate execution_strategy")


def test_query_plan_serializes_selected_reference_and_rejected_assets():
    selected = CandidateAsset(
        asset_type="field",
        asset_id="table:user_logs.column:id",
        name="id",
        display_name="日志ID",
        source="schema",
        confidence=0.9,
        match_signals=[],
        metadata={"table_name": "user_logs", "column_name": "id"},
        usage="selected",
    )
    reference = CandidateAsset(
        asset_type="blueprint",
        asset_id=3,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.7,
        match_signals=[],
        metadata={"implementation_type": "sql_template"},
        usage="reference",
    )
    rejected = CandidateAsset(
        asset_type="metric",
        asset_id=8,
        name="日志总数",
        display_name="日志总数",
        source="semantic_metric",
        confidence=0.2,
        match_signals=[],
        metadata={},
        usage="rejected",
        reject_reason="用户要求明细列表，不需要聚合指标",
    )

    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="blueprint_as_reference",
        confidence=0.86,
        selected_assets=[selected],
        reference_assets=[reference],
        rejected_assets=[rejected],
        required_inputs=[],
        clarification=None,
        fallback_reason=None,
        planner_source="llm",
        explanation={
            "summary": "识别为明细查询",
            "why_not_blueprint_execute": "用户要求查询10条日志，不是个人日报固定分析。",
        },
        decision_factors=[
            {
                "code": "detail_query_signal",
                "message": "问题包含明细查询信号",
                "evidence": ["10条", "日志"],
            }
        ],
        planner_warnings=[
            {
                "code": "blueprint_reference_only",
                "message": "蓝图只能作为参考，不能强执行。",
            }
        ],
        governance_suggestions=[
            {
                "type": "asset_quality",
                "message": "可补充用户日志表的业务字段说明。",
            }
        ],
    )

    payload = plan.to_dict()

    assert payload["execution_strategy"] == "blueprint_as_reference"
    assert payload["selected_assets"][0]["asset_type"] == "field"
    assert payload["reference_assets"][0]["asset_type"] == "blueprint"
    assert payload["rejected_assets"][0]["reject_reason"] == "用户要求明细列表，不需要聚合指标"
    assert payload["decision_factors"][0]["code"] == "detail_query_signal"
    assert payload["planner_warnings"][0]["code"] == "blueprint_reference_only"
    assert payload["governance_suggestions"][0]["type"] == "asset_quality"


def test_normalize_query_plan_accepts_audit_fields():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "query_graph",
        "confidence": 0.81,
        "planner_source": "llm",
        "explanation": {"summary": "使用字段和表查询明细。"},
        "decision_factors": [{"code": "field_match", "message": "命中字段"}],
        "planner_warnings": [{"code": "low_blueprint_fit", "message": "蓝图不适用"}],
        "governance_suggestions": [{"type": "term", "message": "补充失败日志术语"}],
    }

    plan = normalize_query_plan(raw)

    assert plan.decision_factors == [{"code": "field_match", "message": "命中字段"}]
    assert plan.planner_warnings == [{"code": "low_blueprint_fit", "message": "蓝图不适用"}]
    assert plan.governance_suggestions == [{"type": "term", "message": "补充失败日志术语"}]


def test_normalize_query_plan_rejects_malformed_audit_fields():
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "query_graph",
        "confidence": 0.81,
        "planner_source": "llm",
        "explanation": {"summary": "使用字段和表查询明细。"},
        "decision_factors": ["field_match"],
    }

    try:
        normalize_query_plan(raw)
    except QueryPlanValidationError as exc:
        assert "decision_factors" in str(exc)
    else:
        raise AssertionError("audit fields must be list[object]")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("detail_rounds", "three"),
        ("detail_rounds", "3"),
        ("detail_rounds", True),
        (
            "attempted_detail_requests",
            {"asset_type": "table", "asset_id": "wide_table"},
        ),
        ("attempted_detail_requests", "wide_table"),
        ("attempted_detail_requests", ["wide_table"]),
        ("asset_detail_coverage", "wide_table"),
        ("missing_context", "缺少时间字段"),
        ("missing_context", [123]),
        ("risk_flags", "wide_table"),
        ("risk_flags", [{"code": "x"}]),
        ("why_not_generate_sql", 123),
    ],
)
def test_normalize_query_plan_rejects_malformed_detail_audit_fields(
    field_name,
    bad_value,
):
    raw = {
        "query_type": "detail_query",
        "execution_strategy": "reject",
        "confidence": 0.2,
        "planner_source": "llm",
        "explanation": {"summary": "上下文不足"},
        field_name: bad_value,
    }

    try:
        normalize_query_plan(raw)
    except QueryPlanValidationError as exc:
        assert field_name in str(exc)
    else:
        raise AssertionError(f"{field_name} should fail validation")


def test_subagent_event_type_cannot_be_overridden_by_payload():
    event = SubAgentEvent(event_type="query_plan", payload={"type": "wrong", "node": "query_plan"})

    payload = event.to_sse_payload()

    assert payload["type"] == "query_plan"
    assert payload["node"] == "query_plan"


def test_subagent_result_serializes_query_plan_and_trace_payload():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.72,
    )
    result = SubAgentResult(
        final_state={"answer": "已生成查询计划"},
        query_plan=plan,
        candidate_assets={"field": [{"name": "id"}]},
        step_traces=[{"node": "query_plan"}],
    )

    payload = result.to_dict()

    assert payload["final_state"]["answer"] == "已生成查询计划"
    assert payload["query_plan"]["execution_strategy"] == "query_graph"
    assert payload["candidate_assets"]["field"][0]["name"] == "id"
    assert payload["step_traces"][0]["node"] == "query_plan"
