# ============================================================
# File Name   : j5k6l7m8n9o0_add_conversation_state.py
# Description:
#   新增多轮对话会话状态表。
#
# Responsibilities:
#   - 保存 LeadAgent 跨轮状态和 SubAgent 胶囊桶。
#   - 提供会话轮次锁字段，避免同一 session 并发半写。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

"""add_conversation_state

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-06-12 16:50:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("conversation_state"):
        op.create_table(
            "conversation_state",
            sa.Column("session_id", sa.String(length=120), nullable=False, comment="业务多轮会话 ID"),
            sa.Column("user_id", sa.String(length=64), nullable=False, comment="用户 ID"),
            sa.Column("messages", _json_type(), nullable=False, server_default=sa.text("'[]'"), comment="压缩前后的消息索引"),
            sa.Column("compacted_summary", sa.Text(), nullable=True, comment="长会话压缩摘要"),
            sa.Column("facts", _json_type(), nullable=False, server_default=sa.text("'[]'"), comment="会话内稳定事实"),
            sa.Column("resolved_time_context", _json_type(), nullable=True, comment="LeadAgent 最近解析的时间上下文"),
            sa.Column("active_dataset_id", sa.String(length=64), nullable=True, comment="当前活跃数据集 ID"),
            sa.Column("pending_clarification", _json_type(), nullable=True, comment="跨轮挂起澄清状态"),
            sa.Column("subagent_capsules", _json_type(), nullable=False, server_default=sa.text("'{}'"), comment="按数据集分桶的 SubAgent 状态胶囊"),
            sa.Column("turn_index", sa.Integer(), nullable=False, server_default="0", comment="已完成轮次"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="idle", comment="idle / turn_pending"),
            sa.Column("lock_owner", sa.String(length=80), nullable=True, comment="当前轮锁持有者"),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True, comment="轮次锁过期时间"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间"),
            sa.PrimaryKeyConstraint("session_id"),
            comment="多轮对话会话状态表",
        )

    indexes = {index["name"] for index in inspector.get_indexes("conversation_state")}
    if "ix_conversation_state_user_updated" not in indexes:
        op.create_index(
            "ix_conversation_state_user_updated",
            "conversation_state",
            ["user_id", "updated_at"],
        )
    if "ix_conversation_state_status" not in indexes:
        op.create_index("ix_conversation_state_status", "conversation_state", ["status"])
    if "ix_conversation_state_locked_until" not in indexes:
        op.create_index(
            "ix_conversation_state_locked_until",
            "conversation_state",
            ["locked_until"],
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("conversation_state"):
        return
    indexes = [idx.get("name") for idx in inspector.get_indexes("conversation_state")]
    for index_name in indexes:
        if index_name:
            op.drop_index(index_name, table_name="conversation_state")
    op.drop_table("conversation_state")
