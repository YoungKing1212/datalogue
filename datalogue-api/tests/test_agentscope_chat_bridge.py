# ============================================================
# File Name   : test_agentscope_chat_bridge.py
# Description:
#   C3 AgentScope Chat Bridge 服务测试。
#
# Responsibilities:
#   - 验证新 Chat turn 会先写入 AgentScope user / assistant running message。
#   - 验证完成、失败和旧会话只读边界。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

import asyncio
import json

from app.api.chat import _mirror_agentscope_stream_event
import pytest

from app.models.agentscope_workbench import AgentScopeEvent, AgentScopeMessage, AgentScopeSession
from app.schemas.bi_workbench import build_datalogue_event_envelope
from app.schemas.chat import ChatRequest
from app.services.agentscope_chat_bridge import (
    begin_chat_turn,
    complete_chat_turn,
    fail_chat_turn,
    record_stream_event,
)


def test_begin_chat_turn_creates_agentscope_session_and_messages(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id=None,
        user_text="查询杨凯 2024 年工作日志",
        metadata={"dataset_id": 10, "legacy_conversation_id": 25},
    )

    session = db_session.query(AgentScopeSession).filter(AgentScopeSession.thread_id == context.thread_id).one()
    messages = (
        db_session.query(AgentScopeMessage)
        .filter(AgentScopeMessage.thread_id == context.thread_id)
        .order_by(AgentScopeMessage.id.asc())
        .all()
    )

    assert context.thread_id.startswith("as_")
    assert context.is_legacy_read_only is False
    assert session.source_type == "agentscope"
    assert session.legacy_conversation_id == 25
    assert session.metadata_json["legacy_conversation_id"] == 25
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].status == "completed"
    assert messages[1].status == "running"


@pytest.mark.asyncio
async def test_chat_stream_shadow_runtime_boundary_records_safe_contract(db_session, monkeypatch):
    from app.api import chat as chat_api

    class Settings:
        MULTITURN_ENABLED = False
        AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED = True

    async def successful_singleturn(*args, **kwargs):
        yield {"data": json.dumps({"type": "final", "answer": "完成"}, ensure_ascii=False)}

    monkeypatch.setattr("app.api.chat.get_settings", lambda: Settings())
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", successful_singleturn)

    events = [
        event
        async for event in chat_api._stream_chat(
            ChatRequest(
                question="查询 GMV",
                dataset_id=12,
                conversation_id=7,
                thread_id="as_11111111-1111-1111-1111-111111111111",
            ),
            db_session,
        )
    ]

    session = db_session.query(AgentScopeSession).one()
    boundary = session.metadata_json["agentic_runtime_boundary"]
    assert len(events) == 1
    assert boundary["status"] == "ready"
    assert boundary["selected_agent"] == "bi_lead_agent"
    assert boundary["projected_context"] == {
        "question": "查询 GMV",
        "conversation_id": 7,
        "dataset_id": 12,
        "thread_id": "as_11111111-1111-1111-1111-111111111111",
    }
    assert [tool["name"] for tool in boundary["tool_registry"]] == [
        "get_dataset_status",
        "list_candidate_assets",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "create_query_artifact",
        "get_artifact_summary",
    ]
    dumped = repr(boundary)
    for forbidden in ("ask_bi", "AgentScopeShellAdapter", "schema", "raw_rows", "query_plan", "select "):
        assert forbidden not in dumped


@pytest.mark.asyncio
async def test_chat_stream_shadow_runtime_boundary_defaults_off(db_session, monkeypatch):
    from app.api import chat as chat_api

    class Settings:
        MULTITURN_ENABLED = False
        AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED = False

    async def successful_singleturn(*args, **kwargs):
        yield {"data": json.dumps({"type": "final", "answer": "完成"}, ensure_ascii=False)}

    monkeypatch.setattr("app.api.chat.get_settings", lambda: Settings())
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", successful_singleturn)

    _ = [
        event
        async for event in chat_api._stream_chat(
            ChatRequest(question="查询 GMV", dataset_id=12),
            db_session,
        )
    ]

    session = db_session.query(AgentScopeSession).one()
    assert "agentic_runtime_boundary" not in session.metadata_json


def test_chat_request_accepts_agentscope_thread_id():
    request = ChatRequest(
        question="继续查询",
        thread_id="as_88888888-8888-8888-8888-888888888888",
    )

    assert request.thread_id == "as_88888888-8888-8888-8888-888888888888"


def test_chat_bridge_projects_stream_events_and_completes_turn(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id=None,
        user_text="查询杨凯 2024 年工作日志",
        metadata={},
    )
    envelope = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={"answer": "已完成"},
        task_id="task-2",
        trace_id="trace-2",
    )

    record_stream_event(db_session, context=context, envelope=envelope)
    completed = complete_chat_turn(
        db_session,
        context=context,
        final_summary="已完成",
        final_payload={"answer": "已完成", "trace_ref": "trace-2"},
    )

    assert completed.status == "completed"
    assert completed.content_summary == "已完成"


def test_chat_bridge_marks_failed_turn(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id=None,
        user_text="查询失败",
        metadata={},
    )

    failed = fail_chat_turn(
        db_session,
        context=context,
        error_summary="执行失败",
        error_payload={"checkpoint_ref": "checkpoint:failed"},
    )

    assert failed.status == "failed"
    assert failed.content_summary == "执行失败"


def test_chat_bridge_keeps_legacy_thread_read_only(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id="conv_25",
        user_text="继续旧会话",
        metadata={},
    )

    assert context.thread_id == "conv_25"
    assert context.is_legacy_read_only is True
    assert context.user_message_id is None
    assert context.assistant_message_id is None
    assert db_session.query(AgentScopeSession).count() == 0
    assert db_session.query(AgentScopeMessage).count() == 0

    assert complete_chat_turn(db_session, context=context, final_summary="完成", final_payload={"answer": "完成"}) is None
    assert fail_chat_turn(db_session, context=context, error_summary="失败", error_payload={"error": "失败"}) is None
    assert db_session.query(AgentScopeSession).count() == 0
    assert db_session.query(AgentScopeMessage).count() == 0


def test_chat_bridge_does_not_treat_numeric_thread_id_as_legacy(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id="25",
        user_text="继续旧会话",
        metadata={},
    )

    assert context.thread_id.startswith("as_")
    assert context.is_legacy_read_only is False
    assert db_session.query(AgentScopeSession).count() == 1
    assert db_session.query(AgentScopeMessage).count() == 2


def test_mirror_stream_final_uses_envelope_and_does_not_persist_top_level_sql(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id=None,
        user_text="查询杨凯 2024 年工作日志",
        metadata={},
    )
    envelope = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={"answer": "已完成"},
        task_id="task-safe",
        trace_id="trace-safe",
    )
    event = {
        "data": json.dumps(
            {
                "type": "final",
                "answer": "已完成",
                "sql": "select * from secret_table",
                "event_envelope": envelope.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
    }

    mirrored, final_seen, bridge_closed = _mirror_agentscope_stream_event(
        db=db_session,
        context=context,
        event=event,
        final_seen=False,
        bridge_closed=False,
    )

    assistant = (
        db_session.query(AgentScopeMessage)
        .filter(AgentScopeMessage.message_id == context.assistant_message_id)
        .one()
    )
    timeline_event = (
        db_session.query(AgentScopeEvent)
        .filter(AgentScopeEvent.thread_id == context.thread_id)
        .one()
    )
    parsed = json.loads(mirrored["data"])

    assert final_seen is True
    assert bridge_closed is True
    assert parsed["thread_id"] == context.thread_id
    assert assistant.status == "completed"
    assert "sql" not in assistant.business_payload_json
    assert timeline_event.payload_json == {"answer": "已完成"}


def test_chat_bridge_sanitizes_summary_and_payload_text(db_session):
    context = begin_chat_turn(
        db_session,
        raw_thread_id=None,
        user_text="查询",
        metadata={},
    )

    completed = complete_chat_turn(
        db_session,
        context=context,
        final_summary='psycopg2.errors.UndefinedColumn: column "secret_name" does not exist',
        final_payload={"answer": 'psycopg2.errors.UndefinedColumn: column "secret_name" does not exist'},
    )
    failed = fail_chat_turn(
        db_session,
        context=context,
        error_summary='psycopg2.errors.UndefinedColumn: column "secret_name" does not exist',
        error_payload={"error": 'psycopg2.errors.UndefinedColumn: column "secret_name" does not exist'},
    )

    assert completed.content_summary == "查询已完成，结果请通过引用查看。"
    assert completed.business_payload_json["answer"] == "查询已完成，结果请通过引用查看。"
    assert failed.status == "completed"


@pytest.mark.asyncio
async def test_singleturn_stream_exception_closes_agentscope_message(db_session, monkeypatch):
    from app.api import chat as chat_api
    from app.schemas.chat import ChatRequest

    async def broken_singleturn(*args, **kwargs):
        raise RuntimeError("select * from secret_table")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_api.get_settings(), "MULTITURN_ENABLED", False)
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", broken_singleturn)

    with pytest.raises(RuntimeError):
        async for _ in chat_api._stream_chat(ChatRequest(question="查询"), db_session):
            pass

    assistant = db_session.query(AgentScopeMessage).filter(AgentScopeMessage.role == "assistant").one()
    assert assistant.status == "failed"
    assert assistant.lease_expires_at is None
    assert assistant.content_summary == "问数执行失败，内部细节已隐藏。"


@pytest.mark.asyncio
async def test_singleturn_stream_cancel_closes_agentscope_message(db_session, monkeypatch):
    from app.api import chat as chat_api
    from app.schemas.chat import ChatRequest

    async def cancelled_singleturn(*args, **kwargs):
        raise asyncio.CancelledError()
        yield  # pragma: no cover

    monkeypatch.setattr(chat_api.get_settings(), "MULTITURN_ENABLED", False)
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", cancelled_singleturn)

    with pytest.raises(asyncio.CancelledError):
        async for _ in chat_api._stream_chat(ChatRequest(question="查询"), db_session):
            pass

    assistant = db_session.query(AgentScopeMessage).filter(AgentScopeMessage.role == "assistant").one()
    assert assistant.status == "interrupted"
    assert assistant.lease_expires_at is None


@pytest.mark.asyncio
async def test_singleturn_stream_without_final_marks_failed(db_session, monkeypatch):
    from app.api import chat as chat_api
    from app.schemas.chat import ChatRequest

    async def no_final_singleturn(*args, **kwargs):
        yield {"data": json.dumps({"type": "step", "status": "done"}, ensure_ascii=False)}

    monkeypatch.setattr(chat_api.get_settings(), "MULTITURN_ENABLED", False)
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", no_final_singleturn)

    events = [event async for event in chat_api._stream_chat(ChatRequest(question="查询"), db_session)]

    assistant = db_session.query(AgentScopeMessage).filter(AgentScopeMessage.role == "assistant").one()
    assert len(events) == 1
    assert assistant.status == "failed"
    assert assistant.lease_expires_at is None


@pytest.mark.asyncio
async def test_singleturn_error_blocked_final_marks_failed(db_session, monkeypatch):
    from app.api import chat as chat_api
    from app.schemas.chat import ChatRequest

    envelope = build_datalogue_event_envelope(
        event_type="error.blocked",
        visibility="user_visible",
        payload={"answer": "无法处理该问题。"},
    )

    async def blocked_singleturn(*args, **kwargs):
        yield {
            "data": json.dumps(
                {
                    "type": "final",
                    "answer": "无法处理该问题。",
                    "event_envelope": envelope.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(chat_api.get_settings(), "MULTITURN_ENABLED", False)
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", blocked_singleturn)

    events = [event async for event in chat_api._stream_chat(ChatRequest(question="查询"), db_session)]

    assistant = db_session.query(AgentScopeMessage).filter(AgentScopeMessage.role == "assistant").one()
    assert len(events) == 1
    assert assistant.status == "failed"


@pytest.mark.asyncio
async def test_multiturn_persist_failure_does_not_override_completed_mirror(db_session, monkeypatch):
    from app.api import chat as chat_api
    from app.schemas.chat import ChatRequest

    envelope = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={"answer": "已完成"},
    )

    async def successful_singleturn(*args, **kwargs):
        yield {
            "data": json.dumps(
                {
                    "type": "final",
                    "answer": "已完成",
                    "event_envelope": envelope.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
        }

    def fail_persist(*args, **kwargs):
        raise RuntimeError("persist failed")

    monkeypatch.setattr(chat_api.get_settings(), "MULTITURN_ENABLED", True)
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", successful_singleturn)
    monkeypatch.setattr(chat_api, "_persist_completed_turn", fail_persist)

    events = [event async for event in chat_api._stream_chat(ChatRequest(question="查询"), db_session)]

    assistant = db_session.query(AgentScopeMessage).filter(AgentScopeMessage.role == "assistant").one()
    assert len(events) == 1
    assert assistant.status == "completed"
