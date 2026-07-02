# ============================================================
# File Name   : test_agentic_shell_retry_writer.py
# Description:
#   AS-R0 PR1.4 Shell writer 接管 retry/checkpoint 事件写回测试。
#
# Responsibilities:
#   - 验证 Workbench retry 请求通过 Agentic Shell action 写入。
#   - 验证写回 payload 继续阻断 SQL/schema/raw rows/query_plan 等内部执行载荷。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from app.models.agentscope_workbench import AgentScopeEvent
from app.schemas.agentscope_workbench import WorkbenchRetryRequest
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentscope_mirror import (
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_failed,
    record_agentscope_ref,
)
from app.services.workbench_actions import request_controlled_retry


def test_workbench_retry_request_is_written_through_shell_action(db_session, monkeypatch):
    from app.services import workbench_actions

    calls: list[dict] = []
    real_shell = DatalogueAgenticShell

    class SpyShell(real_shell):
        def record_action(self, **kwargs):
            calls.append(kwargs)
            return super().record_action(**kwargs)

    monkeypatch.setattr(workbench_actions, "DatalogueAgenticShell", SpyShell)

    session = create_agentscope_session(
        db_session,
        thread_id="as_14141414-1414-1414-1414-141414141414",
        title="retry shell writer",
    )
    failed = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="查询执行中断，可基于检查点重试。",
        payload={"checkpoint_ref": "checkpoint://shell-retry"},
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://shell-retry",
        relation="checkpoint",
    )

    response = request_controlled_retry(
        db_session,
        request=WorkbenchRetryRequest(
            thread_id=session.thread_id,
            message_id=failed.message_id,
            checkpoint_ref="checkpoint://shell-retry",
            selected_action="retry_last_step",
        ),
    )

    assert response.accepted is True
    assert calls == [
        {
            "action_id": "retry_last_step",
            "thread_id": session.thread_id,
            "message_id": response.retry_message_id,
            "payload": {
                "checkpoint_ref": "checkpoint://shell-retry",
                "selected_action": "retry_last_step",
                "summary": "已接收重试请求，准备从检查点恢复。",
            },
        }
    ]
    event = db_session.query(AgentScopeEvent).filter_by(event_type="workbench.retry_requested").one()
    assert event.message_id == response.retry_message_id
    assert event.payload_json["checkpoint_ref"] == "checkpoint://shell-retry"
