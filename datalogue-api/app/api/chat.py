# ============================================================
# File Name   : chat.py
# Description:
#   旧 Chat 路由兼容层。
#
# Responsibilities:
#   - 明确下线旧 /chat/stream 执行链路，避免请求继续进入旧 LeadAgent。
#   - 保留 /chat/feedback 的短期兼容转发。
#   - 对历史 Dataset Runtime direct 调试入口返回显式迁移响应。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.services.observability.feedback import submit_message_feedback

router = APIRouter()


@router.post("/dataset-runtime/direct")
def dataset_runtime_direct(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    """旧 /chat 直通调试入口已下线；主执行入口统一切到 Agentic Shell。"""

    raise HTTPException(
        status_code=410,
        detail="Dataset Runtime direct entry has moved behind /api/agentic-shell/tasks/stream",
    )


@router.post("/feedback")
def chat_feedback(payload: schemas.ChatFeedback, db: Session = Depends(get_db)):
    """短期兼容旧反馈路由；消息反馈的真实写入仍由 observability feedback service 承接。"""

    return submit_message_feedback(
        db,
        message_id=payload.message_id,
        action=payload.action,
        comment=payload.comment,
        trace_id=payload.trace_id,
        reason=payload.reason,
    )
