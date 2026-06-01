from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class ConversationOut(BaseModel):
    id: int
    title: str
    thread_id: Optional[str] = None
    user_id: Optional[int] = None
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
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: List[MessageOut]
