# ============================================================
# File Name   : d4e5f6a7b8c9_add_blueprint_usage_log_details.py
# Description:
#   为分析蓝图使用日志补充执行行数和结构化诊断。
#
# Responsibilities:
#   - 增加 row_count 字段记录本次返回行数。
#   - 增加 diagnosis 字段记录结构化失败诊断。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""add_blueprint_usage_log_details

Revision ID: d4e5f6a7b8c9
Revises: c9d1e2f3a4b5
Create Date: 2026-06-09 17:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c9d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("blueprint_usage_log", sa.Column("row_count", sa.Integer(), nullable=True))
    op.add_column("blueprint_usage_log", sa.Column("diagnosis", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("blueprint_usage_log", "diagnosis")
    op.drop_column("blueprint_usage_log", "row_count")
