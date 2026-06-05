# ============================================================
# File Name   : conversation.py
# Description:
#   会话 API 的 Pydantic Schema。
#
# Responsibilities:
#   - 校验会话创建和更新请求。
#   - 序列化会话信息和消息历史。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class ConversationOut(BaseModel):
    id: int
    title: str
    thread_id: Optional[str] = None
    user_id: Optional[int] = None
    archived: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sql_list: Optional[List[str]] = None
    report_html: Optional[str] = None
    token_usage: Optional[dict] = None
    step_trace: Optional[List[dict]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: List[MessageOut]


class ConversationCreate(BaseModel):
    """创建空会话请求体（assistant-ui initialize 流程使用）。"""

    title: str = Field(default="新对话", max_length=200)
    thread_id: Optional[str] = Field(default=None, max_length=64)


class ConversationRename(BaseModel):
    """重命名请求体。"""

    title: str = Field(..., min_length=1, max_length=200)
