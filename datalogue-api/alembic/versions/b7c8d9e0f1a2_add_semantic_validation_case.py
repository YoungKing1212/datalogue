# ============================================================
# File Name   : b7c8d9e0f1a2_add_semantic_validation_case.py
# Description:
#   新增语义验证用例表。
#
# Responsibilities:
#   - 保存数据集语义验证问题、路由结果、SQL、失败原因和报告快照。
#   - 支持后续回放评测业务术语、分析蓝图和普通问数路径。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""add_semantic_validation_case

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 22:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    table_exists = inspector.has_table("semantic_validation_case")
    existing_indexes = (
        {idx.get("name") for idx in inspector.get_indexes("semantic_validation_case")}
        if table_exists
        else set()
    )

    if not table_exists:
        op.create_table(
            "semantic_validation_case",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("route_type", sa.String(length=50), nullable=True),
            sa.Column("entry_intent", sa.String(length=50), nullable=True),
            sa.Column("entry_route", sa.String(length=50), nullable=True),
            sa.Column("blueprint_id", sa.Integer(), nullable=True),
            sa.Column("sql", sa.Text(), nullable=True),
            sa.Column("answer", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("report", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["blueprint_id"], ["analysis_blueprint.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "ix_semantic_validation_case_id" not in existing_indexes:
        op.create_index("ix_semantic_validation_case_id", "semantic_validation_case", ["id"])
    if "ix_semantic_validation_case_dataset_id" not in existing_indexes:
        op.create_index(
            "ix_semantic_validation_case_dataset_id",
            "semantic_validation_case",
            ["dataset_id"],
        )
    if "ix_semantic_validation_case_blueprint_id" not in existing_indexes:
        op.create_index(
            "ix_semantic_validation_case_blueprint_id",
            "semantic_validation_case",
            ["blueprint_id"],
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("semantic_validation_case"):
        return
    indexes = {idx.get("name") for idx in inspector.get_indexes("semantic_validation_case")}
    if "ix_semantic_validation_case_blueprint_id" in indexes:
        op.drop_index("ix_semantic_validation_case_blueprint_id", table_name="semantic_validation_case")
    if "ix_semantic_validation_case_dataset_id" in indexes:
        op.drop_index("ix_semantic_validation_case_dataset_id", table_name="semantic_validation_case")
    if "ix_semantic_validation_case_id" in indexes:
        op.drop_index("ix_semantic_validation_case_id", table_name="semantic_validation_case")
    op.drop_table("semantic_validation_case")
