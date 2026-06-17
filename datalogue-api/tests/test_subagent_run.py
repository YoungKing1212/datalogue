# ============================================================
# File Name   : test_subagent_run.py
# Description:
#   DatasetSubAgent.run 编排层单元测试。
#
# Responsibilities:
#   - 验证候选资产召回、查询规划和策略执行的事件顺序。
#   - 验证 QueryGraph 执行前会注入规划结果、候选资产和蓝图参考上下文。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.dataset_subagent import DatasetSubAgent
from app.services.runner import DatasetSubAgentRequest
from app.services.subagent_planning import CandidateAsset, QueryPlan


class FakeTraceContext:
    trace_id = "trace-test"


class FakeTracer:
    def __init__(self):
        self.started_spans: list[dict[str, Any]] = []
        self.ended_spans: list[dict[str, Any]] = []

    def start_span(self, context, *, node, display_name, input_payload=None, trace_tags=None):
        self.started_spans.append(
            {
                "context": context,
                "node": node,
                "display_name": display_name,
                "input_payload": input_payload or {},
                "trace_tags": trace_tags or [],
            }
        )

    def end_span(self, context, *, node, output_payload=None, elapsed_ms=None, error=None):
        self.ended_spans.append(
            {
                "context": context,
                "node": node,
                "output_payload": output_payload or {},
                "elapsed_ms": elapsed_ms,
                "error": error,
            }
        )


class FakeLLMResponse:
    def __init__(self, content):
        self.content = content


class SequentialFakeLLM:
    def __init__(self, contents):
        self.contents = list(contents)
        self.messages = []
        self.model_name = "fake-planner-model"

    def invoke(self, messages):
        self.messages.append(messages)
        return FakeLLMResponse(self.contents.pop(0))


def _request() -> DatasetSubAgentRequest:
    return DatasetSubAgentRequest(
        question="查询个人日报",
        dataset_id=10,
        manifest_version="manifest-v1",
        bound_schema_version="schema-v1",
        thread_id="thread-1",
        time_context={"today": "2026-06-15"},
        thread_context={},
        route_decision={"decision": "selected", "dataset_id": 10},
        schema_status={},
        lead_agent_context={"time_context": {"today": "2026-06-15"}},
    )


async def _collect(agent: DatasetSubAgent, request: DatasetSubAgentRequest, **kwargs: Any):
    return [
        event
        async for event in agent.run(
            request,
            FakeTraceContext(),
            **kwargs,
        )
    ]


def _empty_recall_result() -> dict[str, Any]:
    return {
        "dataset_id": 10,
        "question": "查询个人日报",
        "assets": [],
        "summary": {
            "blueprint_count": 0,
            "metric_count": 0,
            "dimension_count": 0,
            "term_count": 0,
            "field_count": 0,
            "table_count": 0,
        },
        "recall_debug": {},
        "context": {"schema_context": "schema text"},
    }


def _blueprint_asset(*, usage: str = "candidate") -> CandidateAsset:
    return CandidateAsset(
        asset_type="blueprint",
        asset_id=7,
        name="个人日报查询",
        display_name="个人日报查询",
        source="analysis_blueprint",
        confidence=0.91,
        metadata={
            "description": "按人员和日期查询日报明细。",
            "parameters": [{"name": "person_name", "required": True}],
            "sql_template": "SELECT * FROM daily_report WHERE person_name = :person_name",
        },
        usage=usage,
    )


def _blueprint_recall_result() -> dict[str, Any]:
    return {
        "dataset_id": 10,
        "question": "查询个人日报",
        "assets": [_blueprint_asset().to_dict()],
        "summary": {
            "blueprint_count": 1,
            "metric_count": 0,
            "dimension_count": 0,
            "term_count": 0,
            "field_count": 0,
            "table_count": 0,
        },
        "recall_debug": {},
        "context": {
            "schema_context": "schema text",
            "schema_structured": {"fields": []},
            "ddl_context": "CREATE TABLE daily_report(id int);",
            "query_constraints": {"default_limit": 100},
            "dataset_prompt_instructions": "只能查询当前数据集。",
            "dataset_context_debug": {"dataset_id": 10},
            "datasource_context": {"db_type": "sqlite"},
        },
    }


def _table_schema_recall_result() -> dict[str, Any]:
    table_asset = {
        "asset_type": "table",
        "asset_id": "plan_task_daily_record",
        "name": "plan_task_daily_record",
        "display_name": "计划任务日报记录表",
        "source": "schema",
        "confidence": 0.91,
        "metadata": {"table_name": "plan_task_daily_record", "comment": "个人日报记录"},
    }
    fields = [
        {
            "table_name": "plan_task_daily_record",
            "column_name": "id",
            "data_type": "bigint",
            "column_comment": "主键",
        },
        {
            "table_name": "plan_task_daily_record",
            "column_name": "rzrq",
            "data_type": "date",
            "column_comment": "日志日期",
        },
        {
            "table_name": "plan_task_daily_record",
            "column_name": "account",
            "data_type": "varchar",
            "column_comment": "账号",
        },
        {
            "table_name": "plan_task_daily_record",
            "column_name": "private_salary_shadow",
            "data_type": "decimal",
            "column_comment": "仅用于泄露回灌测试的敏感字段",
        },
    ]
    return {
        "dataset_id": 10,
        "question": "查询个人日报",
        "assets": [table_asset],
        "summary": {
            "blueprint_count": 0,
            "metric_count": 0,
            "dimension_count": 0,
            "term_count": 0,
            "field_count": 0,
            "table_count": 1,
        },
        "recall_debug": {
            "manifest_version": "manifest-v1",
            "bound_schema_version": "schema-v1",
        },
        "context": {
            "schema_context": "schema text",
            "schema_structured": {"fields": fields},
            "datasource_context": {"db_type": "sqlite"},
        },
    }


def test_subagent_run_emits_candidate_assets_and_query_plan(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _empty_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="ambiguous",
            execution_strategy="clarify",
            confidence=0.62,
            clarification={"message": "请补充查询对象。"},
        ),
    )

    events = asyncio.run(_collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=None))

    assert [event.event_type for event in events] == ["candidate_assets", "query_plan", "result"]
    assert events[0].payload["display_name"] == "subagent.candidate_assets"
    assert events[1].payload["display_name"] == "subagent.query_plan"
    assert events[0].payload["candidate_assets"]["assets"] == []
    assert "context" not in events[0].payload["candidate_assets"]
    assert events[-1].payload["final_state"]["entry_route"] == "clarify"
    assert events[-1].payload["final_state"]["candidate_assets"]["assets"] == []


@pytest.mark.asyncio
async def test_dataset_subagent_uses_detail_loop_when_enabled(monkeypatch, db_session):
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.dataset_subagent.get_settings",
        lambda: SimpleNamespace(
            SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED=True,
            SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS=3,
            SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND=5,
            SUBAGENT_PLANNER_FIELD_SEARCH_DEFAULT_TOP_K=30,
            SUBAGENT_PLANNER_FIELD_SEARCH_MAX_TOP_K=50,
            SUBAGENT_PLANNER_TABLE_FULL_FIELD_LIMIT=120,
            SUBAGENT_PLANNER_TABLE_COMPACT_FIELD_LIMIT=300,
        ),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )

    class FakeLoop:
        def __init__(self, *, max_rounds, max_requests_per_round, planner_call, detail_service):
            captured["loop_init"] = {
                "max_rounds": max_rounds,
                "max_requests_per_round": max_requests_per_round,
                "planner_call": planner_call,
                "detail_service": detail_service,
            }

        def run(self, **kwargs):
            captured["loop_run"] = kwargs
            return SimpleNamespace(
                query_plan=QueryPlan(
                    query_type="ambiguous",
                    execution_strategy="clarify",
                    confidence=0.71,
                    clarification={"message": "请补充查询对象。"},
                    asset_detail_coverage={"7": {"coverage": "full"}},
                    risk_flags=["partial_asset_detail"],
                ),
                detail_rounds=1,
                attempted_detail_requests=[
                    {"asset_type": "table", "asset_id": 7, "detail_type": "full"}
                ],
                warnings=[{"code": "detail_warning", "message": "测试告警"}],
                sql_generation_context={"coverage": {}},
            )

    monkeypatch.setattr("app.services.dataset_subagent.PlannerDetailLoop", FakeLoop)

    events = await _collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=None)

    assert [event.event_type for event in events] == [
        "candidate_assets",
        "asset_detail",
        "query_plan",
        "result",
    ]
    assert captured["loop_init"]["max_rounds"] == 3
    assert captured["loop_init"]["max_requests_per_round"] == 5
    assert captured["loop_init"]["planner_call"].__name__ == "plan_query_with_detail_context"
    assert captured["loop_init"]["detail_service"].field_search_default_top_k == 30
    assert captured["loop_run"]["candidate_assets"]["context"]["schema_context"] == "schema text"

    asset_detail_payload = events[1].payload
    assert asset_detail_payload["display_name"] == "subagent.asset_detail"
    assert asset_detail_payload["detail_rounds"] == 1
    assert asset_detail_payload["requested_count"] == 1
    assert asset_detail_payload["coverage"] == {"7": {"coverage": "full"}}
    assert asset_detail_payload["risk_flags"] == ["partial_asset_detail"]
    assert asset_detail_payload["warnings"] == [{"code": "detail_warning", "message": "测试告警"}]

    final_state = events[-1].payload["final_state"]
    assert final_state["candidate_assets"]["summary"]["blueprint_count"] == 1
    assert final_state["sql_generation_context"] == {"coverage": {}}


@pytest.mark.asyncio
async def test_dataset_subagent_detail_loop_hydrates_table_schema_contract(
    monkeypatch, db_session
):
    captured: dict[str, Any] = {}
    detail_request_payload = {
        "asset_detail_requests": [
            {
                "asset_type": "table",
                "asset_id": "plan_task_daily_record",
                "detail_level": "full_schema",
                "purpose": "sql_generation",
                "reason": "需要字段",
            }
        ]
    }
    final_plan_payload = {
        "query_type": "detail_query",
        "execution_strategy": "query_graph",
        "confidence": 0.86,
        "selected_assets": [
            {
                "asset_type": "table",
                "asset_id": "plan_task_daily_record",
                "name": "plan_task_daily_record",
                "display_name": "计划任务日报记录表",
                "source": "schema",
                "confidence": 0.91,
                "metadata": {
                    "table_name": "plan_task_daily_record",
                    "fields": [{"name": "private_salary_shadow"}],
                    "sql_template": "SELECT * FROM secret_table",
                    "expr": "private_salary_shadow > 0",
                    "asset_detail_context": {"payload": {"fields": ["private_salary_shadow"]}},
                },
            }
        ],
        "planner_source": "llm",
        "explanation": {
            "summary": "fields: private_salary_shadow; sql_template: SELECT * FROM secret_table",
            "payload": {"fields": [{"name": "private_salary_shadow"}]},
        },
        "planner_warnings": [
            {
                "code": "echo",
                "message": "sql_template: SELECT * FROM secret_table",
                "expr": "private_salary_shadow > 0",
            }
        ],
        "debug": {
            "asset_detail_context": {"payload": {"fields": ["private_salary_shadow"]}},
            "safe_note": "保留短说明",
        },
    }
    fake_llm = SequentialFakeLLM(
        [
            json.dumps(detail_request_payload, ensure_ascii=False),
            json.dumps(final_plan_payload, ensure_ascii=False),
        ]
    )

    monkeypatch.setattr(
        "app.services.dataset_subagent.get_settings",
        lambda: SimpleNamespace(
            SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED=True,
            SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS=3,
            SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND=5,
            SUBAGENT_PLANNER_FIELD_SEARCH_DEFAULT_TOP_K=30,
            SUBAGENT_PLANNER_FIELD_SEARCH_MAX_TOP_K=50,
            SUBAGENT_PLANNER_TABLE_FULL_FIELD_LIMIT=120,
            SUBAGENT_PLANNER_TABLE_COMPACT_FIELD_LIMIT=300,
        ),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _table_schema_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.subagent_planning.planner.get_llm",
        lambda temperature=0.0, **kwargs: fake_llm,
    )

    class FakeRunner:
        def __init__(self, graph, db):
            pass

        async def run(self, request, trace_context, initial_state, **kwargs):
            captured["initial_state"] = initial_state
            yield {"event": "on_chain_end", "data": {"output": {"answer": "完成"}}}

    monkeypatch.setattr(
        "app.services.dataset_subagent.InProcessDatasetSubAgentRunner",
        FakeRunner,
    )

    events = await _collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=object())

    asset_detail_event = next(event for event in events if event.event_type == "asset_detail")
    query_plan_event = next(event for event in events if event.event_type == "query_plan")
    final_state = events[-1].payload["final_state"]
    table_schemas = final_state["sql_generation_context"]["table_schemas"]
    query_plan_text = json.dumps(query_plan_event.payload["query_plan"], ensure_ascii=False)
    initial_plan_text = json.dumps(captured["initial_state"]["query_plan"], ensure_ascii=False)

    assert asset_detail_event.payload["requested_count"] > 0
    assert table_schemas[0]["table_name"] == "plan_task_daily_record"
    assert [field["name"] for field in table_schemas[0]["fields"]] == [
        "id",
        "rzrq",
        "account",
        "private_salary_shadow",
    ]
    assert "private_salary_shadow" in json.dumps(table_schemas, ensure_ascii=False)
    for leaked_text in ("private_salary_shadow", "SELECT * FROM secret_table"):
        assert leaked_text not in query_plan_text
        assert leaked_text not in initial_plan_text
    assert query_plan_event.payload["query_plan"]["selected_assets"][0]["metadata"] == {
        "schema_version": "schema-v1",
        "manifest_version": "manifest-v1",
    }
    assert query_plan_event.payload["query_plan"]["debug"] == {"safe_note": "保留短说明"}
    assert captured["initial_state"]["sql_generation_context"]["table_schemas"] == table_schemas
    assert len(fake_llm.messages) == 2
    second_prompt = json.loads(fake_llm.messages[1][1].content)
    assert second_prompt["asset_detail_context"][0]["payload"]["table_name"] == (
        "plan_task_daily_record"
    )


@pytest.mark.asyncio
async def test_dataset_subagent_keeps_direct_planner_when_detail_loop_disabled(
    monkeypatch, db_session
):
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.dataset_subagent.get_settings",
        lambda: SimpleNamespace(SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED=False),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )

    def fake_plan_query(**kwargs):
        captured["plan_query"] = kwargs
        return QueryPlan(
            query_type="ambiguous",
            execution_strategy="clarify",
            confidence=0.62,
            clarification={"message": "请补充查询对象。"},
        )

    class UnexpectedLoop:
        def __init__(self, *args, **kwargs):
            raise AssertionError("detail loop should stay disabled")

    monkeypatch.setattr("app.services.dataset_subagent.plan_query", fake_plan_query)
    monkeypatch.setattr("app.services.dataset_subagent.PlannerDetailLoop", UnexpectedLoop)

    events = await _collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=None)

    assert [event.event_type for event in events] == ["candidate_assets", "query_plan", "result"]
    assert captured["plan_query"]["candidate_assets"]["summary"]["blueprint_count"] == 1
    assert "context" not in captured["plan_query"]["candidate_assets"]
    assert "asset_detail" not in [event.event_type for event in events]
    assert "sql_generation_context" not in events[-1].payload["final_state"]


def test_subagent_run_records_candidate_assets_and_query_plan_spans(monkeypatch, db_session):
    fake_tracer = FakeTracer()
    monkeypatch.setattr(
        "app.services.dataset_subagent.get_observability_tracer",
        lambda: fake_tracer,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="blueprint_query",
            execution_strategy="clarify",
            confidence=0.51,
            fallback_reason="planner validation failed",
            planner_source="fallback",
            decision_factors=[{"code": "missing_required_input"}],
            planner_warnings=[{"code": "fallback_used"}],
            governance_suggestions=[{"code": "complete_blueprint_params"}],
            debug={"validation_error": "blueprint_execute cannot include required_inputs"},
            clarification={"message": "请补充用户和日期。"},
        ),
    )

    events = asyncio.run(_collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=None))

    assert events[-1].event_type == "result"
    assert [span["node"] for span in fake_tracer.started_spans] == [
        "subagent.candidate_assets",
        "subagent.query_plan",
    ]
    assert [span["display_name"] for span in fake_tracer.started_spans] == [
        "subagent.candidate_assets",
        "subagent.query_plan",
    ]
    ended_by_node = {span["node"]: span for span in fake_tracer.ended_spans}
    assert ended_by_node["subagent.candidate_assets"]["output_payload"]["summary"]["blueprint_count"] == 1
    query_plan_output = ended_by_node["subagent.query_plan"]["output_payload"]
    assert query_plan_output["execution_strategy"] == "clarify"
    assert query_plan_output["fallback_reason"] == "planner validation failed"
    assert query_plan_output["validation_error"] == "blueprint_execute cannot include required_inputs"
    assert query_plan_output["decision_factors"] == [{"code": "missing_required_input"}]


def test_subagent_run_blueprint_reference_marks_context_and_query_graph(monkeypatch, db_session):
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="blueprint_as_reference",
            confidence=0.83,
            reference_assets=[_blueprint_asset(usage="reference")],
        ),
    )

    class FakeRunner:
        def __init__(self, graph, db):
            captured["graph"] = graph
            captured["db"] = db

        async def run(self, request, trace_context, initial_state, **kwargs):
            captured["request"] = request
            captured["trace_context"] = trace_context
            captured["initial_state"] = initial_state
            captured["kwargs"] = kwargs
            yield {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "answer": "已完成查询。",
                        "sql": "SELECT * FROM daily_report",
                        "sql_list": ["SELECT * FROM daily_report"],
                    }
                },
            }

    monkeypatch.setattr(
        "app.services.dataset_subagent.InProcessDatasetSubAgentRunner",
        FakeRunner,
    )

    events = asyncio.run(
        _collect(
            DatasetSubAgent(db=db_session, dataset_id=10),
            _request(),
            graph=object(),
            initial_state={"question": "查询10条个人日报"},
            graph_kwargs={"version": "v2"},
        )
    )

    final_result = events[-1].payload["final_state"]
    initial_state = captured["initial_state"]

    assert events[-1].event_type == "result"
    assert final_result["answer"] == "已完成查询。"
    assert initial_state["query_plan"]["execution_strategy"] == "blueprint_as_reference"
    assert initial_state["candidate_assets"]["summary"]["blueprint_count"] == 1
    assert "context" not in initial_state["candidate_assets"]
    assert "只能作为参考证据" in initial_state["blueprint_context"]
    assert "不能原样执行" in initial_state["dataset_prompt_instructions"]
    assert captured["kwargs"] == {"version": "v2"}


def test_subagent_run_uses_request_task_capsule_when_initial_state_missing(monkeypatch, db_session):
    captured: dict[str, Any] = {}
    capsule = {
        "turn_type": "followup",
        "base_task_ref": {"task_id": "task-1"},
        "base_main_table": "plan_task_daily_record",
        "standalone_question": "查询杨凯最近7天的个人日报",
        "base_question": "查询杨凯的个人日报",
    }
    turn_event = {"event_id": "turn-2", "turn_type": "followup"}
    request = DatasetSubAgentRequest(
        **(_request().__dict__ | {"query_task_capsule": capsule, "turn_event": turn_event})
    )

    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.77,
        ),
    )

    class FakeRunner:
        def __init__(self, graph, db):
            pass

        async def run(self, request, trace_context, initial_state, **kwargs):
            captured["initial_state"] = initial_state
            yield {"event": "on_chain_end", "data": {"output": {"answer": "完成"}}}

    monkeypatch.setattr(
        "app.services.dataset_subagent.InProcessDatasetSubAgentRunner",
        FakeRunner,
    )

    events = asyncio.run(
        _collect(
            DatasetSubAgent(db=db_session, dataset_id=10),
            request,
            graph=object(),
        )
    )

    initial_state = captured["initial_state"]
    assert events[-1].event_type == "result"
    assert initial_state["query_task_capsule"] == capsule
    assert initial_state["turn_event"] == turn_event
    assert initial_state["question"] == "查询杨凯最近7天的个人日报"
    assert initial_state["original_question"] == "查询个人日报"


def test_subagent_run_preserves_existing_task_capsule_over_request(monkeypatch, db_session):
    captured: dict[str, Any] = {}
    request_capsule = {
        "turn_type": "followup",
        "base_task_ref": {"task_id": "request-task"},
        "standalone_question": "请求里的独立问题",
        "base_question": "请求里的原始问题",
    }
    existing_capsule = {
        "turn_type": "refine",
        "base_task_ref": {"task_id": "state-task"},
        "base_main_table": "existing_table",
        "standalone_question": "已有状态里的独立问题",
        "base_question": "已有状态里的原始问题",
    }
    existing_turn_event = {"event_id": "state-turn"}
    request = DatasetSubAgentRequest(
        **(
            _request().__dict__
            | {"query_task_capsule": request_capsule, "turn_event": {"event_id": "request-turn"}}
        )
    )

    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.77,
        ),
    )

    class FakeRunner:
        def __init__(self, graph, db):
            pass

        async def run(self, request, trace_context, initial_state, **kwargs):
            captured["initial_state"] = initial_state
            yield {"event": "on_chain_end", "data": {"output": {"answer": "完成"}}}

    monkeypatch.setattr(
        "app.services.dataset_subagent.InProcessDatasetSubAgentRunner",
        FakeRunner,
    )

    asyncio.run(
        _collect(
            DatasetSubAgent(db=db_session, dataset_id=10),
            request,
            graph=object(),
            initial_state={
                "question": "初始问题",
                "query_task_capsule": existing_capsule,
                "turn_event": existing_turn_event,
            },
        )
    )

    initial_state = captured["initial_state"]
    assert initial_state["query_task_capsule"] == existing_capsule
    assert initial_state["turn_event"] == existing_turn_event
    assert initial_state["question"] == "已有状态里的独立问题"
    assert initial_state["original_question"] == "初始问题"


def test_subagent_run_unwraps_node_output_before_merging(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.77,
        ),
    )

    class FakeRunner:
        def __init__(self, graph, db):
            pass

        async def run(self, request, trace_context, initial_state, **kwargs):
            yield {
                "event": "on_chain_end",
                "metadata": {"langgraph_node": "dsl_generate"},
                "data": {
                    "output": {
                        "dsl_generate": {
                            "answer": "完成",
                            "sql": "select 1",
                        }
                    }
                },
            }

    monkeypatch.setattr(
        "app.services.dataset_subagent.InProcessDatasetSubAgentRunner",
        FakeRunner,
    )

    events = asyncio.run(
        _collect(
            DatasetSubAgent(db=db_session, dataset_id=10),
            _request(),
            graph=object(),
        )
    )

    final_state = events[-1].payload["final_state"]

    assert final_state["answer"] == "完成"
    assert final_state["sql"] == "select 1"
    assert "dsl_generate" not in final_state


def test_subagent_run_blueprint_execute_uses_reference_blueprint_id(monkeypatch, db_session):
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="blueprint_query",
            execution_strategy="blueprint_execute",
            confidence=0.88,
            reference_assets=[_blueprint_asset(usage="reference")],
        ),
    )

    def fake_resolve(self, **kwargs):
        captured.update(kwargs)
        return {
            "status": "executed",
            "blueprint_id": kwargs["blueprint_id"],
            "blueprint_name": "个人日报查询",
            "answer": None,
            "sql": "select 1",
            "sql_list": ["select 1"],
            "sql_result": {"columns": ["value"], "rows": [[1]], "row_count": 1},
            "error": None,
            "route_payload": {"kind": "analysis_blueprint", "blueprint_id": kwargs["blueprint_id"]},
            "should_retry": False,
            "generation_mode": "analysis_blueprint",
        }

    monkeypatch.setattr(DatasetSubAgent, "resolve_analysis_blueprint", fake_resolve)

    events = asyncio.run(
        _collect(
            DatasetSubAgent(db=db_session, dataset_id=10),
            _request(),
            graph=None,
            initial_state={"question": "查询个人日报"},
        )
    )

    final_state = events[-1].payload["final_state"]

    assert captured["blueprint_id"] == 7
    assert final_state["blueprint_id"] == 7
    assert final_state["sql"] == "select 1"


def test_subagent_run_blueprint_execute_merges_routing_params(monkeypatch, db_session):
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _blueprint_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="blueprint_query",
            execution_strategy="blueprint_execute",
            confidence=0.9,
            reference_assets=[_blueprint_asset(usage="reference")],
        ),
    )

    def fake_resolve(self, **kwargs):
        captured.update(kwargs)
        input_params = kwargs.get("input_params") or {}
        missing = [key for key in ("user_name", "start_date") if not input_params.get(key)]
        if missing:
            return {
                "status": "clarification",
                "blueprint_id": kwargs["blueprint_id"],
                "blueprint_name": "个人日报查询",
                "answer": "缺少参数",
                "sql": None,
                "sql_list": [],
                "sql_result": None,
                "error": "缺少参数",
                "route_payload": {"kind": "clarification", "missing": missing},
                "should_retry": False,
                "generation_mode": None,
            }
        return {
            "status": "executed",
            "blueprint_id": kwargs["blueprint_id"],
            "blueprint_name": "个人日报查询",
            "answer": None,
            "sql": "select 1",
            "sql_list": ["select 1"],
            "sql_result": {"columns": ["value"], "rows": [[1]], "row_count": 1},
            "error": None,
            "route_payload": {
                "kind": "analysis_blueprint",
                "blueprint_id": kwargs["blueprint_id"],
                "params": input_params,
            },
            "should_retry": False,
            "generation_mode": "analysis_blueprint",
        }

    monkeypatch.setattr(DatasetSubAgent, "resolve_analysis_blueprint", fake_resolve)

    events = asyncio.run(
        _collect(
            DatasetSubAgent(db=db_session, dataset_id=10),
            _request(),
            graph=None,
            initial_state={
                "question": "查询 KenYang 2026-06-01 的个人日报",
                "entities": {"user_name": "KenYang", "start_date": "2026-06-01"},
                "route_payload": {
                    "kind": "analysis_blueprint",
                    "params": {"user_name": "route-user", "start_date": "2026-01-01"},
                },
            },
        )
    )

    final_state = events[-1].payload["final_state"]

    assert final_state["blueprint_outcome_status"] == "executed"
    assert final_state["route_payload"]["params"]["user_name"] == "KenYang"
    assert final_state["route_payload"]["params"]["start_date"] == "2026-06-01"
    assert captured["input_params"]["user_name"] == "KenYang"
    assert captured["input_params"]["start_date"] == "2026-06-01"


def test_subagent_run_query_graph_requires_graph(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _empty_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.7,
        ),
    )

    try:
        asyncio.run(_collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=None))
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("query_graph without graph should raise ValueError")

    assert "query_graph" in message
    assert "dataset_id=10" in message


def test_subagent_run_reject_result_is_not_error(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.dataset_subagent.recall_candidate_assets",
        lambda *args, **kwargs: _empty_recall_result(),
    )
    monkeypatch.setattr(
        "app.services.dataset_subagent.plan_query",
        lambda **kwargs: QueryPlan(
            query_type="unsupported",
            execution_strategy="reject",
            confidence=0.24,
            explanation={"summary": "当前数据集不支持该类问题。"},
        ),
    )

    events = asyncio.run(_collect(DatasetSubAgent(db=db_session, dataset_id=10), _request(), graph=None))
    final_state = events[-1].payload["final_state"]

    assert final_state["entry_route"] == "reject"
    assert final_state["error"] is None
    assert final_state["answer"] == "当前数据集不支持该类问题。"
