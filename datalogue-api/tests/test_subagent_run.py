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
from typing import Any

from app.services.dataset_subagent import DatasetSubAgent
from app.services.runner import DatasetSubAgentRequest
from app.services.subagent_planning import CandidateAsset, QueryPlan


class FakeTraceContext:
    trace_id = "trace-test"


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
    assert events[0].payload["candidate_assets"]["assets"] == []
    assert "context" not in events[0].payload["candidate_assets"]
    assert events[-1].payload["final_state"]["entry_route"] == "clarify"
    assert events[-1].payload["final_state"]["candidate_assets"]["assets"] == []


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
