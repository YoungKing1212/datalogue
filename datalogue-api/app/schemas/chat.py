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

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None
    dataset_id: Optional[int] = None


class ChatFeedback(BaseModel):
    message_id: int
    action: str  # approve / reject / modify
    comment: Optional[str] = None
