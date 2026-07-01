# ============================================================
# File Name   : bi_lead_agent.py
# Description:
#   BI LeadAgent K1 编排状态持久化模型。
#
# Responsibilities:
#   - 保存 LeadAgent run、用户确认和 DatasetAgent handoff 的轻量状态。
#   - 为确认回放、子 Agent 移交追踪和失败诊断提供稳定数据库契约。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.core.database import Base


def _json_type():
    """兼容 SQLite 测试和 PostgreSQL 生产环境的 JSON 类型。"""

    return JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class BILeadAgentRun(Base):
    __tablename__ = "bi_lead_agent_run"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(
        String(40),
        nullable=False,
        default="created",
        server_default="created",
        index=True,
    )  # LeadAgent 总状态，只记录路由/确认/移交阶段，不承载 DatasetAgent 内部执行明细。
    phase = Column(String(60), nullable=False, default="created", server_default="created", index=True)
    question = Column(Text, nullable=False)
    task_id = Column(String(120), nullable=True, index=True)
    trace_id = Column(String(120), nullable=True, unique=True, index=True)
    status_reason = Column(Text, nullable=True)  # 给前端和重放链路看的状态原因，避免只靠枚举猜测失败边界。
    error_code = Column(String(80), nullable=True, index=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    confirmation = relationship(
        "BILeadAgentConfirmation",
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    handoff = relationship(
        "BIAgentHandoff",
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )


class BILeadAgentConfirmation(Base):
    __tablename__ = "bi_lead_agent_confirmation"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_bi_lead_agent_confirmation_run_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("bi_lead_agent_run.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    confirmed_question = Column(Text, nullable=False)
    task_goal = Column(Text, nullable=True)
    capability_snapshot_json = Column(_json_type(), nullable=False, default=dict)
    routing_rationale = Column(Text, nullable=True)
    risk_notice = Column(Text, nullable=True)
    user_decision = Column(
        String(40),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )  # 用户确认边界：pending/approved/rejected/expired，K1 只保存决策结果和路由级摘要。
    trace_id = Column(String(120), nullable=True, index=True)
    parent_run_id = Column(String(120), nullable=True, index=True)
    status_reason = Column(Text, nullable=True)
    error_code = Column(String(80), nullable=True, index=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    decided_at = Column(DateTime(timezone=True), nullable=True, index=True)

    run = relationship("BILeadAgentRun", back_populates="confirmation")


class BIAgentHandoff(Base):
    __tablename__ = "bi_agent_handoff"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_bi_agent_handoff_run_id"),
        UniqueConstraint("handoff_id", name="uq_bi_agent_handoff_handoff_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("bi_lead_agent_run.id", ondelete="CASCADE"), nullable=False, index=True)
    handoff_id = Column(String(120), nullable=False, index=True)
    parent_agent = Column(String(80), nullable=False, default="bi_lead_agent", server_default="bi_lead_agent", index=True)
    child_agent = Column(String(80), nullable=False, index=True)
    child_run_id = Column(String(120), nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("semantic_dataset.id"), nullable=True, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    trace_id = Column(String(120), nullable=True, index=True)
    checkpoint_ref = Column(String(200), nullable=True, index=True)
    artifact_ref = Column(String(200), nullable=True, index=True)
    handoff_status = Column(
        String(40),
        nullable=False,
        default="created",
        server_default="created",
        index=True,
    )  # 子 Agent 移交状态：created/running/completed/failed，用于 LeadAgent 回放和故障定位。
    answer_summary = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    status_reason = Column(Text, nullable=True)
    error_code = Column(String(80), nullable=True, index=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    run = relationship("BILeadAgentRun", back_populates="handoff")
