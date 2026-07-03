# ============================================================
# File Name   : agent_team_task.py
# Description:
#   AgentScope Agent Team 任务真相源模型。
#
# Responsibilities:
#   - 保存一次 Agent Team task 的生命周期、AgentScope session/message 关联和安全 refs。
#   - 为 Chat UI、Workbench 和 artifact 审计提供 task_id 聚合主键。
#   - 暂时复用历史数据库表名，避免本次主链迁移引入破坏性数据迁移。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func

from app.core.database import Base


def _json_type():
    return JSON().with_variant(postgresql.JSONB(astext_type=postgresql.TEXT()), "postgresql")


class AgentTeamTask(Base):
    """Datalogue Agent Team 对外 task 真相源；不等同于 AgentScope SDK Message。"""

    # 数据库兼容：旧版本表名已经落库，代码层统一改为 AgentTeamTask。
    __tablename__ = "agentic_shell_task"
    __table_args__ = {"comment": "AgentScope Agent Team 任务真相源表"}

    id = Column(Integer, primary_key=True, index=True, comment="自增主键")
    task_id = Column(String(80), unique=True, nullable=False, index=True, comment="Agent Team task 对外稳定 ID")
    task_source = Column(String(40), nullable=False, index=True, comment="任务来源，字典：chat=聊天入口，workbench=工作台动作，dataset=数据集试问")
    task_type = Column(String(40), nullable=False, index=True, comment="任务类型，字典：bi_query=BI 问数任务")
    status = Column(String(40), nullable=False, default="created", index=True, comment="任务状态，字典：created/running/completed/failed/cancelled")
    selected_agent = Column(String(80), nullable=False, default="agent_team_leader", index=True, comment="本次任务的 Agent Team leader")
    parent_task_id = Column(String(80), nullable=True, index=True, comment="父任务 ID，用于 retry 追溯")
    agent_scope_session_id = Column(String(120), nullable=True, index=True, comment="关联的 AgentScope mirror session ID")
    thread_id = Column(String(120), nullable=True, index=True, comment="前端工作线程或会话线程 ID")
    message_id = Column(String(120), nullable=True, index=True, comment="关联的 assistant message ID")
    trace_id = Column(String(120), nullable=True, index=True, comment="链路追踪 ID")
    artifact_refs_json = Column(_json_type(), nullable=False, default=list, comment="本任务产生的脱敏 artifact refs")
    checkpoint_refs_json = Column(_json_type(), nullable=False, default=list, comment="本任务产生或消费的 checkpoint refs")
    request_payload_json = Column(_json_type(), nullable=False, default=dict, comment="清洗后的任务请求快照")
    final_payload_json = Column(_json_type(), nullable=False, default=dict, comment="清洗后的最终业务结果快照")
    error_payload_json = Column(_json_type(), nullable=False, default=dict, comment="清洗后的错误摘要")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )
