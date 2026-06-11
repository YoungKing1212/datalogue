# ============================================================
# File Name   : feedback.py
# Description:
#   问数回答反馈与 Langfuse Score 写入服务。
#
# Responsibilities:
#   - 校验 assistant message 并更新本地 response_metadata。
#   - 将点赞/点踩写入 Langfuse score，失败时返回 partial success。
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
from app.services.observability.tracer import get_observability_tracer


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
    """提交消息反馈并尽力同步 Langfuse score。"""

    message = db.get(models.Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="只能反馈 assistant 消息")
    normalized = (action or "").strip().lower()
    if normalized not in ACTION_TO_SCORE and normalized != "modify":
        raise HTTPException(status_code=400, detail="不支持的反馈动作")

    metadata = dict(message.response_metadata or {})
    langfuse_meta = dict(metadata.get("langfuse") or {})
    stored_trace_id = langfuse_meta.get("trace_id")
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

    langfuse_synced = False
    if normalized != "modify":
        langfuse_synced = get_observability_tracer().score_trace(
            trace_id=effective_trace_id,
            name="user_feedback",
            value=ACTION_TO_SCORE[normalized],
            data_type="NUMERIC",
            comment=comment,
            metadata={"reason": reason, "message_id": message_id, "action": normalized},
        )

    return {
        "ok": True,
        "status": normalized,
        "message_id": message.id,
        "trace_id": effective_trace_id,
        "feedback": feedback_payload,
        "langfuse_synced": langfuse_synced,
        "partial_success": bool(effective_trace_id and normalized != "modify" and not langfuse_synced),
    }
