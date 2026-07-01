# ============================================================
# File Name   : messages.py
# Description:
#   消息级操作 API。
#
# Responsibilities:
#   - 接收 assistant 消息的人工反馈。
#   - 将反馈同步到本地消息 metadata 和 Observability Score。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.services.observability.feedback import submit_message_feedback

router = APIRouter()


@router.post("/{message_id}/feedback")
def message_feedback(
    message_id: int,
    payload: schemas.ChatFeedback,
    db: Session = Depends(get_db),
):
    """提交 assistant 消息反馈，并尽力写入 Observability score。"""

    return submit_message_feedback(
        db,
        message_id=message_id,
        action=payload.action,
        comment=payload.comment,
        trace_id=payload.trace_id,
        reason=payload.reason,
    )
