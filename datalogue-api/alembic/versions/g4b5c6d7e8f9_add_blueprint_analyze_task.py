# ============================================================
# File Name   : g4b5c6d7e8f9_add_blueprint_analyze_task.py
# Description:
#   持久化分析蓝图 AI 任务状态。
#
# Responsibilities:
#   - 让任务状态可被任意 API worker 查询。
#   - 通过数据集外键在数据集删除时清理任务记录。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

"""add blueprint analyze task

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "g4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    table_exists = inspector.has_table("blueprint_analyze_task")
    existing_indexes = (
        {index.get("name") for index in inspector.get_indexes("blueprint_analyze_task")}
        if table_exists
        else set()
    )

    if not table_exists:
        op.create_table(
            "blueprint_analyze_task",
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("task_id"),
        )
    if "ix_blueprint_analyze_task_dataset_id" not in existing_indexes:
        op.create_index(
            "ix_blueprint_analyze_task_dataset_id",
            "blueprint_analyze_task",
            ["dataset_id"],
        )
    if "ix_blueprint_analyze_task_status" not in existing_indexes:
        op.create_index(
            "ix_blueprint_analyze_task_status", "blueprint_analyze_task", ["status"]
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("blueprint_analyze_task"):
        return
    indexes = {
        index.get("name") for index in inspector.get_indexes("blueprint_analyze_task")
    }
    if "ix_blueprint_analyze_task_status" in indexes:
        op.drop_index(
            "ix_blueprint_analyze_task_status", table_name="blueprint_analyze_task"
        )
    if "ix_blueprint_analyze_task_dataset_id" in indexes:
        op.drop_index(
            "ix_blueprint_analyze_task_dataset_id",
            table_name="blueprint_analyze_task",
        )
    op.drop_table("blueprint_analyze_task")
