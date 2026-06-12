# ============================================================
# File Name   : f6a7b8c9d0e1_add_sql_diagnosis_log.py
# Description:
#   新增 SQL 执行失败诊断日志表。
#
# Responsibilities:
#   - 记录每次 SQL 执行失败后的结构化诊断。
#   - 支持后续按会话和数据集统计失败原因。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""add_sql_diagnosis_log

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09 17:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    table_exists = inspector.has_table("sql_diagnosis_log")
    existing_indexes = (
        {idx.get("name") for idx in inspector.get_indexes("sql_diagnosis_log")}
        if table_exists
        else set()
    )

    if not table_exists:
        op.create_table(
            "sql_diagnosis_log",
            sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
            sa.Column("conversation_id", sa.Integer(), nullable=True, comment='关联的会话 ID'),
            sa.Column("dataset_id", sa.Integer(), nullable=True, comment='关联的数据集 ID'),
            sa.Column("question", sa.Text(), nullable=True, comment='触发 SQL 的用户问题'),
            sa.Column("sql", sa.Text(), nullable=True, comment='执行失败的 SQL'),
            sa.Column("error", sa.Text(), nullable=True, comment='数据库返回的错误信息'),
            sa.Column("diagnosis", sa.JSON(), nullable=True, comment='结构化诊断结果'),
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False, comment='已重试次数'),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
                comment='创建时间',
            ),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
            sa.PrimaryKeyConstraint("id"),
            comment='SQL 执行失败诊断日志表',
        )
    if "ix_sql_diagnosis_log_conversation_id" not in existing_indexes:
        op.create_index(
            "ix_sql_diagnosis_log_conversation_id",
            "sql_diagnosis_log",
            ["conversation_id"],
        )
    if "ix_sql_diagnosis_log_dataset_id" not in existing_indexes:
        op.create_index("ix_sql_diagnosis_log_dataset_id", "sql_diagnosis_log", ["dataset_id"])
    if "ix_sql_diagnosis_log_id" not in existing_indexes:
        op.create_index("ix_sql_diagnosis_log_id", "sql_diagnosis_log", ["id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("sql_diagnosis_log"):
        return
    indexes = {idx.get("name") for idx in inspector.get_indexes("sql_diagnosis_log")}
    if "ix_sql_diagnosis_log_id" in indexes:
        op.drop_index("ix_sql_diagnosis_log_id", table_name="sql_diagnosis_log")
    if "ix_sql_diagnosis_log_dataset_id" in indexes:
        op.drop_index("ix_sql_diagnosis_log_dataset_id", table_name="sql_diagnosis_log")
    if "ix_sql_diagnosis_log_conversation_id" in indexes:
        op.drop_index("ix_sql_diagnosis_log_conversation_id", table_name="sql_diagnosis_log")
    op.drop_table("sql_diagnosis_log")
