# ============================================================
# File Name   : test_agentscope_lease_recovery.py
# Description:
#   C3 AgentScope running message lease recovery 测试。
#
# Responsibilities:
#   - 验证过期 running assistant message 会被业务级中断。
#   - 验证未过期 running message 不受 recovery 影响。
#   - 验证 recovery 后可通过 checkpoint ref 进入受控 retry。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.agentscope_mirror import create_agentscope_session, create_running_assistant_message
from app.services.workbench_actions import run_lease_recovery


def test_lease_recovery_interrupts_expired_running_message(db_session):
    now = datetime(2026, 6, 30, 13, 10, tzinfo=timezone.utc)
    session = create_agentscope_session(
        db_session,
        thread_id="as_dddddddd-dddd-dddd-dddd-dddddddddddd",
        title="lease recovery",
    )
    expired = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=30)
    expired.lease_expires_at = now - timedelta(seconds=1)
    expired.business_payload_json = {"checkpoint_ref": "checkpoint://lease-expired"}
    active = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=30)
    active.lease_expires_at = now + timedelta(seconds=30)
    db_session.commit()

    recovered = run_lease_recovery(db_session, now=now)

    assert [message.message_id for message in recovered] == [expired.message_id]
    db_session.refresh(expired)
    db_session.refresh(active)
    assert expired.status == "interrupted"
    assert expired.content_summary == "问数任务超时中断，可从检查点安全重试。"
    assert expired.lease_expires_at is None
    assert expired.business_payload_json == {
        "checkpoint_ref": "checkpoint://lease-expired",
        "recovery_status": "interrupted",
    }
    assert active.status == "running"
    assert active.lease_expires_at is not None


def test_lease_recovery_adds_checkpoint_when_missing(db_session):
    now = datetime(2026, 6, 30, 13, 15, tzinfo=timezone.utc)
    session = create_agentscope_session(
        db_session,
        thread_id="as_eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        title="lease recovery checkpoint",
    )
    expired = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=30)
    expired.lease_expires_at = now - timedelta(seconds=1)
    db_session.commit()

    recovered = run_lease_recovery(db_session, now=now)

    assert len(recovered) == 1
    db_session.refresh(expired)
    assert expired.status == "interrupted"
    assert expired.business_payload_json["checkpoint_ref"].startswith(f"checkpoint://{session.thread_id}/")
    assert expired.business_payload_json["recovery_status"] == "interrupted"
