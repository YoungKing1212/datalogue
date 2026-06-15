from app.services.subagent_planning.contracts import (
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
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
    )

    payload = plan.to_dict()

    assert payload["execution_strategy"] == "blueprint_as_reference"
    assert payload["selected_assets"][0]["asset_type"] == "field"
    assert payload["reference_assets"][0]["asset_type"] == "blueprint"
    assert payload["rejected_assets"][0]["reject_reason"] == "用户要求明细列表，不需要聚合指标"
