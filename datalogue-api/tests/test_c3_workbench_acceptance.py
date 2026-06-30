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

import pytest

from app import models
from app.models.agentscope_workbench import AgentScopeEvent, AgentScopeMessage, AgentScopeRef, AgentScopeSession
from app.schemas.bi_workbench import build_datalogue_event_envelope
from app.schemas.chat import ChatRequest
from app.services.agentscope_mirror import create_agentscope_session, create_running_assistant_message
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
