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
            sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
            sa.Column("dataset_id", sa.Integer(), nullable=False, comment='所属数据集 ID'),
            sa.Column("question", sa.Text(), nullable=False, comment='测试问题文本'),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="unknown", comment='验证状态（pass/fail/unknown）'),
            sa.Column("route_type", sa.String(length=50), nullable=True, comment='问数路由类型'),
            sa.Column("entry_intent", sa.String(length=50), nullable=True, comment='识别出的入口意图'),
            sa.Column("entry_route", sa.String(length=50), nullable=True, comment='识别出的入口路由'),
            sa.Column("blueprint_id", sa.Integer(), nullable=True, comment='关联的分析蓝图 ID'),
            sa.Column("sql", sa.Text(), nullable=True, comment='生成的 SQL'),
            sa.Column("answer", sa.Text(), nullable=True, comment='回答内容'),
            sa.Column("error", sa.Text(), nullable=True, comment='执行错误信息'),
            sa.Column("report", sa.JSON(), nullable=True, comment='报告数据快照'),
            sa.Column("created_by", sa.String(length=50), nullable=True, comment='创建人'),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment='创建时间'),
            sa.Column("updated_at", sa.DateTime(), nullable=True, comment='更新时间'),
            sa.ForeignKeyConstraint(["blueprint_id"], ["analysis_blueprint.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment='语义验证用例表',
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
