# ============================================================
# File Name   : bi_lead_agent.py
# Description:
#   BI LeadAgent K1 run-centric API 端点。
#
# Responsibilities:
#   - 提供 LeadAgent run 创建、用户确认和 run 查询的最小 HTTP 契约。
#   - 只返回 BILeadAgentRunResponse 安全 DTO，不暴露 DatasetAgent 内部执行上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.bi_lead_agent import (
    BILeadAgentRunResponse,
    ConfirmBILeadAgentRunRequest,
    CreateBILeadAgentRunRequest,
)
from app.services.bi_lead_agent.confirmation_service import BILeadAgentConfirmationService
from app.services.bi_lead_agent.handoff_service import BIHandoffService
from app.services.bi_lead_agent.run_service import BILeadAgentRunService

router = APIRouter()

_NOT_FOUND_ERRORS = {"BI_LEAD_AGENT_RUN_NOT_FOUND"}
_BUSINESS_REQUEST_ERRORS = {
    "DATASET_CONFIRMATION_MISMATCH",
    "CONFIRMATION_ALREADY_DECIDED",
    "USER_CONFIRMATION_REQUIRED",
}


def _raise_http_error(exc: ValueError) -> None:
    """把服务层业务错误映射到 HTTP；未知 ValueError 仍按 400 处理，避免误映射成 404。"""

    error_code = str(exc)
    if error_code in _NOT_FOUND_ERRORS:
        raise HTTPException(status_code=404, detail=error_code) from exc
    if error_code in _BUSINESS_REQUEST_ERRORS:
        raise HTTPException(status_code=400, detail=error_code) from exc
    raise HTTPException(status_code=400, detail=error_code or "BI_LEAD_AGENT_REQUEST_INVALID") from exc


@router.post("/runs", response_model=BILeadAgentRunResponse)
def create_bi_lead_agent_run(
    payload: CreateBILeadAgentRunRequest,
    db: Session = Depends(get_db),
) -> BILeadAgentRunResponse:
    """创建 LeadAgent run，并立即进入用户确认等待态。"""

    run_service = BILeadAgentRunService(db)
    run = run_service.create_run(
        question=payload.question,
        trace_id=payload.trace_id,
        task_id=payload.task_id,
    )
    run_service.mark_phase(
        run,
        phase="confirm_run",
        status="waiting_confirmation",
        status_reason="confirmation_required",
    )  # Task 5 只建立 run-centric 确认门禁，不在创建阶段触发 DatasetAgent 原子工具或 handoff。
    return run_service.get_response(run.id)


@router.post("/runs/{run_id}/confirm", response_model=BILeadAgentRunResponse)
def confirm_bi_lead_agent_run(
    run_id: int,
    payload: ConfirmBILeadAgentRunRequest,
    db: Session = Depends(get_db),
) -> BILeadAgentRunResponse:
    """保存用户确认并返回 run 安全视图；production handoff endpoint 留给后续任务。"""

    run_service = BILeadAgentRunService(db)
    confirmation_service = BILeadAgentConfirmationService(db)
    try:
        confirmation_service.confirm(run_id, payload)
        return run_service.get_response(run_id)
    except ValueError as exc:
        _raise_http_error(exc)


@router.get("/runs/{run_id}", response_model=BILeadAgentRunResponse)
def get_bi_lead_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> BILeadAgentRunResponse:
    """读取 LeadAgent run 安全视图。"""

    try:
        return BILeadAgentRunService(db).get_response(run_id)
    except ValueError as exc:
        _raise_http_error(exc)


@router.post("/runs/{run_id}/handoff", response_model=BILeadAgentRunResponse)
async def handoff_bi_lead_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> BILeadAgentRunResponse:
    """触发已确认 run 的 DatasetAgent handoff；API 层不直接接触 Dataset 原子工具。"""

    try:
        await BIHandoffService(db).query_dataset(run_id=run_id)
        return BILeadAgentRunService(db).get_response(run_id)
    except ValueError as exc:
        _raise_http_error(exc)
