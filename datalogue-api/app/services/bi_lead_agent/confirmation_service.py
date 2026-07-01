# ============================================================
# File Name   : confirmation_service.py
# Description:
#   BI LeadAgent K1 用户确认服务。
#
# Responsibilities:
#   - 保存用户对单数据集路由的确认快照。
#   - 根据确认结果更新 run 状态，并为 handoff 提供确认门禁。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.bi_lead_agent import BILeadAgentConfirmation, BILeadAgentRun
from app.schemas.bi_lead_agent import ConfirmBILeadAgentRunRequest


class BILeadAgentConfirmationService:
    """管理用户确认记录；只有 approved 确认可以放行到 DatasetAgent handoff。"""

    def __init__(self, db: Session):
        self.db = db

    def confirm(self, run_id: int, request: ConfirmBILeadAgentRunRequest) -> BILeadAgentConfirmation:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        if request.capability_snapshot.dataset_id != request.dataset_id:
            # 用户确认的是能力快照里的数据集；二者不一致时必须 fail closed，不能把 A 快照放行到 B 数据集。
            raise ValueError("DATASET_CONFIRMATION_MISMATCH")
        if run.confirmation is not None:
            # 单 run 只允许一次明确决策，避免前端重试/双击落到数据库唯一约束异常并变成 500。
            raise ValueError("CONFIRMATION_ALREADY_DECIDED")

        decided_at = datetime.now(timezone.utc)  # approved/rejected 都是用户明确决策，审计链路必须记录决策时间。
        status_reason = (
            "confirmation_approved" if request.user_decision == "approved" else "confirmation_rejected"
        )
        confirmation = BILeadAgentConfirmation(
            run_id=run.id,
            dataset_id=request.dataset_id,
            confirmed_question=request.confirmed_question,
            task_goal=request.task_goal,
            capability_snapshot_json=request.capability_snapshot.model_dump(),
            routing_rationale=request.routing_rationale,
            risk_notice=request.risk_notice,
            user_decision=request.user_decision,
            trace_id=run.trace_id,  # 确认记录继承父 run trace，保证后续 handoff 和审计链路可串联。
            parent_run_id=str(run.id),
            status_reason=status_reason,
            decided_at=decided_at,
        )

        run.phase = "confirm_run"
        run.status_reason = status_reason
        if request.user_decision == "approved":
            run.status = "running"  # approved 只表示确认门禁通过，真正 DatasetAgent 完成态由后续 handoff 更新。
        else:
            run.status = "blocked"  # rejected 是用户主动终止单数据集路线，必须阻断后续 handoff。

        self.db.add(confirmation)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(confirmation)
        self.db.refresh(run)
        return confirmation

    def require_approved_confirmation(self, run_id: int) -> BILeadAgentConfirmation:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        confirmation = run.confirmation
        if confirmation is None or confirmation.user_decision != "approved":
            raise ValueError("USER_CONFIRMATION_REQUIRED")
        return confirmation
