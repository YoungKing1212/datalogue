# ============================================================
# File Name   : m8n9o0p1q2r3_add_late_table_comments.py
# Description:
#   补充后续新增表的中文表注释。
#
# Responsibilities:
#   - 为 conversation_state、dataset_subagent_manifest、query_artifact 写入表级中文注释。
#   - 兼容已有库中表不存在的情况，迁移时跳过缺失表。
#
# Author      : yangkai
# Created On  : 2026-06-22
# ============================================================

"""add_late_table_comments

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m8n9o0p1q2r3"
down_revision: Union[str, None] = "l7m8n9o0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_COMMENTS: list[tuple[str, str]] = [
    ("conversation_state", "多轮对话会话状态表"),
    ("dataset_subagent_manifest", "数据集 SubAgent Manifest 版本治理表"),
    ("query_artifact", "查询产物存储表"),
]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _apply_table_comments(comments: list[tuple[str, str | None]]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, comment in comments:
        if table not in existing_tables:
            continue
        if comment is None:
            bind.execute(sa.text(f"COMMENT ON TABLE {_quote_ident(table)} IS NULL"))
            continue
        escaped_comment = comment.replace("'", "''")
        bind.execute(
            sa.text(f"COMMENT ON TABLE {_quote_ident(table)} IS '{escaped_comment}'")
        )


def upgrade() -> None:
    _apply_table_comments(_TABLE_COMMENTS)


def downgrade() -> None:
    _apply_table_comments([(table, None) for table, _ in _TABLE_COMMENTS])
