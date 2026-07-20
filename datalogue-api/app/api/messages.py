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

from app.api.deps import require_api_user
from app.core import models, schemas
from app.core.database import get_db
from app.domains.agent_team.message_feedback import submit_message_feedback

router = APIRouter()


@router.post("/{message_id}/feedback")
def message_feedback(
    message_id: int,
    payload: schemas.ChatFeedback,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_api_user),
):
    """提交 assistant 消息反馈，并写入本地消息 metadata。"""

    return submit_message_feedback(
        db,
        message_id=message_id,
        owner_user_id=current_user.id,
        action=payload.action,
        comment=payload.comment,
        trace_id=payload.trace_id,
        reason=payload.reason,
    )
