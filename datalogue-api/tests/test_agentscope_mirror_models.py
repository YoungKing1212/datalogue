# ============================================================
# File Name   : test_agentscope_mirror_models.py
# Description:
#   C3 AgentScope Workbench 本地镜像表和服务测试。
#
# Responsibilities:
#   - 验证 session/message/event/ref 四类镜像记录可以被主链写入。
#   - 验证 ref 唯一约束和 running message lease 查询行为。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.agentscope_workbench import AgentScopeRef
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    find_expired_running_messages,
    mark_message_completed,
    mark_message_failed,
    mark_message_interrupted,
    record_agentscope_event,
    record_agentscope_ref,
)


@pytest.fixture
def frozen_time():
    return datetime(2026, 6, 30, 11, 30, tzinfo=timezone.utc)


def test_create_agentscope_session_and_messages(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_01234567-89ab-cdef-0123-456789abcdef",
        title="工作日志查询",
    )
    user_message = append_user_message(
        db_session,
        thread_id=session.thread_id,
        content_summary="查询杨凯 2024 年工作日志",
        payload={"intent": "worklog_query"},
    )
    assistant_message = create_running_assistant_message(
        db_session,
        thread_id=session.thread_id,
        lease_seconds=60,
    )
    completed = mark_message_completed(
        db_session,
        message_id=assistant_message.message_id,
        content_summary="已完成查询",
        payload={"answer_summary": "共 10 条"},
    )
    event = record_agentscope_event(
        db_session,
        thread_id=session.thread_id,
        message_id=completed.message_id,
        event_type="answer.completed",
        payload={"summary": "已完成查询"},
        visibility="user",
        task_id="task-1",
        trace_id="trace-1",
    )
    ref = record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=completed.message_id,
        ref_type="artifact",
        ref_value="artifact:0123456789abcdef0123456789abcdef",
        relation="primary",
    )

    assert session.thread_id.startswith("as_")
    assert session.source_type == "agentscope"
    assert user_message.role == "user"
    assert user_message.status == "completed"
    assert completed.role == "assistant"
    assert completed.status == "completed"
    assert completed.content_summary == "已完成查询"
    assert event.event_type == "answer.completed"
    assert event.visibility == "user"
    assert ref.relation == "primary"


def test_agentscope_mirror_rejects_legacy_thread_writes(db_session):
    with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_REQUIRES_AS_THREAD"):
        append_user_message(
            db_session,
            thread_id="conv_25",
            content_summary="旧会话续聊",
            payload={"intent": "legacy"},
        )


def test_agentscope_mirror_rejects_forbidden_business_payload(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_33333333-3333-3333-3333-333333333333",
        title="泄露防护测试",
    )

    with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED"):
        append_user_message(
            db_session,
            thread_id=session.thread_id,
            content_summary="危险 payload",
            payload={"query_plan": {"sql": "select * from private_table"}},
        )


def test_agentscope_mirror_rejects_forbidden_payload_variants(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_44444444-4444-4444-4444-444444444444",
        title="复杂泄露防护测试",
    )

    dangerous_payloads = [
        {"compiled_sql": "select * from private_table"},
        {"schema_context": {"dataset": "internal"}},
        {"rows": [{"secret": "value"}]},
        {"message": "请执行 SELECT * FROM private_table"},
    ]

    for payload in dangerous_payloads:
        with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED"):
            record_agentscope_event(
                db_session,
                thread_id=session.thread_id,
                message_id=None,
                event_type="task.started",
                payload=payload,
                visibility="user",
                task_id=None,
                trace_id=None,
            )


def test_agentscope_ref_rejects_duplicate_relation(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_11111111-1111-1111-1111-111111111111",
        title="重复引用测试",
    )
    message = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=message.message_id,
        error_summary="查询中断",
        payload={"checkpoint_ref": "checkpoint:1"},
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=message.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint:1",
        relation="checkpoint",
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(
                AgentScopeRef(
                    thread_id=session.thread_id,
                    message_id=message.message_id,
                    ref_type="checkpoint",
                    ref_value="checkpoint:1",
                    relation="checkpoint",
                )
            )
            db_session.flush()


def test_agentscope_ref_rejects_duplicate_thread_level_relation(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_55555555-5555-5555-5555-555555555555",
        title="线程级引用重复测试",
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=None,
        ref_type="trace",
        ref_value="trace-1",
        relation="trace",
    )

    with pytest.raises(ValueError, match="AGENTSCOPE_REF_ALREADY_EXISTS"):
        record_agentscope_ref(
            db_session,
            thread_id=session.thread_id,
            message_id=None,
            ref_type="trace",
            ref_value="trace-1",
            relation="trace",
        )


def test_find_expired_running_messages(db_session, frozen_time):
    session = create_agentscope_session(
        db_session,
        thread_id="as_22222222-2222-2222-2222-222222222222",
        title="lease 测试",
    )
    expired = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    active = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=3600)
    interrupted = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)

    expired.lease_expires_at = frozen_time - timedelta(seconds=1)
    active.lease_expires_at = frozen_time + timedelta(seconds=1)
    interrupted.lease_expires_at = frozen_time - timedelta(seconds=1)
    mark_message_interrupted(db_session, message_id=interrupted.message_id, reason="lease 超时")
    db_session.commit()

    expired_messages = find_expired_running_messages(db_session, now=frozen_time)

    assert [message.message_id for message in expired_messages] == [expired.message_id]
