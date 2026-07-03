# ============================================================
# File Name   : bi_agent.py
# Description:
#   BI Agent K1 run-centric API 端点。
#
# Responsibilities:
#   - 提供 BI Agent run 创建、用户确认和 run 查询的最小 HTTP 契约。
#   - 只返回 BIAgentRunResponse 安全 DTO，不暴露 DatasetAgent 内部执行上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.bi_agent import (
    BIAgentRunResponse,
    ConfirmBIAgentRunRequest,
    CreateBIAgentRunRequest,
)
from app.agents.bi_agent.confirmation_service import BIAgentConfirmationService
from app.agents.bi_agent.handoff_service import BIAgentHandoffService
from app.agents.bi_agent.run_service import BIAgentRunService
from app.middlewares.lifecycle import log_lifecycle

router = APIRouter()

_NOT_FOUND_ERRORS = {"BI_LEAD_AGENT_RUN_NOT_FOUND"}
_BUSINESS_REQUEST_ERRORS = {
    "DATASET_CONFIRMATION_MISMATCH",
    "CONFIRMATION_ALREADY_DECIDED",
    "USER_CONFIRMATION_REQUIRED",
}


def _raise_http_error(exc: ValueError) -> NoReturn:
    """把服务层业务错误映射到 HTTP；未知 ValueError 仍按 400 处理，避免误映射成 404。"""

    error_code = str(exc)
    if error_code in _NOT_FOUND_ERRORS:
        raise HTTPException(status_code=404, detail=error_code) from exc
    if error_code in _BUSINESS_REQUEST_ERRORS:
        raise HTTPException(status_code=400, detail=error_code) from exc
    raise HTTPException(status_code=400, detail=error_code or "BI_LEAD_AGENT_REQUEST_INVALID") from exc


@router.post("/runs", response_model=BIAgentRunResponse)
def create_bi_agent_run(
    payload: CreateBIAgentRunRequest,
    db: Session = Depends(get_db),
) -> BIAgentRunResponse:
    """创建 BI Agent run，并立即进入用户确认等待态。"""

    run_service = BIAgentRunService(db)
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
    response = run_service.get_response(run.id)
    log_lifecycle(
        "bi_agent.api.create_run.completed",
        endpoint="/api/bi-agent/runs",
        run_id=response.run_id,
        trace_id=response.trace_id,
        task_id=response.task_id,
        status=response.status,
        phase=response.phase,
    )
    return response


@router.post("/runs/{run_id}/confirm", response_model=BIAgentRunResponse)
def confirm_bi_agent_run(
    run_id: int,
    payload: ConfirmBIAgentRunRequest,
    db: Session = Depends(get_db),
) -> BIAgentRunResponse:
    """保存用户确认并返回 run 安全视图；production handoff endpoint 留给后续任务。"""

    run_service = BIAgentRunService(db)
    confirmation_service = BIAgentConfirmationService(db)
    try:
        confirmation = confirmation_service.confirm(run_id, payload)
        response = run_service.get_response(run_id)
        log_lifecycle(
            "bi_agent.api.confirm_run.completed",
            endpoint="/api/bi-agent/runs/{run_id}/confirm",
            run_id=response.run_id,
            trace_id=response.trace_id,
            task_id=response.task_id,
            dataset_id=confirmation.dataset_id,
            confirmation_id=confirmation.id,
            status=response.status,
            phase=response.phase,
        )
        return response
    except ValueError as exc:
        _raise_http_error(exc)


@router.get("/runs/{run_id}", response_model=BIAgentRunResponse)
def get_bi_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> BIAgentRunResponse:
    """读取 BI Agent run 安全视图。"""

    try:
        return BIAgentRunService(db).get_response(run_id)
    except ValueError as exc:
        _raise_http_error(exc)


@router.post("/runs/{run_id}/handoff", response_model=BIAgentRunResponse)
async def handoff_bi_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> BIAgentRunResponse:
    """触发已确认 run 的 DatasetAgent handoff；API 层不直接接触 Dataset 原子工具。"""

    try:
        await BIAgentHandoffService(db).query_dataset(run_id=run_id)
        response = BIAgentRunService(db).get_response(run_id)
        log_lifecycle(
            "bi_agent.api.handoff_run.completed",
            endpoint="/api/bi-agent/runs/{run_id}/handoff",
            run_id=response.run_id,
            trace_id=response.trace_id,
            task_id=response.task_id,
            status=response.status,
            phase=response.phase,
            handoff_status=response.handoff.handoff_status if response.handoff else None,
            artifact_ref=response.handoff.artifact_ref if response.handoff else None,
            checkpoint_ref=response.handoff.checkpoint_ref if response.handoff else None,
        )
        return response
    except ValueError as exc:
        _raise_http_error(exc)
