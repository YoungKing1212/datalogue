# ============================================================
# File Name   : chat.py
# Description:
#   消息反馈相关 Pydantic Schema。
#
# Responsibilities:
#   - 校验 assistant 消息反馈请求。
#   - 保留当前 /api/messages/{message_id}/feedback 使用的 DTO。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from typing import Optional

from pydantic import BaseModel


class ChatFeedback(BaseModel):
    message_id: int
    action: str  # approve / reject / modify
    comment: Optional[str] = None
    trace_id: Optional[str] = None
    reason: Optional[str] = None
