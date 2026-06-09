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


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sql_diagnosis_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("dataset_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("sql", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sql_diagnosis_log_conversation_id", "sql_diagnosis_log", ["conversation_id"])
    op.create_index("ix_sql_diagnosis_log_dataset_id", "sql_diagnosis_log", ["dataset_id"])
    op.create_index("ix_sql_diagnosis_log_id", "sql_diagnosis_log", ["id"])


def downgrade() -> None:
    op.drop_index("ix_sql_diagnosis_log_id", table_name="sql_diagnosis_log")
    op.drop_index("ix_sql_diagnosis_log_dataset_id", table_name="sql_diagnosis_log")
    op.drop_index("ix_sql_diagnosis_log_conversation_id", table_name="sql_diagnosis_log")
    op.drop_table("sql_diagnosis_log")
