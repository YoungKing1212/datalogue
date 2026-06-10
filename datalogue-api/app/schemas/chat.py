# ============================================================
# File Name   : chat.py
# Description:
#   聊天请求和响应的 Pydantic Schema。
#
# Responsibilities:
#   - 校验聊天输入参数。
#   - 序列化聊天回答、SQL 和执行元数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from typing import Any, Optional

from pydantic import BaseModel


class ClarificationResponse(BaseModel):
    clarification_id: Optional[int] = None
    selected_term_id: Optional[int] = None
    selected_index: Optional[int] = None
    selected_text: Optional[str] = None


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None
    dataset_id: Optional[int] = None
    clarification_response: Optional[ClarificationResponse | dict[str, Any]] = None


class ChatFeedback(BaseModel):
    message_id: int
    action: str  # approve / reject / modify
    comment: Optional[str] = None
