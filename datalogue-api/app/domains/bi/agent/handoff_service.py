# ============================================================
# File Name   : handoff_service.py
# Description:
#   BI Agent K1 handoff 编排服务。
#
# Responsibilities:
#   - 在用户 approved confirmation 之后触发 DatasetAgent handoff。
#   - 持久化安全 handoff 摘要，并同步更新 LeadAgent run 阶段和终态。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.models.bi_agent import BIAgentHandoff, BIAgentRun
from app.core.schemas.bi_agent import BIAgentHandoffRequest, BIAgentHandoffResult
from app.core.middlewares.lifecycle import log_lifecycle
from app.domains.bi.agent.confirmation_service import BIAgentConfirmationService
from app.domains.bi.agent.handoff_port import BIHandoffPort
from app.domains.bi.agent.run_service import BIAgentRunService


_TERMINAL_HANDOFF_STATUS_TO_RUN_STATUS = {
    "completed": "completed",
    "blocked": "blocked",
    "failed": "failed",
    "cancelled": "cancelled",
}


class BIAgentHandoffService:
    """BI Agent handoff 应用服务；确认门禁通过后才允许调用 Dataset Query Skill。"""

    def __init__(
        self,
        db: Session,
        *,
        adapter: BIHandoffPort | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter or _default_handoff_port(db)
        self.run_service = BIAgentRunService(db)
        self.confirmation_service = BIAgentConfirmationService(db)

    async def query_dataset(self, *, run_id: int) -> BIAgentHandoffResult:
        run = self.db.get(BIAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        confirmation = self.confirmation_service.require_approved_confirmation(run_id)
        log_lifecycle(
            "bi_agent.handoff_service.started",
            bi_run_id=run.id,
            task_id=run.task_id,
            trace_id=run.trace_id,
            dataset_id=confirmation.dataset_id,
        )

        self.run_service.mark_phase(
            run,
            phase="handoff_run",
            status="running",
            status_reason="handoff_started",
        )  # handoff 开始前先落库，前端轮询和失败恢复能看到 DatasetAgent 已接管。
        request = BIAgentHandoffRequest(
            dataset_id=confirmation.dataset_id,
            confirmed_question=confirmation.confirmed_question,
            task_goal=confirmation.task_goal,
            user_confirmation_id=confirmation.id,
            routing_rationale=confirmation.routing_rationale,
            trace_id=run.trace_id,
            parent_run_id=str(run.id),
        )
        result = await self.adapter.query_dataset(request, task_id=run.task_id)
        log_lifecycle(
            "bi_agent.handoff_service.adapter.completed",
            bi_run_id=run.id,
            task_id=run.task_id,
            trace_id=run.trace_id,
            dataset_id=result.dataset_id,
            handoff_status=result.handoff_status,
            error_code=result.error_code,
            has_artifact=bool(result.artifact_ref),
        )
        self._persist_handoff(run=run, result=result)
        self._complete_run_from_handoff(run=run, result=result)
        self.db.commit()
        self.db.refresh(run)
        log_lifecycle(
            "bi_agent.handoff_service.completed",
            bi_run_id=run.id,
            task_id=run.task_id,
            trace_id=run.trace_id,
            dataset_id=result.dataset_id,
            handoff_status=result.handoff_status,
            error_code=result.error_code,
            run_status=run.status,
        )
        return result

    def _persist_handoff(self, *, run: BIAgentRun, result: BIAgentHandoffResult) -> BIAgentHandoff:
        handoff = run.handoff or BIAgentHandoff(run_id=run.id)
        handoff.handoff_id = result.handoff_id
        handoff.parent_agent = result.parent_agent
        handoff.child_agent = result.child_agent
        handoff.child_run_id = result.child_run_id
        handoff.dataset_id = result.dataset_id
        handoff.task_id = result.task_id
        handoff.trace_id = result.trace_id
        handoff.checkpoint_ref = result.checkpoint_ref
        handoff.artifact_ref = result.artifact_ref
        handoff.handoff_status = result.handoff_status
        handoff.answer_summary = result.answer_summary
        handoff.row_count = result.row_count
        handoff.column_count = result.column_count
        handoff.status_reason = result.status_reason
        handoff.error_code = result.error_code
        handoff.error_summary = result.error_summary
        if result.handoff_status in _TERMINAL_HANDOFF_STATUS_TO_RUN_STATUS:
            handoff.completed_at = datetime.now(timezone.utc)
        self.db.add(handoff)  # 只落 BIAgentHandoffResult 白名单字段，避免 DatasetAgent 内部执行态写入 handoff 表。
        return handoff

    def _complete_run_from_handoff(self, *, run: BIAgentRun, result: BIAgentHandoffResult) -> None:
        run.phase = "summarize_run"
        run.status = _TERMINAL_HANDOFF_STATUS_TO_RUN_STATUS.get(result.handoff_status, "running")
        run.status_reason = result.status_reason or f"handoff_{result.handoff_status}"
        run.error_code = result.error_code
        run.error_summary = result.error_summary
        if run.status in {"completed", "blocked", "failed", "cancelled"}:
            run.completed_at = datetime.now(timezone.utc)
        self.db.add(run)  # run 只表达外层阶段和终态；DatasetAgent 细节通过 refs 回看。


def _default_handoff_port(db: Session) -> BIHandoffPort:
    from app.domains.bi.agent.native_handoff import AgentScopeNativeBIHandoff

    return AgentScopeNativeBIHandoff.from_db(db)
