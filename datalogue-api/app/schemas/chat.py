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
