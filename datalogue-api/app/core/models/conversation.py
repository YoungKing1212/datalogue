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

from datetime import datetime

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, JSON, ForeignKey, DateTime, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import relationship

from app.core.database import Base


def _json_type():
    """兼容 SQLite 测试和 PostgreSQL 生产环境的 JSON 类型。"""

    return JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class Conversation(Base):
    __tablename__ = "conversation"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=True)
    title = Column(String(200), nullable=False)
    thread_id = Column(String(64))
    user_id = Column(Integer, nullable=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
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
    response_metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SQLDiagnosisLog(Base):
    __tablename__ = "sql_diagnosis_log"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    question = Column(Text)
    sql = Column(Text)
    error = Column(Text)
    diagnosis = Column(JSON)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PendingClarification(Base):
    __tablename__ = "pending_clarification"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    clarification_type = Column(String(50), nullable=False, default="term_conflict")
    status = Column(String(20), nullable=False, default="pending", index=True)
    original_question = Column(Text, nullable=False)
    conflict_payload = Column(JSON)
    candidates = Column(JSON)
    expires_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime)
    selected_payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ObservabilityTraceIndex(Base):
    __tablename__ = "observability_trace_index"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(120), nullable=False, index=True)
    trace_session_id = Column(String(120), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("message.id"), nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    entry_route = Column(String(60), index=True)
    status = Column(String(30), nullable=False, default="success", server_default="success", index=True)
    total_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    total_cost = Column(Float, nullable=False, default=0, server_default="0")
    metadata_json = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class TraceAnnotationCandidate(Base):
    __tablename__ = "trace_annotation_candidate"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(120), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("message.id"), nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    reason = Column(String(100), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending", server_default="pending", index=True)
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class QueryArtifact(Base):
    __tablename__ = "query_artifact"

    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(String(120), nullable=False, unique=True, index=True)
    kind = Column(String(40), nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("message.id"), nullable=True, index=True)
    trace_id = Column(String(120), nullable=True, index=True)
    content_json = Column(_json_type())
    content_text = Column(Text)
    content_mime = Column(String(80), nullable=False, default="application/json", server_default="application/json")
    size_bytes = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class ConversationState(Base):
    __tablename__ = "conversation_state"

    session_id = Column(String(120), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True)
    messages = Column(_json_type(), nullable=False, default=list)
    compacted_summary = Column(Text)
    facts = Column(_json_type(), nullable=False, default=list)
    resolved_time_context = Column(_json_type())
    active_dataset_id = Column(String(64))
    pending_clarification = Column(_json_type())
    subagent_capsules = Column(_json_type(), nullable=False, default=dict)
    turn_index = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(16), nullable=False, default="idle", server_default="idle", index=True)
    lock_owner = Column(String(80))
    locked_until = Column(DateTime(timezone=True), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
