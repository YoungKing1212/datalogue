# ============================================================
# File Name   : feedback.py
# Description:
#   问数回答反馈本地写入服务。
#
# Responsibilities:
#   - 校验 assistant message 并更新本地 response_metadata。
#   - 暂不把反馈同步到外部 Trace/Score 系统。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
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
    action: str,
    comment: str | None = None,
    trace_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """提交消息反馈；当前只更新本地消息 metadata。"""

    message = db.get(models.Message, message_id)
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
        "updated_at": datetime.utcnow().isoformat(),
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
