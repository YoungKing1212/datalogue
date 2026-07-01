# ============================================================
# File Name   : test_c3_workbench_acceptance.py
# Description:
#   C3 AgentScope Workbench 双主路径验收测试。
#
# Responsibilities:
#   - 验证新 as_* 会话从 Chat stream mirror 到 Workbench View Model 的主路径。
#   - 验证 failed/interrupted 消息通过 checkpoint 执行受控 retry。
#   - 验证旧 conv_* 会话只读回放且不创建 AgentScope mirror。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest

from app import models
from app.models.agentscope_workbench import AgentScopeEvent, AgentScopeMessage, AgentScopeRef, AgentScopeSession
from app.schemas.bi_workbench import build_datalogue_event_envelope
from app.schemas.chat import ChatRequest
from app.services.conversation_store import ConversationStore
from app.services.agentscope_mirror import create_agentscope_session, create_running_assistant_message
from app.services.agentscope_mirror import mark_message_failed, record_agentscope_ref
from app.services.artifact_store import ArtifactStore
from app.services.workbench_actions import run_lease_recovery


FORBIDDEN_PUBLIC_KEYS = {
    "sql",
    "raw_sql",
    "llm_sql",
    "direct_sql",
    "schema",
    "raw_result",
    "raw_rows",
    "query_plan",
    "field_patch",
    "table_name",
    "column_name",
    "columns",
    "rows",
}


def _sse(payload: dict[str, Any]) -> dict[str, str]:
    return {"data": json.dumps(payload, ensure_ascii=False)}


def _assert_public_payload_safe(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert str(key) not in FORBIDDEN_PUBLIC_KEYS
            _assert_public_payload_safe(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_public_payload_safe(item)


@pytest.mark.asyncio
async def test_new_chat_stream_creates_agentscope_workbench_view(
    client,
    db_session,
    monkeypatch,
    sample_dataset,
):
    from app.api import chat as chat_api

    artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"summary": "共 3 条工作日志", "columns": ["hidden"], "rows": [{"hidden": 1}]},
        dataset_id=sample_dataset.id,
        trace_id="trace-c3-path-a",
    )
    task_started = build_datalogue_event_envelope(
        event_type="task.started",
        visibility="user_visible",
        payload={"summary": "开始理解问数任务"},
        task_id="task-c3-path-a",
        trace_id="trace-c3-path-a",
    )
    answer_completed = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={
            "summary": "已完成查询",
            "primary_ref": {"ref_type": "artifact", "ref": artifact_ref},
            "related_refs": [{"ref_type": "trace", "ref": "trace:trace-c3-path-a"}],
        },
        task_id="task-c3-path-a",
        trace_id="trace-c3-path-a",
    )

    async def successful_singleturn(*args, **kwargs):
        yield _sse({"type": "step", "event_envelope": task_started.model_dump(mode="json")})
        yield _sse(
            {
                "type": "final",
                "answer": "已完成查询",
                "result_ref": artifact_ref,
                "task_id": "task-c3-path-a",
                "trace_id": "trace-c3-path-a",
                "event_envelope": answer_completed.model_dump(mode="json"),
            }
        )

    monkeypatch.setattr(chat_api.get_settings(), "MULTITURN_ENABLED", False)
    monkeypatch.setattr(chat_api, "_stream_chat_singleturn", successful_singleturn)

    events = [
        json.loads(event["data"])
        async for event in chat_api._stream_chat(ChatRequest(question="查询杨凯 2024 年工作日志"), db_session)
    ]
    final_payload = events[-1]
    thread_id = final_payload["thread_id"]

    session = db_session.query(AgentScopeSession).filter_by(thread_id=thread_id).one()
    messages = db_session.query(AgentScopeMessage).filter_by(thread_id=thread_id).order_by(AgentScopeMessage.id).all()
    event_types = [event.event_type for event in db_session.query(AgentScopeEvent).filter_by(thread_id=thread_id).all()]
    refs = db_session.query(AgentScopeRef).filter_by(thread_id=thread_id).all()
    view = client.get(f"/api/workbench/thread/{thread_id}").json()

    assert thread_id.startswith("as_")
    assert session.source_type == "agentscope"
    assert [(message.role, message.status) for message in messages] == [
        ("user", "completed"),
        ("assistant", "completed"),
    ]
    assert event_types == ["task.started", "answer.completed"]
    assert any(ref.ref_value == artifact_ref and ref.relation == "primary" for ref in refs)
    assert view["thread_id"] == thread_id
    assert view["read_only"] is False
    assert view["primary_artifact_ref"] == artifact_ref
    assert [item["event_type"] for item in view["timeline"]] == ["task.started", "answer.completed"]
    _assert_public_payload_safe(final_payload)
    _assert_public_payload_safe(view)


def test_interrupted_workbench_thread_can_request_controlled_retry(client, db_session):
    now = datetime(2026, 6, 30, 13, 40, tzinfo=timezone.utc)
    session = create_agentscope_session(
        db_session,
        thread_id="as_ffffffff-ffff-ffff-ffff-ffffffffffff",
        title="retry acceptance",
    )
    expired = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=30)
    expired.lease_expires_at = now - timedelta(seconds=1)
    expired.business_payload_json = {"checkpoint_ref": "checkpoint://c3-acceptance"}
    db_session.commit()

    recovered = run_lease_recovery(db_session, now=now)
    interrupted = recovered[0]
    unsafe_response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": session.thread_id,
            "message_id": interrupted.message_id,
            "checkpoint_ref": "checkpoint://c3-acceptance",
            "selected_action": "retry_last_step",
            "sql": "select * from hidden_table",
        },
    )
    safe_response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": session.thread_id,
            "message_id": interrupted.message_id,
            "checkpoint_ref": "checkpoint://c3-acceptance",
            "selected_action": "retry_last_step",
        },
    )
    view = client.get(f"/api/workbench/thread/{session.thread_id}").json()

    assert unsafe_response.status_code == 400
    assert safe_response.status_code == 200
    payload = safe_response.json()
    assert payload["accepted"] is True
    retry_message = db_session.query(AgentScopeMessage).filter_by(message_id=payload["retry_message_id"]).one()
    retry_event = db_session.query(AgentScopeEvent).filter_by(event_type="workbench.retry_requested").one()
    assert retry_message.status == "running"
    assert retry_message.business_payload_json == {
        "checkpoint_ref": "checkpoint://c3-acceptance",
        "selected_action": "retry_last_step",
    }
    assert retry_event.payload_json["checkpoint_ref"] == "checkpoint://c3-acceptance"
    assert view["available_actions"][0]["enabled"] is True
    _assert_public_payload_safe(payload)
    _assert_public_payload_safe(view)


@pytest.mark.asyncio
async def test_workbench_retry_run_request_restores_checkpoint_through_chat_stream(
    client,
    db_session,
    monkeypatch,
    sample_dataset,
):
    from app.api import chat as chat_api

    class MultiturnSettings:
        MULTITURN_ENABLED = True
        MULTITURN_LOCK_TTL_SECONDS = 300
        MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS = 2000
        MULTITURN_COMPACTION_ENABLED = False

    monkeypatch.setattr("app.api.chat.get_settings", lambda: MultiturnSettings())
    conversation = models.Conversation(title="C3-P1 retry harness", user_id=1, dataset_id=sample_dataset.id)
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    session_id = f"conversation-{conversation.id}"
    store = ConversationStore(db_session)
    store.load_or_create(session_id=session_id, user_id="1")
    checkpoint_ref = store.register_retry_checkpoint(
        session_id=session_id,
        checkpoint_kind="query_context_ready",
        user_id="1",
        conversation_id=conversation.id,
        task_id="c3-p1-retry-task",
        permission_scope=f"dataset:{sample_dataset.id}",
        context={
            "question": "查询杨凯 2024 年工作日志",
            "dataset_id": sample_dataset.id,
            "route_decision": {"dataset_id": sample_dataset.id, "decision": "selected"},
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session = create_agentscope_session(
        db_session,
        thread_id="as_11111111-2222-3333-4444-555555555555",
        title="查询杨凯 2024 年工作日志",
        legacy_conversation_id=conversation.id,
    )
    failed = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="查询执行中断，可基于检查点重试。",
        payload={"checkpoint_ref": checkpoint_ref},
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value=checkpoint_ref,
        relation="checkpoint",
    )
    retry_response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": session.thread_id,
            "message_id": failed.message_id,
            "checkpoint_ref": checkpoint_ref,
            "selected_action": "retry_last_step",
        },
    )
    run_request = retry_response.json()["run_request"]
    trace_id = "trace-c3-p1-retry"
    artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"summary": "重试后返回 100 条工作日志"},
        dataset_id=sample_dataset.id,
        trace_id=trace_id,
    )
    answer_completed = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={
            "summary": "已从检查点恢复并完成查询",
            "primary_ref": {"ref_type": "artifact", "ref": artifact_ref},
            "related_refs": [{"ref_type": "checkpoint", "ref": checkpoint_ref}],
        },
        task_id="c3-p1-retry-rerun",
        trace_id=trace_id,
    )
    captured_payloads: list[ChatRequest] = []

    async def successful_retry_singleturn(payload, *args, **kwargs):
        captured_payloads.append(payload)
        yield _sse(
            {
                "type": "final",
                "answer": "已从检查点恢复并完成查询",
                "conversation_id": conversation.id,
                "result_ref": artifact_ref,
                "task_id": "c3-p1-retry-rerun",
                "trace_id": trace_id,
                "event_envelope": answer_completed.model_dump(mode="json"),
            }
        )

    with (
        patch("app.api.chat._stream_chat_singleturn", successful_retry_singleturn),
        patch("app.api.chat.resolve_term_clarification", return_value={"status": "none"}),
    ):
        events = [
            json.loads(item["data"])
            async for item in chat_api._stream_chat(
                ChatRequest(
                    question=run_request["question"],
                    session_id=session_id,
                    conversation_id=run_request["conversation_id"],
                    thread_id=run_request["thread_id"],
                    dataset_id=run_request["dataset_id"],
                    retry_checkpoint_ref=run_request["retry_checkpoint_ref"],
                ),
                db_session,
            )
        ]

    event_keys = [event.get("event_envelope", {}).get("event_type") or event.get("type") for event in events]
    assert retry_response.status_code == 200
    assert run_request["thread_id"] == session.thread_id
    assert run_request["conversation_id"] == conversation.id
    assert captured_payloads[-1].question == "查询杨凯 2024 年工作日志"
    assert captured_payloads[-1].dataset_id == sample_dataset.id
    assert event_keys.index("retry.checkpoint_restored") < event_keys.index("answer.completed")
    final_payload = [event for event in events if event.get("type") == "final"][-1]
    assert final_payload["thread_id"] == session.thread_id
    assert final_payload["trace_id"] == trace_id
    assert final_payload["result_ref"] == artifact_ref
    persisted_event_types = [
        event.event_type
        for event in db_session.query(AgentScopeEvent).filter_by(thread_id=session.thread_id).all()
    ]
    refs = db_session.query(AgentScopeRef).filter_by(thread_id=session.thread_id).all()
    assert "workbench.retry_requested" in persisted_event_types
    assert "retry.checkpoint_restored" in persisted_event_types
    assert "answer.completed" in persisted_event_types
    assert any(ref.ref_type == "artifact" and ref.ref_value == artifact_ref for ref in refs)
    assert any(ref.ref_type == "checkpoint" and ref.ref_value == checkpoint_ref for ref in refs)
    assert any(ref.ref_type == "trace" and ref.ref_value == trace_id for ref in refs)
    _assert_public_payload_safe(events)


@pytest.mark.asyncio
async def test_browser_retry_completed_harness_replays_workbench_click_to_completed(
    client,
    db_session,
    monkeypatch,
    sample_dataset,
):
    from workbench_retry_harness import run_workbench_retry_completed_harness

    result = await run_workbench_retry_completed_harness(
        client=client,
        db_session=db_session,
        monkeypatch=monkeypatch,
        dataset_id=sample_dataset.id,
    )

    assert result.initial_view["status_summary"]["status"] == "failed"
    assert result.retry_response["accepted"] is True
    assert result.final_payload["thread_id"] == result.thread_id
    assert result.final_payload["result_ref"] == result.primary_artifact_ref
    assert result.completed_view["status_summary"]["status"] == "completed"
    assert result.completed_view["primary_artifact_ref"] == result.primary_artifact_ref
    assert result.observability_detail["found"] is True
    assert result.observability_detail["trace_id"] == result.trace_id
    contract = result.observability_detail["observability_contract"]
    assert contract["passed"] is True, contract
    assert contract["missing_events"] == []
    assert contract["attributes"]["thread_id"] == result.thread_id
    assert (
        contract["attributes"]["checkpoint_ref"]
        == result.checkpoint_ref
    )
    assert (
        contract["attributes"]["artifact_ref"]
        == result.primary_artifact_ref
    )
    assert result.event_types.index("retry.checkpoint_restored") < result.event_types.index("answer.completed")
    assert "retry.completed" in result.persisted_event_types
    assert "answer.completed" in result.persisted_event_types
    assert any(ref["relation"] == "primary" and ref["ref"] == result.primary_artifact_ref for ref in result.refs)
    _assert_public_payload_safe(result.initial_view)
    _assert_public_payload_safe(result.retry_response)
    _assert_public_payload_safe(result.stream_events)
    _assert_public_payload_safe(result.completed_view)


def test_legacy_conversation_workbench_view_is_read_only_without_mirror(client, db_session, sample_dataset):
    before_sessions = db_session.query(AgentScopeSession).count()
    conversation = models.Conversation(
        id=250,
        title="旧会话只读验收",
        thread_id="legacy-thread-250",
        user_id=1,
        dataset_id=sample_dataset.id,
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.add(
        models.Message(
            conversation_id=conversation.id,
            role="assistant",
            content="旧会话回答",
            response_metadata={},
        )
    )
    db_session.commit()

    response = client.get("/api/workbench/thread/conv_250")
    retry_response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": "conv_250",
            "message_id": "conv_msg_1",
            "checkpoint_ref": "checkpoint://legacy",
            "selected_action": "retry_last_step",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_id"] == "conv_250"
    assert payload["read_only"] is True
    assert payload["available_actions"] == []
    assert retry_response.json()["accepted"] is False
    assert db_session.query(AgentScopeSession).count() == before_sessions
    _assert_public_payload_safe(payload)
