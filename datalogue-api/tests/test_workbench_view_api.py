# ============================================================
# File Name   : test_workbench_view_api.py
# Description:
#   C3 Workbench View Model API 测试。
#
# Responsibilities:
#   - 验证 AgentScope mirror 会话可转换成工作台只读视图。
#   - 验证旧 conversation 可按 conv_* 形式只读回放且不伪造 ArtifactCard。
#   - 验证工作台 artifact 读取口只返回脱敏业务摘要。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

from app.core import models
from app.services.runtime_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
    record_agentscope_event,
    record_agentscope_ref,
)
from app.domains.query_execution.artifact_store import ArtifactStore


FORBIDDEN_KEYS = {
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
    "content_json",
    "content_text",
}


def _assert_no_forbidden_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key not in FORBIDDEN_KEYS
            _assert_no_forbidden_keys(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_keys(item)


def test_get_workbench_thread_returns_agentscope_view(client, db_session, sample_dataset):
    thread = create_agentscope_session(
        db_session,
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        title="工作日志查询",
        metadata={"business_title": "工作日志查询"},
    )
    append_user_message(
        db_session,
        thread_id=thread.thread_id,
        content_summary="查询杨凯 2024 年工作日志",
        payload={"intent": "worklog_query"},
    )
    assistant = create_running_assistant_message(db_session, thread_id=thread.thread_id, lease_seconds=60)
    completed = mark_message_completed(
        db_session,
        message_id=assistant.message_id,
        content_summary="已完成查询，共 10 条工作日志。",
        payload={"answer_summary": "已完成查询"},
    )
    artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"columns": ["work_date"], "rows": [{"work_date": "2024-01-01"}], "summary": "共 10 条工作日志"},
        dataset_id=sample_dataset.id,
        trace_id="trace-workbench-1",
    )
    record_agentscope_event(
        db_session,
        thread_id=thread.thread_id,
        message_id=completed.message_id,
        event_type="answer.completed",
        payload={"summary": "已完成查询"},
        visibility="user",
        task_id="task-workbench-1",
        trace_id="trace-workbench-1",
    )
    record_agentscope_ref(
        db_session,
        thread_id=thread.thread_id,
        message_id=completed.message_id,
        ref_type="artifact",
        ref_value=artifact_ref,
        relation="primary",
    )
    record_agentscope_ref(
        db_session,
        thread_id=thread.thread_id,
        message_id=completed.message_id,
        ref_type="trace",
        ref_value="trace:trace-workbench-1",
        relation="trace",
    )

    response = client.get(f"/api/workbench/thread/{thread.thread_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_id"] == thread.thread_id
    assert payload["read_only"] is False
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][1]["content_summary"] == "已完成查询，共 10 条工作日志。"
    assert payload["timeline"][0]["event_type"] == "answer.completed"
    assert payload["timeline"][0]["summary"] == "已完成查询"
    assert payload["primary_artifact_ref"] == artifact_ref
    assert {"ref_type": "trace", "ref": "trace:trace-workbench-1", "relation": "trace"} in payload["related_refs"]
    assert payload["available_actions"][0]["action_id"] == "retry"
    assert payload["available_actions"][0]["enabled"] is False
    assert payload["status_summary"] == {
        "status": "completed",
        "label": "已完成",
        "tone": "success",
        "actionable": False,
        "read_only": False,
        "latest_message_id": completed.message_id,
        "primary_artifact_ref": artifact_ref,
        "retry_checkpoint_ref": None,
        "trace_ref": "trace:trace-workbench-1",
        "summary": "已完成查询，共 10 条工作日志。",
    }
    assert payload["legacy_notice"] is None
    _assert_no_forbidden_keys(payload)


def test_get_workbench_thread_returns_legacy_read_only_view(client, db_session, sample_dataset):
    conversation = models.Conversation(
        id=25,
        title="旧会话",
        thread_id="legacy-thread-25",
        user_id=1,
        dataset_id=sample_dataset.id,
    )
    db_session.add(conversation)
    db_session.commit()
    legacy_message = models.Message(
        conversation_id=conversation.id,
        role="assistant",
        content="旧回答",
        response_metadata={
            "result_ref": "artifact:legacy-result",
            "report_ref": "artifact:legacy-report",
        },
    )
    db_session.add(legacy_message)
    db_session.commit()

    response = client.get("/api/workbench/thread/conv_25")

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_id"] == "conv_25"
    assert payload["read_only"] is True
    assert payload["legacy_notice"]
    assert payload["messages"][0]["content_summary"] == "旧回答"
    assert payload["primary_artifact_ref"] is None
    assert payload["related_refs"] == []
    assert payload["available_actions"] == []
    assert payload["status_summary"] == {
        "status": "read_only",
        "label": "只读回放",
        "tone": "neutral",
        "actionable": False,
        "read_only": True,
        "latest_message_id": f"conv_msg_{legacy_message.id}",
        "primary_artifact_ref": None,
        "retry_checkpoint_ref": None,
        "trace_ref": None,
        "summary": "旧会话以只读方式展示，不会迁移、回填或发起 Workbench 重试。",
    }
    _assert_no_forbidden_keys(payload)


def test_get_workbench_thread_returns_retryable_failed_status(client, db_session):
    thread = create_agentscope_session(
        db_session,
        thread_id="as_abababab-abab-abab-abab-abababababab",
        title="失败重试测试",
    )
    failed = create_running_assistant_message(db_session, thread_id=thread.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="查询执行失败，可从检查点重试。",
        payload={"checkpoint_ref": "checkpoint://failed-status"},
    )
    record_agentscope_ref(
        db_session,
        thread_id=thread.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://failed-status",
        relation="checkpoint",
    )

    response = client.get(f"/api/workbench/thread/{thread.thread_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_actions"][0]["enabled"] is True
    assert payload["available_actions"][0]["checkpoint_ref"] == "checkpoint://failed-status"
    assert payload["status_summary"]["status"] == "failed"
    assert payload["status_summary"]["label"] == "执行失败"
    assert payload["status_summary"]["tone"] == "warning"
    assert payload["status_summary"]["actionable"] is True
    assert payload["status_summary"]["retry_checkpoint_ref"] == "checkpoint://failed-status"
    assert payload["status_summary"]["summary"] == "查询执行失败，可从检查点重试。"
    _assert_no_forbidden_keys(payload)


def test_get_workbench_thread_requires_checkpoint_on_latest_failed_message(client, db_session):
    thread = create_agentscope_session(
        db_session,
        thread_id="as_acacacac-acac-acac-acac-acacacacacac",
        title="检查点归属测试",
    )
    older = create_running_assistant_message(db_session, thread_id=thread.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=older.message_id,
        error_summary="旧失败",
        payload={"checkpoint_ref": "checkpoint://older"},
    )
    latest = create_running_assistant_message(db_session, thread_id=thread.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=latest.message_id,
        error_summary="最新失败缺少检查点",
        payload={},
    )
    record_agentscope_ref(
        db_session,
        thread_id=thread.thread_id,
        message_id=older.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://older",
        relation="checkpoint",
    )

    response = client.get(f"/api/workbench/thread/{thread.thread_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_actions"][0]["enabled"] is False
    assert payload["available_actions"][0]["disabled_reason"] == "当前消息缺少可用检查点。"
    assert payload["status_summary"]["status"] == "failed"
    assert payload["status_summary"]["actionable"] is False
    assert payload["status_summary"]["retry_checkpoint_ref"] is None
    _assert_no_forbidden_keys(payload)


def test_get_workbench_thread_returns_404_for_missing_agentscope_thread(client):
    response = client.get("/api/workbench/thread/as_missing")

    assert response.status_code == 404


def test_get_workbench_artifact_returns_sanitized_view(client, db_session, sample_dataset):
    artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={
            "columns": ["work_date"],
            "rows": [{"work_date": "2024-01-01"}],
            "summary": "共 10 条工作日志",
        },
        dataset_id=sample_dataset.id,
        conversation_id=25,
        trace_id="trace-workbench-2",
    )

    response = client.get(f"/api/workbench/artifact/{artifact_ref}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_ref"] == artifact_ref
    assert payload["kind"] == "query_result"
    assert payload["dataset_id"] == sample_dataset.id
    assert payload["preview_payload"] == {"summary": "共 10 条工作日志"}
    assert "content_json" not in payload
    assert "content_text" not in payload
    _assert_no_forbidden_keys(payload)


def test_get_workbench_artifact_can_be_thread_scoped(client, db_session, sample_dataset):
    thread = create_agentscope_session(
        db_session,
        thread_id="as_adadadad-adad-adad-adad-adadadadadad",
        title="产物归属测试",
    )
    owned_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"summary": "当前线程产物"},
        dataset_id=sample_dataset.id,
    )
    other_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"summary": "其他线程产物"},
        dataset_id=sample_dataset.id,
    )
    record_agentscope_ref(
        db_session,
        thread_id=thread.thread_id,
        message_id="msg_owned",
        ref_type="result",
        ref_value=owned_ref,
        relation="primary",
    )

    owned_response = client.get(f"/api/workbench/artifact/{owned_ref}?thread_id={thread.thread_id}")
    other_response = client.get(f"/api/workbench/artifact/{other_ref}?thread_id={thread.thread_id}")

    assert owned_response.status_code == 200
    assert owned_response.json()["preview_payload"] == {"summary": "当前线程产物"}
    assert other_response.status_code == 404


def test_get_workbench_artifact_fails_closed_for_non_artifact_ref(client):
    response = client.get("/api/workbench/artifact/trace:trace-workbench-1")

    assert response.status_code == 404
