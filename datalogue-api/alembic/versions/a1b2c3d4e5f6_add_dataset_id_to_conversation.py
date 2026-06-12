# ============================================================
# File Name   : a1b2c3d4e5f6_add_dataset_id_to_conversation.py
# Description:
#   为 conversation 表补充 dataset_id 外键列。
#
# Responsibilities:
#   - 保存历史对话所属数据集，支持切换会话时恢复数据集选择。
#   - 降级时移除会话数据集绑定字段和索引。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""add_dataset_id_to_conversation

Revision ID: a1b2c3d4e5f6
Revises: 0f1e2d3c4b5a
Create Date: 2026-06-09 19:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0f1e2d3c4b5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("conversation")}
    indexes = {index["name"] for index in inspector.get_indexes("conversation")}
    if "dataset_id" not in columns:
        op.add_column(
            "conversation",
            sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("semantic_dataset.id"), nullable=True, comment='会话绑定的语义数据集 ID'),
        )
    if "ix_conversation_dataset_id" not in indexes:
        op.create_index("ix_conversation_dataset_id", "conversation", ["dataset_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("conversation")}
    indexes = {index["name"] for index in inspector.get_indexes("conversation")}
    if "ix_conversation_dataset_id" in indexes:
        op.drop_index("ix_conversation_dataset_id", table_name="conversation")
    if "dataset_id" in columns:
        op.drop_column("conversation", "dataset_id")
