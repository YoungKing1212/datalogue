# ============================================================
# File Name   : run_service.py
# Description:
#   BI LeadAgent K1 run 状态服务。
#
# Responsibilities:
#   - 创建和更新 LeadAgent run 的外层编排状态。
#   - 查询 run 的安全响应 DTO，避免 DatasetAgent 内部上下文外泄。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.bi_lead_agent import BIAgentHandoff, BILeadAgentRun
from app.schemas.bi_lead_agent import BILeadAgentHandoffResult, BILeadAgentRunResponse


def _new_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class BILeadAgentRunService:
    """管理 BI LeadAgent 外层 run；K1 不承载 DatasetAgent 的执行明细。"""

    def __init__(self, db: Session):
        self.db = db

    def create_run(self, question: str, trace_id: str | None = None, task_id: str | None = None) -> BILeadAgentRun:
        run = BILeadAgentRun(
            status="created",
            phase="route_run",
            question=question,
            trace_id=(trace_id or "").strip() or _new_prefixed_id("bi-lead-trace"),
            task_id=(task_id or "").strip() or _new_prefixed_id("bi-lead-task"),
        )
        self.db.add(run)
        self.db.commit()  # run_id/trace/task 是后续确认和 handoff 的父级锚点，创建后立即落库。
        self.db.refresh(run)
        return run

    def mark_phase(
        self,
        run: BILeadAgentRun,
        phase: str,
        status: str,
        status_reason: str | None = None,
    ) -> BILeadAgentRun:
        run.phase = phase
        run.status = status
        run.status_reason = status_reason
        self.db.add(run)
        self.db.commit()  # 阶段切换需要及时持久化，便于前端轮询和失败恢复读取一致状态。
        self.db.refresh(run)
        return run

    def mark_failed(
        self,
        run: BILeadAgentRun,
        phase: str,
        error_code: str,
        error_summary: str,
    ) -> BILeadAgentRun:
        run.phase = phase
        run.status = "failed"
        run.status_reason = error_code  # status_reason 保留机器可读失败原因，UI 可再读取 error_summary 展示。
        run.error_code = error_code
        run.error_summary = error_summary
        run.completed_at = datetime.now(timezone.utc)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_response(self, run_id: int) -> BILeadAgentRunResponse:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")

        confirmation_id = run.confirmation.id if run.confirmation is not None else None
        handoff = self._handoff_response(run.handoff) if run.handoff is not None else None
        return BILeadAgentRunResponse(
            run_id=run.id,
            status=run.status,
            phase=run.phase,
            question=run.question,
            trace_id=run.trace_id,
            task_id=run.task_id,
            confirmation_id=confirmation_id,
            handoff=handoff,
            status_reason=run.status_reason,
            error_code=run.error_code,
            error_summary=run.error_summary,
        )

    @staticmethod
    def _handoff_response(handoff: BIAgentHandoff) -> BILeadAgentHandoffResult:
        # 只复制 BILeadAgentHandoffResult 允许的字段；禁止 __dict__/model_dump 透传内部 SQL、schema、raw rows。
        return BILeadAgentHandoffResult(
            handoff_id=handoff.handoff_id,
            parent_agent=handoff.parent_agent,
            child_agent=handoff.child_agent,
            child_run_id=handoff.child_run_id,
            dataset_id=handoff.dataset_id,
            task_id=handoff.task_id,
            trace_id=handoff.trace_id,
            handoff_status=handoff.handoff_status,
            answer_summary=handoff.answer_summary,
            artifact_ref=handoff.artifact_ref,
            checkpoint_ref=handoff.checkpoint_ref,
            row_count=handoff.row_count,
            column_count=handoff.column_count,
            status_reason=handoff.status_reason,
            error_code=handoff.error_code,
            error_summary=handoff.error_summary,
        )
