# ============================================================
# File Name   : b2c4d6e8f901_add_dataset_query_constraints.py
# Description:
#   为数据集增加 SQL 生成查询约束字段。
#
# Responsibilities:
#   - 持久化默认时间范围、默认 LIMIT 和最大 LIMIT 配置。
#   - 支持迁移回滚时移除查询约束字段。
#
# Author      : yangkai
# Created On  : 2026-06-08
# ============================================================

"""add_dataset_query_constraints

Revision ID: b2c4d6e8f901
Revises: a4d9e8f1c230
Create Date: 2026-06-08 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "b2c4d6e8f901"
down_revision: Union[str, None] = "a4d9e8f1c230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {col["name"] for col in inspector.get_columns("semantic_dataset")}
    if "query_constraints" not in columns:
        op.add_column("semantic_dataset", sa.Column("query_constraints", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {col["name"] for col in inspector.get_columns("semantic_dataset")}
    if "query_constraints" in columns:
        op.drop_column("semantic_dataset", "query_constraints")
