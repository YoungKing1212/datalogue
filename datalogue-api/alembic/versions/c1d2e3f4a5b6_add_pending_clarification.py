# ============================================================
# File Name   : c1d2e3f4a5b6_add_pending_clarification.py
# Description:
#   新增问数澄清态持久化表。
#
# Responsibilities:
#   - 保存会话内待处理的术语冲突澄清候选。
#   - 支持用户下一轮回复后恢复原问题继续执行 QueryGraph。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

"""add_pending_clarification

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-06-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("pending_clarification"):
        op.create_table(
            "pending_clarification",
            sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
            sa.Column("conversation_id", sa.Integer(), nullable=False, comment='所属会话 ID'),
            sa.Column("dataset_id", sa.Integer(), nullable=True, comment='关联的数据集 ID'),
            sa.Column("clarification_type", sa.String(length=50), nullable=False, comment='澄清类型（term_conflict等）'),
            sa.Column("status", sa.String(length=20), nullable=False, comment='处理状态（pending/resolved/expired）'),
            sa.Column("original_question", sa.Text(), nullable=False, comment='触发澄清的原始问题'),
            sa.Column("conflict_payload", sa.JSON(), nullable=True, comment='冲突信息载体'),
            sa.Column("candidates", sa.JSON(), nullable=True, comment='供用户选择的候选项列表'),
            sa.Column("expires_at", sa.DateTime(), nullable=False, comment='澄清过期时间'),
            sa.Column("resolved_at", sa.DateTime(), nullable=True, comment='澄清解决时间'),
            sa.Column("selected_payload", sa.JSON(), nullable=True, comment='用户最终选择的载体'),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment='创建时间'),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment='待处理术语澄清表',
        )

    existing_indexes = {
        idx.get("name") for idx in inspector.get_indexes("pending_clarification")
    }
    if "ix_pending_clarification_id" not in existing_indexes:
        op.create_index("ix_pending_clarification_id", "pending_clarification", ["id"])
    if "ix_pending_clarification_conversation_id" not in existing_indexes:
        op.create_index(
            "ix_pending_clarification_conversation_id",
            "pending_clarification",
            ["conversation_id"],
        )
    if "ix_pending_clarification_dataset_id" not in existing_indexes:
        op.create_index(
            "ix_pending_clarification_dataset_id",
            "pending_clarification",
            ["dataset_id"],
        )
    if "ix_pending_clarification_status" not in existing_indexes:
        op.create_index(
            "ix_pending_clarification_status",
            "pending_clarification",
            ["status"],
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("pending_clarification"):
        existing_indexes = {
            idx.get("name") for idx in inspector.get_indexes("pending_clarification")
        }
        for name in (
            "ix_pending_clarification_status",
            "ix_pending_clarification_dataset_id",
            "ix_pending_clarification_conversation_id",
            "ix_pending_clarification_id",
        ):
            if name in existing_indexes:
                op.drop_index(name, table_name="pending_clarification")
        op.drop_table("pending_clarification")
