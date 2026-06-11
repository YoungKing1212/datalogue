# ============================================================
# File Name   : f1a2b3c4d5e6_add_observability_tables.py
# Description:
#   新增 Langfuse 本地观测索引和标注候选表。
#
# Responsibilities:
#   - 保存 trace/session 与本地会话消息的索引关系。
#   - 支持点踩、失败和低质量 trace 的人工标注候选池。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

"""add_observability_tables

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-06-11 11:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    inspector = inspect(op.get_bind())
    indexes = {idx.get("name") for idx in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table("observability_trace_index"):
        op.create_table(
            "observability_trace_index",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("langfuse_trace_id", sa.String(length=120), nullable=False),
            sa.Column("langfuse_session_id", sa.String(length=120), nullable=False),
            sa.Column("conversation_id", sa.Integer(), nullable=True),
            sa.Column("message_id", sa.Integer(), nullable=True),
            sa.Column("dataset_id", sa.Integer(), nullable=True),
            sa.Column("entry_route", sa.String(length=60), nullable=True),
            sa.Column("status", sa.String(length=30), server_default="success", nullable=False),
            sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("total_cost", sa.Float(), server_default="0", nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["message.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, columns in {
        "ix_observability_trace_index_id": ["id"],
        "ix_observability_trace_index_langfuse_trace_id": ["langfuse_trace_id"],
        "ix_observability_trace_index_langfuse_session_id": ["langfuse_session_id"],
        "ix_observability_trace_index_conversation_id": ["conversation_id"],
        "ix_observability_trace_index_message_id": ["message_id"],
        "ix_observability_trace_index_dataset_id": ["dataset_id"],
        "ix_observability_trace_index_entry_route": ["entry_route"],
        "ix_observability_trace_index_status": ["status"],
        "ix_observability_trace_index_created_at": ["created_at"],
    }.items():
        _create_index_if_missing("observability_trace_index", index_name, columns)

    if not inspector.has_table("trace_annotation_candidate"):
        op.create_table(
            "trace_annotation_candidate",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("langfuse_trace_id", sa.String(length=120), nullable=False),
            sa.Column("conversation_id", sa.Integer(), nullable=True),
            sa.Column("message_id", sa.Integer(), nullable=True),
            sa.Column("dataset_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["message.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, columns in {
        "ix_trace_annotation_candidate_id": ["id"],
        "ix_trace_annotation_candidate_langfuse_trace_id": ["langfuse_trace_id"],
        "ix_trace_annotation_candidate_conversation_id": ["conversation_id"],
        "ix_trace_annotation_candidate_message_id": ["message_id"],
        "ix_trace_annotation_candidate_dataset_id": ["dataset_id"],
        "ix_trace_annotation_candidate_reason": ["reason"],
        "ix_trace_annotation_candidate_status": ["status"],
        "ix_trace_annotation_candidate_created_at": ["created_at"],
    }.items():
        _create_index_if_missing("trace_annotation_candidate", index_name, columns)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table_name in ("trace_annotation_candidate", "observability_trace_index"):
        if not inspector.has_table(table_name):
            continue
        indexes = [idx.get("name") for idx in inspector.get_indexes(table_name)]
        for index_name in indexes:
            if index_name:
                op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
