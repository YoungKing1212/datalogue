"""add agentic shell task

Revision ID: u1v2w3x4y5z6
Revises: r2s3t4u5v6w7
Create Date: 2026-07-02 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "u1v2w3x4y5z6"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agentic_shell_task",
        sa.Column("id", sa.Integer(), nullable=False, comment="自增主键"),
        sa.Column("task_id", sa.String(length=80), nullable=False, comment="Agentic Shell task 对外稳定 ID"),
        sa.Column("task_source", sa.String(length=40), nullable=False, comment="任务来源，字典：chat=聊天入口，workbench=工作台动作，dataset=数据集试问"),
        sa.Column("task_type", sa.String(length=40), nullable=False, comment="任务类型，字典：bi_query=BI 问数任务"),
        sa.Column("status", sa.String(length=40), nullable=False, comment="任务状态，字典：created/running/completed/failed/cancelled"),
        sa.Column("selected_agent", sa.String(length=80), nullable=False, comment="本次任务选择的业务 Agent"),
        sa.Column("parent_task_id", sa.String(length=80), nullable=True, comment="父任务 ID，用于 retry/handoff 追溯"),
        sa.Column("agent_scope_session_id", sa.String(length=120), nullable=True, comment="关联的 AgentScope mirror session ID"),
        sa.Column("thread_id", sa.String(length=120), nullable=True, comment="前端工作线程或会话线程 ID"),
        sa.Column("message_id", sa.String(length=120), nullable=True, comment="关联的 assistant message ID"),
        sa.Column("trace_id", sa.String(length=120), nullable=True, comment="链路追踪 ID"),
        sa.Column("artifact_refs_json", _json_type(), nullable=False, comment="本任务产生的脱敏 artifact refs"),
        sa.Column("checkpoint_refs_json", _json_type(), nullable=False, comment="本任务产生或消费的 checkpoint refs"),
        sa.Column("request_payload_json", _json_type(), nullable=False, comment="清洗后的任务请求快照"),
        sa.Column("final_payload_json", _json_type(), nullable=False, comment="清洗后的最终业务结果快照"),
        sa.Column("error_payload_json", _json_type(), nullable=False, comment="清洗后的错误摘要"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        comment="Agentic Shell 统一任务入口的任务真相源表",
    )
    for column in (
        "task_id",
        "task_source",
        "task_type",
        "status",
        "selected_agent",
        "parent_task_id",
        "agent_scope_session_id",
        "thread_id",
        "message_id",
        "trace_id",
    ):
        op.create_index(f"ix_agentic_shell_task_{column}", "agentic_shell_task", [column])


def downgrade() -> None:
    for column in (
        "trace_id",
        "message_id",
        "thread_id",
        "agent_scope_session_id",
        "parent_task_id",
        "selected_agent",
        "status",
        "task_type",
        "task_source",
        "task_id",
    ):
        op.drop_index(f"ix_agentic_shell_task_{column}", table_name="agentic_shell_task")
    op.drop_table("agentic_shell_task")
