# ============================================================
# File Name   : k6l7m8n9o0p1_add_query_artifact.py
# Description:
#   新增查询产物存储表。
#
# Responsibilities:
#   - 保存 SQL 结果、报告和 SubAgent 完成态的 artifact 引用。
#   - 为 TTL 清理和按会话/数据集追踪产物提供索引。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

"""add_query_artifact

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "k6l7m8n9o0p1"
down_revision: Union[str, None] = "j5k6l7m8n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _existing_index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {item["name"] for item in sa.inspect(bind).get_indexes(table_name)}


def _create_index_if_missing(
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if index_name in _existing_index_names("query_artifact"):
        return
    op.create_index(index_name, "query_artifact", columns, unique=unique)


def _drop_index_if_exists(index_name: str) -> None:
    if not _has_table("query_artifact"):
        return
    if index_name not in _existing_index_names("query_artifact"):
        return
    op.drop_index(index_name, table_name="query_artifact")


def upgrade() -> None:
    if not _has_table("query_artifact"):
        op.create_table(
            "query_artifact",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("artifact_id", sa.String(length=120), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=True),
            sa.Column("conversation_id", sa.Integer(), nullable=True),
            sa.Column("message_id", sa.Integer(), nullable=True),
            sa.Column("trace_id", sa.String(length=120), nullable=True),
            sa.Column("content_json", _json_type(), nullable=True),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column(
                "content_mime",
                sa.String(length=80),
                server_default="application/json",
                nullable=False,
            ),
            sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["message.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_query_artifact_id"), ["id"])
    _create_index_if_missing(
        op.f("ix_query_artifact_artifact_id"),
        ["artifact_id"],
        unique=True,
    )
    _create_index_if_missing(op.f("ix_query_artifact_kind"), ["kind"])
    _create_index_if_missing(op.f("ix_query_artifact_dataset_id"), ["dataset_id"])
    _create_index_if_missing(op.f("ix_query_artifact_conversation_id"), ["conversation_id"])
    _create_index_if_missing(op.f("ix_query_artifact_message_id"), ["message_id"])
    _create_index_if_missing(op.f("ix_query_artifact_trace_id"), ["trace_id"])
    _create_index_if_missing(op.f("ix_query_artifact_expires_at"), ["expires_at"])
    _create_index_if_missing(op.f("ix_query_artifact_created_at"), ["created_at"])


def downgrade() -> None:
    _drop_index_if_exists(op.f("ix_query_artifact_created_at"))
    _drop_index_if_exists(op.f("ix_query_artifact_expires_at"))
    _drop_index_if_exists(op.f("ix_query_artifact_trace_id"))
    _drop_index_if_exists(op.f("ix_query_artifact_message_id"))
    _drop_index_if_exists(op.f("ix_query_artifact_conversation_id"))
    _drop_index_if_exists(op.f("ix_query_artifact_dataset_id"))
    _drop_index_if_exists(op.f("ix_query_artifact_kind"))
    _drop_index_if_exists(op.f("ix_query_artifact_artifact_id"))
    _drop_index_if_exists(op.f("ix_query_artifact_id"))
    if _has_table("query_artifact"):
        op.drop_table("query_artifact")
