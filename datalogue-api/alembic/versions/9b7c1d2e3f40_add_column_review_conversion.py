# ============================================================
# File Name   : 9b7c1d2e3f40_add_column_review_conversion.py
# Description:
#   增加字段审核和资产转化追踪字段。
#
# Responsibilities:
#   - 记录 AI 置信度、审核状态和转化目标。
#   - 创建已转化资产的索引和外键约束。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add_column_review_conversion

Revision ID: 9b7c1d2e3f40
Revises: 8c4d2e6f7a90
Create Date: 2026-06-05 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b7c1d2e3f40"
down_revision: Union[str, None] = "8c4d2e6f7a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_column", sa.Column("ai_confidence", sa.Float(), nullable=True, comment='AI 分析置信度'))
    op.add_column("source_column", sa.Column("ai_reason", sa.Text(), nullable=True, comment='AI 分析理由'))
    op.add_column("source_column", sa.Column("suggested_synonyms", sa.JSON(), nullable=True, comment='AI 建议的同义词列表'))
    op.add_column("source_column", sa.Column("suggested_enum_values", sa.JSON(), nullable=True, comment='AI 建议的枚举值列表'))
    op.add_column(
        "source_column",
        sa.Column("review_status", sa.String(length=30), nullable=True, server_default="pending_review", comment='审核状态（pending_review/approved/rejected等）'),
    )
    op.add_column("source_column", sa.Column("converted_metric_id", sa.Integer(), nullable=True, comment='已转化的语义指标 ID'))
    op.add_column("source_column", sa.Column("converted_dimension_id", sa.Integer(), nullable=True, comment='已转化的语义维度 ID'))
    op.add_column("source_column", sa.Column("reviewed_at", sa.DateTime(), nullable=True, comment='审核完成时间'))
    op.create_foreign_key(
        "fk_source_column_converted_metric",
        "source_column",
        "semantic_metric",
        ["converted_metric_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_source_column_converted_dimension",
        "source_column",
        "semantic_dimension",
        ["converted_dimension_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_source_column_review_status",
        "source_column",
        ["review_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_column_review_status", table_name="source_column")
    op.drop_constraint(
        "fk_source_column_converted_dimension",
        "source_column",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_source_column_converted_metric",
        "source_column",
        type_="foreignkey",
    )
    op.drop_column("source_column", "reviewed_at")
    op.drop_column("source_column", "converted_dimension_id")
    op.drop_column("source_column", "converted_metric_id")
    op.drop_column("source_column", "review_status")
    op.drop_column("source_column", "suggested_enum_values")
    op.drop_column("source_column", "suggested_synonyms")
    op.drop_column("source_column", "ai_reason")
    op.drop_column("source_column", "ai_confidence")
