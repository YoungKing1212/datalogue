# ============================================================
# File Name   : test_workbench_retry_actions.py
# Description:
#   C3 Workbench 受控 retry action 测试。
#
# Responsibilities:
#   - 验证 Workbench retry 只能基于 checkpoint 创建新的 running message。
#   - 验证 retry API 不接收 SQL、schema、raw rows 等执行面 payload。
#   - 验证 legacy conv_* 线程保持只读禁用态。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

from app.models.agentscope_workbench import AgentScopeEvent, AgentScopeMessage
from app.services.agentscope_mirror import (
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_failed,
    record_agentscope_ref,
)


def _failed_message_with_checkpoint(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        title="retry 测试",
    )
    failed = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="查询执行中断，可基于检查点重试。",
        payload={"checkpoint_ref": "checkpoint://retry-1"},
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://retry-1",
        relation="checkpoint",
    )
    return session.thread_id, failed.message_id, "checkpoint://retry-1"


def test_retry_action_creates_new_running_message(client, db_session):
    thread_id, message_id, checkpoint_ref = _failed_message_with_checkpoint(db_session)

    response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": thread_id,
            "message_id": message_id,
            "checkpoint_ref": checkpoint_ref,
            "selected_action": "retry_last_step",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["thread_id"] == thread_id
    assert payload["retry_message_id"]
    assert payload["task_request"] == {
        "task_source": "workbench",
        "task_type": "bi_query",
        "question": "retry 测试",
        "conversation_id": None,
        "session_id": None,
        "thread_id": thread_id,
        "clarification_response": None,
        "retry_checkpoint_ref": checkpoint_ref,
            "artifact_ref": None,
            "dataset_id": None,
            "model_credential_id": None,
            "model_name": None,
            "model_parameters": {},
            "user_confirmation": None,
            "client_context": {"action": "retry_last_step"},
        }
    assert payload["run_request"] is None
    assert "sql" not in str(payload["task_request"]).lower()
    retry_message = (
        db_session.query(AgentScopeMessage)
        .filter(AgentScopeMessage.message_id == payload["retry_message_id"])
        .one()
    )
    assert retry_message.status == "running"
    assert retry_message.role == "assistant"
    assert retry_message.business_payload_json == {
        "checkpoint_ref": checkpoint_ref,
        "selected_action": "retry_last_step",
    }
    event = db_session.query(AgentScopeEvent).filter_by(event_type="workbench.retry_requested").one()
    assert event.thread_id == thread_id
    assert event.message_id == retry_message.message_id
    assert event.payload_json == {
        "checkpoint_ref": checkpoint_ref,
        "selected_action": "retry_last_step",
        "summary": "已接收重试请求，准备从检查点恢复。",
    }


def test_retry_action_is_idempotent_for_same_running_checkpoint(client, db_session):
    thread_id, message_id, checkpoint_ref = _failed_message_with_checkpoint(db_session)

    first = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": thread_id,
            "message_id": message_id,
            "checkpoint_ref": checkpoint_ref,
            "selected_action": "retry_last_step",
        },
    )
    second = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": thread_id,
            "message_id": message_id,
            "checkpoint_ref": checkpoint_ref,
            "selected_action": "retry_last_step",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["retry_message_id"] == first.json()["retry_message_id"]
    retry_messages = (
        db_session.query(AgentScopeMessage)
        .filter(AgentScopeMessage.thread_id == thread_id)
        .filter(AgentScopeMessage.status == "running")
        .all()
    )
    assert len(retry_messages) == 1


def test_retry_run_request_sanitizes_internal_question_text(client, db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_dddddddd-dddd-dddd-dddd-dddddddddddd",
        title="select * from hidden_table",
    )
    failed = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="查询执行中断，可基于检查点重试。",
        payload={"checkpoint_ref": "checkpoint://retry-sanitize"},
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://retry-sanitize",
        relation="checkpoint",
    )

    response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": session.thread_id,
            "message_id": failed.message_id,
            "checkpoint_ref": "checkpoint://retry-sanitize",
            "selected_action": "retry_last_step",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["task_request"]["question"] == "重试上一步"
    assert payload["run_request"] is None
    assert "select" not in str(payload["task_request"]).lower()


def test_retry_payload_rejects_internal_execution_keys(client, db_session):
    thread_id, message_id, checkpoint_ref = _failed_message_with_checkpoint(db_session)

    response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": thread_id,
            "message_id": message_id,
            "checkpoint_ref": checkpoint_ref,
            "selected_action": "retry_last_step",
            "sql": "select * from hidden_table",
            "schema": {"tables": ["hidden_table"]},
            "raw_rows": [{"secret": "value"}],
        },
    )

    assert response.status_code == 400


def test_legacy_retry_returns_disabled_reason(client):
    response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": "conv_25",
            "message_id": "conv_msg_1",
            "checkpoint_ref": "checkpoint://legacy",
            "selected_action": "retry_last_step",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "thread_id": "conv_25",
        "retry_message_id": None,
        "accepted": False,
        "disabled_reason": "旧会话为只读模式，不能直接发起 Workbench 重试。",
        "task_request": None,
        "run_request": None,
    }


def test_retry_without_checkpoint_returns_conflict(client, db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_cccccccc-cccc-cccc-cccc-cccccccccccc",
        title="无 checkpoint 测试",
    )
    failed = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="查询失败",
        payload={"error_summary": "查询失败"},
    )

    response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": session.thread_id,
            "message_id": failed.message_id,
            "checkpoint_ref": "checkpoint://missing",
            "selected_action": "retry_last_step",
        },
    )

    assert response.status_code == 409
