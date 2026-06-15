import json

from app.services.subagent_planning.contracts import CandidateAsset
from app.services.subagent_planning.planner import build_fallback_query_plan, plan_query


class FakeLLMResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, content=None, exc=None):
        self.content = content
        self.exc = exc
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if self.exc:
            raise self.exc
        return FakeLLMResponse(self.content)


def _field(name="created_at"):
    return CandidateAsset(
        asset_type="field",
        asset_id=f"table:user_logs.column:{name}",
        name=name,
        display_name="日志时间",
        source="schema",
        confidence=0.82,
        metadata={"table_name": "user_logs", "column_name": name},
    )


def _table(name="user_logs"):
    return {
        "asset_type": "table",
        "asset_id": name,
        "name": name,
        "display_name": "用户日志表",
        "source": "schema",
        "confidence": 0.76,
        "metadata": {"table_name": name},
    }


def _blueprint(parameters=None):
    return CandidateAsset(
        asset_type="blueprint",
        asset_id=7,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.91,
        metadata={"parameters": parameters or []},
    )


def test_fallback_detail_query_uses_query_graph_without_metrics():
    plan = build_fallback_query_plan(
        "查询10条用户日志",
        [_field(), _table()],
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "query_graph"
    assert {asset.asset_type for asset in plan.selected_assets} == {"field", "table"}
    assert plan.explanation["why_continue_without_metric"] == "明细查询不要求必须命中指标或维度。"


def test_fallback_blueprint_hit_detail_query_becomes_reference():
    plan = build_fallback_query_plan(
        "查询10条用户日志",
        [_blueprint(), _field(), _table()],
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "blueprint_as_reference"
    assert plan.reference_assets[0].asset_type == "blueprint"
    assert plan.reference_assets[0].name == "个人日报查询"
    assert plan.reference_assets[0].usage == "reference"
    assert "不是固定蓝图分析" in plan.explanation["why_not_blueprint_execute"]


def test_fallback_blueprint_query_missing_required_input_clarifies():
    plan = build_fallback_query_plan(
        "查一下日报",
        [
            _blueprint(
                parameters=[
                    {"name": "user_name", "required": True},
                    {"key": "start_date", "required": True},
                ]
            )
        ],
    )

    assert plan.query_type == "blueprint_query"
    assert plan.execution_strategy == "clarify"
    assert {item["name"] for item in plan.required_inputs} == {"user_name", "start_date"}
    assert plan.clarification


def test_fallback_accepts_asset_recall_result_dict_for_detail_query():
    plan = build_fallback_query_plan(
        "查询10条用户日志",
        {"assets": [_field().to_dict(), _table()], "summary": {}, "recall_debug": {}},
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "query_graph"
    assert {asset.asset_type for asset in plan.selected_assets} == {"field", "table"}


def test_fallback_accepts_keyword_routing_and_fallback_reason():
    plan = build_fallback_query_plan(
        question="查询10条用户日志",
        routing={"route": "dataset_subagent", "inputs": {"limit": 10}},
        candidate_assets={"assets": [_field().to_dict(), _table()]},
        fallback_reason="llm_plan_invalid",
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "query_graph"
    assert plan.fallback_reason == "llm_plan_invalid"


def test_fallback_blueprint_query_with_inputs_executes_blueprint():
    plan = build_fallback_query_plan(
        question="查一下日报",
        routing={"inputs": {"user_name": "KenYang", "start_date": "2026-06-15"}},
        candidate_assets=[
            _blueprint(
                parameters={
                    "user_name": {"required": True},
                    "start_date": {"required": True},
                }
            )
        ],
    )

    assert plan.query_type == "blueprint_query"
    assert plan.execution_strategy == "blueprint_execute"
    assert plan.selected_assets[0].asset_type == "blueprint"
    assert plan.selected_assets[0].usage == "selected"
    assert plan.required_inputs == []


def test_plan_query_with_llm_validates_and_returns_llm_plan(monkeypatch, db_session):
    llm_payload = {
        "query_type": "detail_query",
        "execution_strategy": "blueprint_as_reference",
        "confidence": 0.88,
        "selected_assets": [_field().to_dict(), _table()],
        "reference_assets": [_blueprint().to_dict()],
        "planner_source": "llm",
        "explanation": {"summary": "使用字段和表查询明细，蓝图仅作为参考。"},
    }
    fake_llm = FakeLLM(json.dumps(llm_payload, ensure_ascii=False))

    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: fake_llm,
    )

    plan = plan_query(
        db=db_session,
        question="查询10条用户日志",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": [_blueprint().to_dict(), _field().to_dict(), _table()]},
    )

    assert plan.planner_source == "llm"
    assert plan.execution_strategy == "blueprint_as_reference"


def test_plan_query_falls_back_when_llm_raises(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: FakeLLM(exc=RuntimeError("planner down")),
    )

    plan = plan_query(
        db=db_session,
        question="查询10条用户日志",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": [_field().to_dict(), _table()]},
    )

    assert plan.planner_source == "fallback"
    assert plan.fallback_reason == "planner down"
    assert plan.execution_strategy == "query_graph"


def test_plan_query_falls_back_when_llm_clarifies_detail_query_with_field_table(
    monkeypatch,
    db_session,
):
    llm_payload = {
        "query_type": "detail_query",
        "execution_strategy": "clarify",
        "confidence": 0.66,
        "required_inputs": [{"name": "metric", "required": True}],
        "clarification": {"message": "请选择指标"},
        "planner_source": "llm",
        "explanation": {"summary": "需要指标后继续。"},
    }
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: FakeLLM(json.dumps(llm_payload, ensure_ascii=False)),
    )

    plan = plan_query(
        db=db_session,
        question="查询10条用户日志",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": [_field().to_dict(), _table()]},
    )

    assert plan.planner_source == "fallback"
    assert plan.execution_strategy == "query_graph"
    assert "detail_query" in plan.fallback_reason
