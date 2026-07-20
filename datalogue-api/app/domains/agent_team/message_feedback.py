# ============================================================
# File Name   : message_feedback.py
# Description:
#   问数回答反馈本地写入服务。
#
# Responsibilities:
#   - 校验 assistant message 并更新本地 response_metadata。
#   - 保持反馈能力独立于已下线的 Trace/Observability 子包。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import models
from app.core.time import utc_now

ACTION_TO_SCORE = {
    "approve": 1,
    "thumbs_up": 1,
    "like": 1,
    "reject": 0,
    "thumbs_down": 0,
    "dislike": 0,
}


def submit_message_feedback(
    db: Session,
    *,
    message_id: int,
    owner_user_id: int | None = None,
    action: str,
    comment: str | None = None,
    trace_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """提交消息反馈；当前只更新本地消息 metadata。"""

    query = db.query(models.Message).filter(models.Message.id == message_id)
    if owner_user_id is not None:
        # 反馈对象必须属于当前用户会话；关联查询同时封堵顺序 message_id 枚举。
        query = query.join(
            models.Conversation,
            models.Conversation.id == models.Message.conversation_id,
        ).filter(models.Conversation.user_id == owner_user_id)
    message = query.one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="只能反馈 assistant 消息")
    normalized = (action or "").strip().lower()
    if normalized not in ACTION_TO_SCORE and normalized != "modify":
        raise HTTPException(status_code=400, detail="不支持的反馈动作")

    metadata = dict(message.response_metadata or {})
    observability_meta = dict(metadata.get("observability") or {})
    stored_trace_id = observability_meta.get("trace_id")
    if trace_id and stored_trace_id and trace_id != stored_trace_id:
        raise HTTPException(status_code=409, detail="trace_id 与消息记录不匹配")
    effective_trace_id = trace_id or stored_trace_id
    feedback_payload = {
        "action": normalized,
        "score": ACTION_TO_SCORE.get(normalized),
        "comment": comment,
        "reason": reason,
        "updated_at": utc_now().isoformat(),
    }
    metadata["feedback"] = feedback_payload
    message.response_metadata = metadata
    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "ok": True,
        "status": normalized,
        "message_id": message.id,
        "trace_id": effective_trace_id,
        "feedback": feedback_payload,
        "observability_synced": False,
        "partial_success": False,
    }
