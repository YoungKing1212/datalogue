# ============================================================
# File Name   : test_as_r0_atomic_runtime_cutover.py
# Description:
#   AS-R0 PR1.3-b BI atomic runtime 直接接管测试。
#
# Responsibilities:
#   - 验证单数据集 BI 查询默认绕过 legacy LangGraph 执行核心。
#   - 验证 atomic runtime 的结果仍复用现有 /chat/stream final、artifact、trace 收口契约。
#   - 验证用户可见 SSE 不暴露 SQL、schema、raw rows 或 query_plan 主体。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from app.schemas.chat import ChatRequest
from app.services.multiturn_context import MergeDecision


def test_dataset_runtime_direct_entry_bypasses_lead_agent_and_legacy_graph(
    db_session,
    sample_dataset,
    monkeypatch,
):
    """DatasetAgent Runtime 直通测试入口不能触发 LeadAgent 或 legacy graph。"""

    from app.api import chat as chat_api

    class FakeAtomicRuntime:
        def __init__(self, *, provider, dsl_generator):
            self.provider = provider
            self.dsl_generator = dsl_generator

        def run_query(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["dataset_id"] == sample_dataset.id
            assert kwargs["question"] == "查询 GMV"
            return {
                "status": "completed",
                "artifact_ref": "artifact:direct-runtime",
                "artifact_summary": {"artifact_ref": "artifact:direct-runtime"},
                "row_count": 1,
                "column_count": 1,
                "tool_calls": [
                    {"name": "get_dataset_status", "status": "active"},
                    {"name": "list_candidate_assets", "status": "ready"},
                    {"name": "generate_dsl", "status": "generated"},
                    {"name": "compile_dsl_to_sql", "status": "compiled"},
                    {"name": "execute_compiled_query", "status": "completed"},
                    {"name": "get_artifact_summary", "status": "ready"},
                ],
            }

    monkeypatch.setattr(
        chat_api,
        "build_lead_agent_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("LeadAgent must not run in direct DatasetAgent Runtime test entry")
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "route_query_intent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("route_query_intent must not run in direct DatasetAgent Runtime test entry")
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "build_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy graph must not run in direct DatasetAgent Runtime test entry")
        ),
    )
    monkeypatch.setattr(chat_api, "DatasetAgentToolCallRuntime", FakeAtomicRuntime, raising=False)

    result = chat_api.dataset_runtime_direct(
        ChatRequest(question="查询 GMV", dataset_id=sample_dataset.id),
        db_session,
    )

    assert result["status"] == "completed"
    assert result["artifact_ref"] == "artifact:direct-runtime"
    assert result["row_count"] == 1
    assert result["column_count"] == 1
    assert [item["name"] for item in result["tool_calls"]] == [
        "get_dataset_status",
        "list_candidate_assets",
        "generate_dsl",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "get_artifact_summary",
    ]


@pytest.mark.asyncio
async def test_chat_stream_atomic_runtime_bypasses_legacy_graph_core_without_flag(
    db_session,
    sample_dataset,
    monkeypatch,
    caplog,
):
    """PR1.3-b: BI 查询执行核心应默认走 AgentScope-owned atomic runtime。"""

    from app.api import chat as chat_api

    class Settings:
        MULTITURN_ENABLED = False
        MULTITURN_REFINEMENT_FAST_PATH_ENABLED = False
        MULTITURN_RESULT_LOCAL_FILTER_ENABLED = False
        MULTITURN_SQL_AST_PATCH_ENABLED = False
        MULTITURN_ARTIFACT_CACHE_TTL_SECONDS = 1800
        LEAD_AGENT_ENABLE_DATASET_FANOUT = False
        AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED = False

    class FakeAtomicRuntime:
        def __init__(self, *, provider, dsl_generator):
            self.provider = provider
            self.dsl_generator = dsl_generator

        def run_query(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["dataset_id"] == sample_dataset.id
            assert kwargs["question"] == "查询 GMV"
            return {
                "status": "completed",
                "artifact_ref": "artifact:atomic-result",
                "artifact_summary": {
                    "artifact_ref": "artifact:atomic-result",
                    "kind": "sql_result",
                    "size_bytes": 128,
                },
                "row_count": 2,
                "column_count": 1,
                "tool_calls": [
                    {"name": "get_dataset_status", "status": "active"},
                    {"name": "list_candidate_assets", "status": "ready"},
                    {"name": "generate_dsl", "status": "generated"},
                    {"name": "compile_dsl_to_sql", "status": "compiled"},
                    {"name": "execute_compiled_query", "status": "completed"},
                    {"name": "get_artifact_summary", "status": "ready"},
                ],
            }

    def fake_build_workflow(_db):
        raise AssertionError("legacy LangGraph core must not run for BI query main chain")

    def fake_lead_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "should_continue": True,
            "effective_dataset_id": sample_dataset.id,
            "resolved_question": "查询 GMV",
            "route_decision": {
                "decision": "selected",
                "dataset_id": sample_dataset.id,
                "dataset_name": sample_dataset.name,
                "reason": "test_selected_dataset",
            },
            "schema_status": {"status": "ok"},
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "policy_violations": [],
            "time_context": {},
            "thread_context": {},
            "audit_trace": {},
        }

    def fake_route_query_intent(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "detail_query",
            "entities": {},
            "entry_intent": "detail_query",
            "entry_route": "query_graph",
            "entry_reason": "test_query_graph",
            "route_payload": {},
        }

    monkeypatch.setattr(chat_api, "get_settings", lambda: Settings())
    monkeypatch.setattr(chat_api, "build_workflow", fake_build_workflow)
    monkeypatch.setattr(chat_api, "build_lead_agent_context", fake_lead_context)
    monkeypatch.setattr(
        chat_api,
        "merge_multiturn_decision_for_chat",
        lambda **_kwargs: MergeDecision(turn_type="new_query", multiturn_context={}, merge_debug={}),
    )
    monkeypatch.setattr(
        chat_api,
        "resolve_term_clarification",
        lambda *_args, **_kwargs: {"status": "none"},
    )
    monkeypatch.setattr(chat_api, "route_query_intent", fake_route_query_intent)
    monkeypatch.setattr(chat_api, "DatasetAgentToolCallRuntime", FakeAtomicRuntime, raising=False)

    with caplog.at_level(logging.INFO, logger="app.api.chat"):
        parsed_events = [
            json.loads(event["data"])
            async for event in chat_api._stream_chat_singleturn(
                ChatRequest(question="查询 GMV", dataset_id=sample_dataset.id),
                db_session,
            )
        ]

    final_events = [event for event in parsed_events if event.get("type") == "final"]
    assert final_events
    final_payload = final_events[-1]
    assert final_payload["answer"] == "Atomic runtime 查询完成，共返回 2 行、1 列。"
    assert final_payload["entry_route"] == "query_graph"
    assert final_payload["result_ref"] == "artifact:atomic-result"
    assert final_payload["trace_id"]
    assert any(
        (event.get("event_envelope") or {}).get("event_type") == "dataset.query.completed"
        for event in parsed_events
    )

    visible_dump = repr(
        [
            (event.get("event_envelope") or {}).get("payload")
            for event in parsed_events
            if (event.get("event_envelope") or {}).get("visibility") == "user_visible"
        ]
    )
    for forbidden in ("SELECT ", "sql_preview", "schema", "raw_rows", "query_plan", "RepairPatch"):
        assert forbidden.lower() not in visible_dump.lower()

    backend_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[chat.stream.dataset_agent_runtime_start]" in backend_logs
    assert "[chat.stream.dataset_agent_runtime_completed]" in backend_logs
    for legacy_term in ("legacy LangGraph", "build_workflow", "DatasetSubAgent"):
        assert legacy_term.lower() not in backend_logs.lower()
