# ============================================================
# File Name   : test_retry_checkpoint.py
# Description:
#   Retry checkpoint 受控恢复测试。
#
# Responsibilities:
#   - 验证安全 checkpoint 的注册、权限校验和过期降级。
#   - 验证 chat stream retry 事件不暴露 SQL、schema 或 control_plane。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import models
from app.schemas.chat import ChatRequest
from app.services.conversation_store import ConversationStore


def _collect_event_types(events):
    return [event.get("type") for event in events]


def _fake_subagent_class(captured_states):
    from app.services.subagent_planning import SubAgentEvent

    class FakeSubAgent:
        def __init__(self, db, dataset_id):
            self.db = db
            self.dataset_id = dataset_id

        def resolve_term_conflict(self, **kwargs):
            return {"status": "not_applicable"}

        def resolve_metric(self, **kwargs):
            return {"status": "not_applicable"}

        def resolve_analysis_blueprint(self, **kwargs):
            return {"status": "not_applicable"}

        async def run(self, request, trace_context, *, graph, initial_state=None, graph_kwargs=None):
            captured_states.append(initial_state or {})
            async for event in graph.astream_events(initial_state or {}, "v2"):
                yield SubAgentEvent(event_type="graph_event", payload={"event": event})

    return FakeSubAgent


def test_retry_checkpoint_restores_safe_context_without_internal_leakage(
    db_session,
    sample_dataset,
):
    """query_context_ready checkpoint 只能恢复业务上下文，不能把 SQL/schema/control_plane 暴露给 retry。"""
    store = ConversationStore(db_session)
    session_id = "retry-safe-context"
    conversation = models.Conversation(title="重试测试", user_id=1, dataset_id=sample_dataset.id)
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    store.load_or_create(session_id=session_id, user_id="1")

    checkpoint_ref = store.register_retry_checkpoint(
        session_id=session_id,
        checkpoint_kind="query_context_ready",
        user_id="1",
        conversation_id=conversation.id,
        task_id="task-1",
        permission_scope=f"dataset:{sample_dataset.id}",
        context={
            "question": "最近30日GMV趋势如何",
            "dataset_id": sample_dataset.id,
            "route_decision": {"dataset_id": sample_dataset.id, "decision": "selected"},
            "query_plan": {"query_type": "metric_query", "debug": {"raw_sql": "SELECT * FROM orders"}},
            "control_plane": {"schema": {"tables": ["orders"]}},
            "sql": "SELECT * FROM orders",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    restored = store.restore_retry_checkpoint(
        checkpoint_ref,
        user_id="1",
        conversation_id=conversation.id,
    )

    assert checkpoint_ref == "checkpoint://task-1/query_context_ready"
    assert restored.retry_scope == "last_safe_checkpoint"
    assert restored.dataset_id == sample_dataset.id
    assert restored.question == "最近30日GMV趋势如何"
    serialized = json.dumps(restored.context, ensure_ascii=False)
    assert "raw_sql" not in serialized
    assert "SELECT" not in serialized
    assert "schema" not in serialized
    assert "control_plane" not in serialized


def test_retry_checkpoint_rejects_unsafe_or_expired_refs(db_session, sample_dataset):
    """非法 kind、过期和用户不匹配都必须 fail closed，调用方再降级整任务重试。"""
    store = ConversationStore(db_session)
    session_id = "retry-invalid"
    conversation = models.Conversation(title="重试测试", user_id=1, dataset_id=sample_dataset.id)
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    store.load_or_create(session_id=session_id, user_id="1")

    with pytest.raises(ValueError, match="unsafe retry checkpoint"):
        store.register_retry_checkpoint(
            session_id=session_id,
            checkpoint_kind="sql_generated",
            user_id="1",
            conversation_id=conversation.id,
            task_id="task-unsafe",
            permission_scope=f"dataset:{sample_dataset.id}",
            context={"question": "查询GMV", "dataset_id": sample_dataset.id},
        )

    checkpoint_ref = store.register_retry_checkpoint(
        session_id=session_id,
        checkpoint_kind="dataset_confirmed",
        user_id="1",
        conversation_id=conversation.id,
        task_id="task-expired",
        permission_scope=f"dataset:{sample_dataset.id}",
        context={"question": "查询GMV", "dataset_id": sample_dataset.id},
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    restored = store.restore_retry_checkpoint(
        checkpoint_ref,
        user_id="1",
        conversation_id=conversation.id,
    )

    assert restored.retry_scope == "whole_task"
    assert restored.fallback_reason == "checkpoint_expired"


@pytest.mark.asyncio
async def test_stream_retry_restores_checkpoint_and_emits_retry_events(
    db_session,
    sample_dataset,
    monkeypatch,
):
    """chat stream retry 成功时恢复 checkpoint，并发出 retry.started/restored/completed。"""
    from app.api.chat import _stream_chat

    class MultiturnSettings:
        MULTITURN_ENABLED = True
        MULTITURN_LOCK_TTL_SECONDS = 300
        MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS = 2000
        MULTITURN_COMPACTION_ENABLED = False

    monkeypatch.setattr("app.api.chat.get_settings", lambda: MultiturnSettings())
    store = ConversationStore(db_session)
    session_id = "retry-stream"
    conversation = models.Conversation(title="重试测试", user_id=1, dataset_id=sample_dataset.id)
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    store.load_or_create(session_id=session_id, user_id="1")
    checkpoint_ref = store.register_retry_checkpoint(
        session_id=session_id,
        checkpoint_kind="query_context_ready",
        user_id="1",
        conversation_id=conversation.id,
        task_id="task-stream",
        permission_scope=f"dataset:{sample_dataset.id}",
        context={
            "question": "最近30日GMV趋势如何",
            "dataset_id": sample_dataset.id,
            "route_decision": {"dataset_id": sample_dataset.id, "decision": "selected"},
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    captured_states = []

    async def fake_astream_events(state, version):
        yield {
            "event": "on_chain_end",
            "name": "report_generator",
            "data": {
                "output": {
                    **state,
                    "answer": "重试完成",
                    "query_plan": {"query_type": "metric_query", "execution_strategy": "query_graph"},
                    "dsl": {"metrics": [{"name": "gmv"}]},
                    "sql": "SELECT 1",
                    "sql_list": ["SELECT 1"],
                    "sql_result": {"columns": ["one"], "rows": [{"one": 1}], "row_count": 1},
                    "error": None,
                }
            },
            "metadata": {"langgraph_node": "report_generator"},
        }

    with (
        patch("app.api.chat.build_workflow") as mock_wf,
        patch("app.api.chat.DatasetSubAgent", _fake_subagent_class(captured_states)),
        patch(
            "app.api.chat.build_lead_agent_context",
            return_value={
                "route_decision": {"decision": "selected", "dataset_id": sample_dataset.id},
                "effective_dataset_id": sample_dataset.id,
                "should_continue": True,
                "resolved_question": "最近30日GMV趋势如何",
                "time_context": {},
                "thread_context": {},
                "schema_status": {"status": "ok", "structured": {"terms": []}},
                "selected_skills": [],
                "planned_tool_calls": [],
                "executed_tool_calls": [],
                "policy_violations": [],
                "audit_trace": {},
                "multiturn_classification": {},
            },
        ),
        patch("app.api.chat.resolve_term_clarification", return_value={"status": "none"}),
        patch(
            "app.api.chat.route_query_intent",
            return_value={
                "intent": "query",
                "entities": {},
                "entry_intent": "metric_query",
                "entry_route": "query_graph",
                "entry_reason": "测试进入查询图",
                "route_payload": {"kind": "query_graph"},
            },
        ),
    ):
        mock_graph = MagicMock()
        mock_graph.astream_events = fake_astream_events
        mock_wf.return_value = mock_graph
        events = [
            json.loads(item["data"])
            async for item in _stream_chat(
                ChatRequest(
                    question="重试",
                    session_id=session_id,
                    conversation_id=conversation.id,
                    retry_checkpoint_ref=checkpoint_ref,
                ),
                db_session,
            )
        ]

    assert "retry.started" in _collect_event_types(events)
    assert "retry.checkpoint_restored" in _collect_event_types(events)
    assert "retry.completed" in _collect_event_types(events)
    assert captured_states[-1]["original_question"] == "最近30日GMV趋势如何"
    assert captured_states[-1]["dataset_id"] == sample_dataset.id
    assert [event for event in events if event.get("type") == "retry.checkpoint_restored"][-1][
        "checkpoint_ref"
    ] == checkpoint_ref
