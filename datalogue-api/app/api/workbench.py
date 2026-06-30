# ============================================================
# File Name   : workbench.py
# Description:
#   C3 Workbench 后端视图 API。
#
# Responsibilities:
#   - 提供 Chat 右侧详情面板所需的线程 View Model。
#   - 提供 artifact:<uuid> 的脱敏工作台摘要读取口。
#   - 为后续独立 BI Workbench 页面预留稳定后端契约。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.agentscope_workbench import (
    WorkbenchArtifactView,
    WorkbenchRetryRequest,
    WorkbenchRetryResponse,
    WorkbenchThreadView,
)
from app.services.workbench_actions import (
    WorkbenchActionConflictError,
    WorkbenchActionNotFoundError,
    request_controlled_retry,
)
from app.services.workbench_view_model import (
    WorkbenchViewNotFoundError,
    build_workbench_artifact_view,
    build_workbench_thread_view,
)

router = APIRouter()


@router.get("/thread/{thread_id}", response_model=WorkbenchThreadView)
def get_workbench_thread(thread_id: str, db: Session = Depends(get_db)) -> WorkbenchThreadView:
    """读取 C3 Workbench 线程视图；as_* 来自 mirror，conv_* 为旧会话只读回放。"""

    try:
        return build_workbench_thread_view(db, thread_id=thread_id)
    except WorkbenchViewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workbench thread not found") from exc
    except ValueError as exc:
        # View Model 是用户可见层，任何泄露检测命中都不返回部分数据。
        raise HTTPException(status_code=400, detail="workbench view unavailable") from exc


@router.get("/artifact/{artifact_ref:path}", response_model=WorkbenchArtifactView)
def get_workbench_artifact(
    artifact_ref: str,
    thread_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorkbenchArtifactView:
    """读取工作台 artifact 摘要；只返回业务级 preview，不返回原始结果或 RepairPlan patch 主体。"""

    try:
        return build_workbench_artifact_view(db, artifact_ref=artifact_ref, thread_id=thread_id)
    except WorkbenchViewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="artifact view unavailable") from exc


@router.post("/actions/retry", response_model=WorkbenchRetryResponse)
def post_workbench_retry(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> WorkbenchRetryResponse:
    """受理 Workbench 受控 retry；只接收 checkpoint/ref，不直接执行查询。"""

    try:
        request = WorkbenchRetryRequest.model_validate(payload)
        return request_controlled_retry(db, request=request)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="invalid retry payload") from exc
    except WorkbenchActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workbench retry target not found") from exc
    except WorkbenchActionConflictError as exc:
        raise HTTPException(status_code=409, detail="workbench retry unavailable") from exc
