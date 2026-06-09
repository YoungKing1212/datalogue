# ============================================================
# File Name   : c9d1e2f3a4b5_add_blueprint_creation_source.py
# Description:
#   为分析蓝图补充创建来源和 AI 生成标记。
#
# Responsibilities:
#   - 增加 creation_source、ai_generated、ai_generation_type 字段。
#   - 回滚时移除对应来源标记字段。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""add_blueprint_creation_source

Revision ID: c9d1e2f3a4b5
Revises: b2c4d6e8f901
Create Date: 2026-06-09 11:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d1e2f3a4b5"
down_revision: Union[str, None] = "b2c4d6e8f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_blueprint",
        sa.Column("creation_source", sa.String(length=30), server_default="manual", nullable=False),
    )
    op.add_column(
        "analysis_blueprint",
        sa.Column("ai_generated", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "analysis_blueprint",
        sa.Column("ai_generation_type", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_blueprint", "ai_generation_type")
    op.drop_column("analysis_blueprint", "ai_generated")
    op.drop_column("analysis_blueprint", "creation_source")
