# ============================================================
# File Name   : test_workbench_agentic_task_actions.py
# Description:
#   Workbench action 迁移到 AgenticShellTaskRequest 的契约测试。
#
# Responsibilities:
#   - 验证 retry action 返回 task_request，而不是旧 chat run_request。
#   - 验证 retry task_request 带 task_source=workbench 和 retry_checkpoint_ref。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from datetime import datetime, timezone

from app.models.agentscope_workbench import AgentScopeMessage
from app.schemas.agentscope_workbench import WorkbenchRetryRequest
from app.services.agentscope_mirror import create_agentscope_session, record_agentscope_ref
from app.services.workbench_actions import request_controlled_retry


def test_workbench_retry_returns_agentic_shell_task_request(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        title="统计合同总金额",
        legacy_conversation_id=7,
        metadata={"dataset_id": 12},
    )
    failed = AgentScopeMessage(
        message_id="msg-failed",
        thread_id=session.thread_id,
        role="assistant",
        status="failed",
        content_summary="查询失败",
        business_payload_json={"question": "统计合同总金额", "dataset_id": 12},
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(failed)
    db_session.commit()
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value="checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg-failed/query_context_ready",
        relation="checkpoint",
    )

    response = request_controlled_retry(
        db_session,
        request=WorkbenchRetryRequest(
            thread_id=session.thread_id,
            message_id=failed.message_id,
            checkpoint_ref="checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg-failed/query_context_ready",
            selected_action="retry_last_step",
        ),
    )

    assert response.accepted is True
    assert response.task_request is not None
    assert response.task_request.task_source == "workbench"
    assert response.task_request.retry_checkpoint_ref.startswith("checkpoint://")
    assert response.task_request.conversation_id == 7
    assert response.task_request.dataset_id == 12
    assert response.run_request is None
