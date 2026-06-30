# ============================================================
# File Name   : agentscope_workbench.py
# Description:
#   AgentScope 工作台本地镜像模型，用于把新会话、消息、事件和产物引用落到 Datalogue 可查询的持久层。
#
# Responsibilities:
#   - 保存 C3 新会话的 AgentScope-compatible session/message/event/ref。
#   - 为 Workbench View Model 和受控 retry 提供稳定的业务级状态来源。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.core.database import Base


def _json_type():
    """兼容 SQLite 测试和 PostgreSQL 生产环境的 JSON 类型。"""

    return JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class AgentScopeSession(Base):
    __tablename__ = "agentscope_session"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String(80), nullable=False, unique=True, index=True)
    source_type = Column(String(40), nullable=False, default="agentscope", server_default="agentscope", index=True)
    legacy_conversation_id = Column(Integer, nullable=True, index=True)
    title = Column(String(200), nullable=True)
    status = Column(String(30), nullable=False, default="active", server_default="active", index=True)
    metadata_json = Column(_json_type(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)


class AgentScopeMessage(Base):
    __tablename__ = "agentscope_message"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(80), nullable=False, unique=True, index=True)
    thread_id = Column(String(80), nullable=False, index=True)
    role = Column(String(20), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="created", server_default="created", index=True)
    content_summary = Column(Text, nullable=True)
    business_payload_json = Column(_json_type(), nullable=False, default=dict)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)


class AgentScopeEvent(Base):
    __tablename__ = "agentscope_event"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(80), nullable=False, unique=True, index=True)
    thread_id = Column(String(80), nullable=False, index=True)
    message_id = Column(String(80), nullable=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    trace_id = Column(String(120), nullable=True, index=True)
    payload_json = Column(_json_type(), nullable=False, default=dict)
    visibility = Column(String(20), nullable=False, default="user", server_default="user", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AgentScopeRef(Base):
    __tablename__ = "agentscope_ref"
    __table_args__ = (
        UniqueConstraint(
            "thread_id",
            "message_id",
            "ref_type",
            "ref_value",
            "relation",
            name="uq_agentscope_ref_thread_message_ref_relation",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String(80), nullable=False, index=True)
    message_id = Column(String(80), nullable=True, index=True)
    ref_type = Column(String(40), nullable=False, index=True)
    ref_value = Column(String(200), nullable=False, index=True)
    relation = Column(String(40), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
