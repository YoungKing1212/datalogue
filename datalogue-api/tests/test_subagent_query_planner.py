import json

from app.services.observability.context import (
    ObservabilityRequestContext,
    set_observability_context,
)
from app.services.subagent_planning.contracts import (
    CandidateAsset,
    QueryPlan,
    normalize_query_plan,
)
from app.services.subagent_planning.planner import (
    _planner_human_prompt,
    build_fallback_query_plan,
    plan_query,
    plan_query_with_detail_context,
)


class FakeLLMResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, content=None, exc=None):
        self.content = content
        self.exc = exc
        self.messages = None
        self.model_name = "fake-planner-model"

    def invoke(self, messages):
        self.messages = messages
        if self.exc:
            raise self.exc
        return FakeLLMResponse(self.content)


class SequentialFakeLLM:
    def __init__(self, contents):
        self.contents = list(contents)
        self.messages = []
        self.model_name = "fake-planner-model"

    def invoke(self, messages):
        self.messages.append(messages)
        return FakeLLMResponse(self.contents.pop(0))


class FakeOpenAIAPIConnectionError(Exception):
    pass


FakeOpenAIAPIConnectionError.__module__ = "openai"


class FakeTracer:
    def __init__(self):
        self.started_generations = []
        self.ended_generations = []

    def start_generation(self, **kwargs):
        self.started_generations.append(kwargs)
        return {"handle": len(self.started_generations)}

    def end_generation(self, handle, **kwargs):
        self.ended_generations.append({"handle": handle, **kwargs})


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


def _daily_field(name="rzrq", display_name="日志日期"):
    return CandidateAsset(
        asset_type="field",
        asset_id=f"table:plan_task_daily_record.column:{name}",
        name=name,
        display_name=display_name,
        source="schema",
        confidence=0.88,
        metadata={"table_name": "plan_task_daily_record", "column_name": name},
    )


def _daily_table():
    return CandidateAsset(
        asset_type="table",
        asset_id="plan_task_daily_record",
        name="plan_task_daily_record",
        display_name="计划任务日报记录表",
        source="schema",
        confidence=0.9,
        metadata={"table_name": "plan_task_daily_record"},
    )


def _person_table():
    return CandidateAsset(
        asset_type="table",
        asset_id="eas_personofile",
        name="eas_personofile",
        display_name="人员档案表",
        source="schema",
        confidence=0.72,
        metadata={"table_name": "eas_personofile"},
    )


def _blueprint(parameters=None, asset_id=7, name="个人日报查询", confidence=0.91):
    return CandidateAsset(
        asset_type="blueprint",
        asset_id=asset_id,
        name=name,
        display_name=name,
        source="analysis_blueprint",
        confidence=confidence,
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


def test_fallback_detail_query_records_main_table_and_join_hints():
    plan = build_fallback_query_plan(
        "查询汤杰10条工作日志",
        [_blueprint(), _daily_field("rzrq"), _daily_field("zt", "状态"), _daily_table(), _person_table()],
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "query_graph"
    assert plan.planner_source == "deterministic"
    assert plan.debug["selected_main_table"] == "plan_task_daily_record"
    assert plan.debug["join_hints"] == [
        {
            "left_table": "plan_task_daily_record",
            "left_column": "account",
            "right_table": "eas_personofile",
            "right_column": "person_card",
            "purpose": "日志账号关联人员姓名",
        }
    ]
    selected_daily = next(asset for asset in plan.selected_assets if asset.name == "plan_task_daily_record")
    assert selected_daily.metadata["main_table_role"] == "fact"
    rejected_blueprint = next(asset for asset in plan.rejected_assets if asset.asset_type == "blueprint")
    assert "日志明细查询不强套日报蓝图" in rejected_blueprint.reject_reason


def test_dataset10_log_detail_uses_template_plan():
    plan = build_fallback_query_plan(
        "查询10条用户日志",
        [_daily_field("rzrq"), _daily_table(), _person_table()],
        routing={"dataset_id": 10},
    )

    assert plan.planner_source == "template"
    assert plan.execution_strategy == "query_graph"
    assert plan.debug["template_name"] == "dataset10_log_detail"
    assert plan.debug["schema_token_budget"] == "template_bypass"
    assert "FROM plan_task_daily_record p" in plan.debug["sql_template"]
    assert "LEFT JOIN eas_personofile ep ON p.account = ep.person_card" in plan.debug["sql_template"]
    assert "LIMIT 10" in plan.debug["sql_template"]


def test_fallback_blueprint_hit_detail_query_becomes_reference():
    plan = build_fallback_query_plan(
        "查询10条用户日志",
        [_blueprint(), _field(), _table()],
    )

    assert plan.query_type == "detail_query"
    assert plan.execution_strategy == "query_graph"
    assert not plan.reference_assets
    rejected_blueprint = next(asset for asset in plan.rejected_assets if asset.asset_type == "blueprint")
    assert rejected_blueprint.name == "个人日报查询"
    assert rejected_blueprint.usage == "rejected"
    assert "不强套日报蓝图" in rejected_blueprint.reject_reason
    assert {factor["code"] for factor in plan.decision_factors} == {
        "detail_query_signal",
        "field_table_coverage",
        "blueprint_rejected_for_detail",
    }
    assert plan.planner_warnings[0]["code"] == "blueprint_rejected_for_detail"


def test_fallback_compares_multiple_blueprint_candidates():
    plan = build_fallback_query_plan(
        "查询张三昨天的个人日报",
        [
            _blueprint(asset_id=1, name="个人日报查询", confidence=0.92),
            _blueprint(asset_id=2, name="团队日报汇总", confidence=0.71),
        ],
        routing={"entities": {"user_name": "张三", "start_date": "2026-06-14"}},
    )

    assert plan.execution_strategy == "blueprint_execute"
    assert plan.selected_assets[0].asset_id == 1
    assert plan.rejected_assets[0].asset_id == 2
    assert "更匹配" in plan.rejected_assets[0].reject_reason
    assert any(
        factor["code"] == "blueprint_candidate_comparison"
        for factor in plan.decision_factors
    )


def test_fallback_does_not_execute_unmatched_blueprint_candidate():
    plan = build_fallback_query_plan(
        "生成销售报告",
        [
            _blueprint(asset_id=1, name="个人日报查询", confidence=0.0),
            _field("amount"),
            _table("sales_orders"),
        ],
    )

    assert plan.execution_strategy != "blueprint_execute"
    assert not any(asset.asset_type == "blueprint" for asset in plan.selected_assets)
    rejected_blueprint = next(asset for asset in plan.rejected_assets if asset.asset_type == "blueprint")
    assert "没有有效匹配信号" in rejected_blueprint.reject_reason


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


def test_query_plan_serializes_asset_detail_audit_fields():
    plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="clarify",
        confidence=0.4,
        planner_source="fallback",
        detail_rounds=3,
        attempted_detail_requests=[{"asset_type": "table", "asset_id": "wide_table"}],
        asset_detail_coverage={"wide_table": "too_large"},
        missing_context=["字段无法定位"],
        why_not_generate_sql="3 轮详情请求后仍缺少可用字段。",
        risk_flags=["wide_table"],
    )

    payload = plan.to_dict()

    assert payload["detail_rounds"] == 3
    assert payload["attempted_detail_requests"][0]["asset_id"] == "wide_table"
    assert payload["asset_detail_coverage"] == {"wide_table": "too_large"}
    assert payload["missing_context"] == ["字段无法定位"]
    assert payload["why_not_generate_sql"] == "3 轮详情请求后仍缺少可用字段。"
    assert payload["risk_flags"] == ["wide_table"]


def test_normalize_query_plan_accepts_asset_detail_audit_fields():
    plan = normalize_query_plan(
        {
            "query_type": "detail_query",
            "execution_strategy": "reject",
            "confidence": 0.2,
            "planner_source": "llm",
            "explanation": {"summary": "上下文不足"},
            "detail_rounds": 3,
            "attempted_detail_requests": [{"asset_type": "table", "asset_id": "wide_table"}],
            "asset_detail_coverage": {"wide_table": "too_large"},
            "missing_context": ["缺少时间字段"],
            "why_not_generate_sql": "无法确定时间字段。",
            "risk_flags": ["wide_table"],
        }
    )

    assert plan.detail_rounds == 3
    assert plan.attempted_detail_requests == [
        {"asset_type": "table", "asset_id": "wide_table"}
    ]
    assert plan.asset_detail_coverage == {"wide_table": "too_large"}
    assert plan.missing_context == ["缺少时间字段"]
    assert plan.why_not_generate_sql == "无法确定时间字段。"
    assert plan.risk_flags == ["wide_table"]
    assert plan.execution_strategy == "reject"


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
        "decision_factors": [
            {"code": "detail_query_signal", "message": "命中明细查询信号。"}
        ],
        "planner_warnings": [
            {"code": "blueprint_reference_only", "message": "蓝图仅作参考。"}
        ],
    }
    fake_llm = FakeLLM(json.dumps(llm_payload, ensure_ascii=False))

    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: fake_llm,
    )

    plan = plan_query(
        db=db_session,
        question="规划一个复杂查询",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": [_blueprint().to_dict(), _field().to_dict(), _table()]},
    )

    assert plan.planner_source == "llm"
    assert plan.execution_strategy == "blueprint_as_reference"
    assert plan.decision_factors[0]["code"] == "detail_query_signal"
    assert plan.planner_warnings[0]["code"] == "blueprint_reference_only"


def test_plan_query_with_detail_context_returns_detail_request_payload(monkeypatch, db_session):
    detail_payload = {
        "asset_detail_requests": [
            {
                "asset_type": "table",
                "asset_id": "user_logs",
                "detail_level": "full_schema",
                "purpose": "sql_generation",
                "reason": "需要字段",
            }
        ]
    }
    fake_llm = FakeLLM(json.dumps(detail_payload, ensure_ascii=False))
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: fake_llm,
    )

    response = plan_query_with_detail_context(
        db=db_session,
        question="查询10条用户日志",
        routing={"route": "dataset_subagent"},
        lightweight_catalog={"assets": [_table("user_logs")]},
        asset_details=[],
        previous_detail_requests=[],
        warnings=[],
    )

    assert response == detail_payload
    assert not isinstance(response, QueryPlan)


def test_plan_query_with_detail_context_prompts_with_asset_details(monkeypatch, db_session):
    final_payload = {
        "query_type": "detail_query",
        "execution_strategy": "query_graph",
        "confidence": 0.82,
        "selected_assets": [_table("user_logs")],
        "planner_source": "llm",
        "explanation": {"summary": "字段详情已足够生成 SQL。"},
    }
    fake_llm = FakeLLM(json.dumps(final_payload, ensure_ascii=False))
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: fake_llm,
    )
    asset_details = [
        {
            "request": {
                "asset_type": "table",
                "asset_id": "user_logs",
                "detail_level": "full_schema",
                "purpose": "sql_generation",
            },
            "coverage": "full",
            "payload": {
                "table_name": "user_logs",
                "fields": [{"name": "created_at", "data_type": "datetime"}],
            },
        }
    ]

    plan = plan_query_with_detail_context(
        db=db_session,
        question="查询10条用户日志",
        routing={"route": "dataset_subagent"},
        lightweight_catalog={"assets": [_table("user_logs")]},
        asset_details=asset_details,
        previous_detail_requests=[asset_details[0]["request"]],
        warnings=[{"code": "wide_table"}],
    )

    prompt_payload = json.loads(fake_llm.messages[1].content)
    assert isinstance(plan, QueryPlan)
    assert prompt_payload["asset_detail_context"][0]["payload"]["table_name"] == "user_logs"
    assert prompt_payload["previous_detail_requests"] == [asset_details[0]["request"]]
    assert prompt_payload["detail_loop_warnings"] == [{"code": "wide_table"}]
    assert any("asset_detail_requests" in rule for rule in prompt_payload["rules"])
    assert "asset_details" not in prompt_payload["multiturn_context"]


def test_plan_query_falls_back_when_llm_raises(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: FakeLLM(exc=RuntimeError("planner down")),
    )

    plan = plan_query(
        db=db_session,
        question="这个数据集支持什么天气预报",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": []},
    )

    assert plan.planner_source == "fallback"
    assert plan.fallback_reason == "planner down"
    assert plan.execution_strategy == "reject"
    assert plan.planner_warnings[0]["code"] == "planner_fallback"
    assert plan.decision_factors


def test_plan_query_falls_back_when_llm_raises_openai_connection_error(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: FakeLLM(exc=FakeOpenAIAPIConnectionError("api connection failed")),
    )

    plan = plan_query(
        db=db_session,
        question="这个数据集支持什么天气预报",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": []},
    )

    assert plan.planner_source == "fallback"
    assert plan.fallback_reason == "api connection failed"
    assert plan.execution_strategy == "reject"


def test_fallback_reject_generates_governance_suggestions():
    plan = build_fallback_query_plan("这个数据集支持什么天气预报")

    assert plan.execution_strategy == "reject"
    assert plan.decision_factors[0]["code"] == "insufficient_assets"
    assert plan.governance_suggestions


def test_plan_query_truncates_long_fallback_reason(monkeypatch, db_session):
    long_reason = "planner down: " + "x" * 500
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: FakeLLM(exc=RuntimeError(long_reason)),
    )

    plan = plan_query(
        db=db_session,
        question="这个数据集支持什么天气预报",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": []},
    )

    assert plan.planner_source == "fallback"
    assert plan.fallback_reason.startswith("planner down: ")
    assert len(plan.fallback_reason) <= 200


def test_plan_query_does_not_swallow_prompt_assembly_errors(monkeypatch, db_session):
    def _broken_prompt(**kwargs):
        raise AssertionError("local prompt bug")

    monkeypatch.setattr(
        "app.services.subagent_planning.planner._planner_human_prompt",
        _broken_prompt,
    )

    try:
        plan_query(
            db=db_session,
            question="这个数据集支持什么天气预报",
            routing={"route": "dataset_subagent"},
            candidate_assets={"assets": []},
        )
    except AssertionError as exc:
        assert str(exc) == "local prompt bug"
    else:
        raise AssertionError("prompt assembly errors should not fallback")


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

    assert plan.planner_source == "deterministic"
    assert plan.execution_strategy == "query_graph"


def test_plan_query_records_llm_generation_with_fallback_metadata(monkeypatch, db_session):
    fake_tracer = FakeTracer()
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_observability_tracer",
        lambda: fake_tracer,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: FakeLLM("not-json"),
    )

    request_context = ObservabilityRequestContext(
        trace_id="trace-test",
        session_id="session-test",
        conversation_id=1,
        dataset_id=10,
        user_id="tester",
        tenant_id="default",
        active=True,
        enabled=True,
    )
    with set_observability_context(request_context):
        plan = plan_query(
            db=db_session,
            question="规划复杂查询",
            routing={"route": "dataset_subagent"},
            candidate_assets={"assets": [_field().to_dict(), _table()]},
        )

    assert plan.planner_source == "fallback"
    assert plan.debug["validation_error"].startswith("Expecting value")
    assert fake_tracer.started_generations[0]["name"] == "llm.subagent_query_planner"
    assert fake_tracer.started_generations[0]["model"] == "fake-planner-model"
    metadata = fake_tracer.ended_generations[0]["metadata"]
    assert metadata["status"] == "fallback"
    assert metadata["fallback_reason"] == plan.fallback_reason
    assert metadata["validation_error"] == plan.debug["validation_error"]
    assert metadata["fallback_execution_strategy"] == "reject"


def test_planner_human_prompt_uses_lightweight_whitelists():
    asset = _blueprint(
        parameters=[
            {"name": "user_name", "required": True},
            {"name": "start_date", "required": True},
        ]
    ).to_dict()
    asset["metadata"].update(
        {
            "sql_template": "SELECT * FROM very_large_template WHERE private_token = 'secret'",
            "ddl": "CREATE TABLE huge_raw_schema(id bigint)",
            "implementation_type": "sql_template",
        }
    )
    asset["match_signals"] = [
        {"type": "keyword", "value": "日报", "score": 0.9, "raw_text": "x" * 1000}
    ]

    prompt = _planner_human_prompt(
        question="查一下日报",
        routing={
            "entry_route": "dataset_subagent",
            "entry_intent": "blueprint_query",
            "dataset_id": 10,
            "matched_manifest": {"manifest_id": "manifest-1", "large_debug": "debug" * 200},
            "raw_trace": "should_not_be_prompted",
        },
        candidate_assets={"assets": [asset]},
        multiturn_context={
            "question_context": "沿用上轮用户",
            "resolved_references": {"用户": "KenYang"},
            "active_filters": [{"field": "date", "value": "today"}],
            "previous_query_summary": "昨天查过日报",
            "messages": [{"role": "user", "content": "full chat history"}],
            "history": ["raw history"],
        },
        lead_agent_context={
            "time_context": {"today": "2026-06-15"},
            "schema_status": "ready",
            "dataset_selection": {"dataset_id": 10},
            "permission_scope": {"allowed": ["user_logs"]},
            "scratchpad": "private reasoning",
        },
    )
    payload = json.loads(prompt)

    assert payload["routing"] == {
        "entry_route": "dataset_subagent",
        "entry_intent": "blueprint_query",
        "dataset_id": 10,
        "matched_manifest": {"manifest_id": "manifest-1"},
    }
    assert payload["multiturn_context"] == {
        "question_context": "沿用上轮用户",
        "resolved_references": {"用户": "KenYang"},
        "active_filters": [{"field": "date", "value": "today"}],
        "previous_query_summary": "昨天查过日报",
    }
    assert payload["lead_agent_context_summary"] == {
        "time_context": {"today": "2026-06-15"},
        "schema_status": "ready",
        "dataset_selection": {"dataset_id": 10},
        "permission_scope": {"allowed": ["user_logs"]},
    }
    assert payload["candidate_assets"][0]["metadata"] == {
        "parameters": [
            {"name": "user_name", "required": True},
            {"name": "start_date", "required": True},
        ],
        "implementation_type": "sql_template",
    }
    assert "sql_template" not in payload["candidate_assets"][0]["metadata"].keys()
    assert "very_large_template" not in prompt
    assert "full chat history" not in prompt
    assert "should_not_be_prompted" not in prompt
    assert "private reasoning" not in prompt


def test_planner_human_prompt_truncates_nested_asset_text():
    long_description = "参数说明" + "长" * 500
    long_signal = "命中信号" + "值" * 500
    long_reason = "匹配原因" + "多" * 500
    long_display_name = "展示名" + "长" * 500
    asset = _blueprint(
        parameters=[
            {
                "name": "user_name",
                "required": True,
                "description": long_description,
                "default": "默认值" + "大" * 500,
            }
        ]
    ).to_dict()
    asset["display_name"] = long_display_name
    asset["match_reason"] = long_reason
    asset["match_signals"] = [{"type": "keyword", "value": long_signal, "score": 0.9}]

    prompt = _planner_human_prompt(
        question="查一下日报",
        routing={"route": "dataset_subagent"},
        candidate_assets={"assets": [asset]},
    )
    prompt_asset = json.loads(prompt)["candidate_assets"][0]

    assert len(prompt_asset["display_name"]) <= 123
    assert len(prompt_asset["match_reason"]) <= 123
    assert len(prompt_asset["match_signals"][0]["value"]) <= 123
    assert len(prompt_asset["metadata"]["parameters"][0]["description"]) <= 123
    assert len(prompt_asset["metadata"]["parameters"][0]["default"]) <= 123
    assert long_description not in prompt
    assert long_signal not in prompt
