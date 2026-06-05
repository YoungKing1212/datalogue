# ============================================================
# File Name   : conversation.py
# Description:
#   会话和消息持久化模型。
#
# Responsibilities:
#   - 存储聊天会话、消息、SQL 和执行轨迹。
#   - 表示 assistant-ui 线程历史数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from sqlalchemy import Boolean, Column, Integer, String, Text, JSON, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversation"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=True)
    title = Column(String(200), nullable=False)
    thread_id = Column(String(64))
    user_id = Column(Integer, nullable=True)
    archived = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship(
        "Message",
        backref="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "message"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sql_list = Column(JSON)
    report_html = Column(Text)
    token_usage = Column(JSON)
    step_trace = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
