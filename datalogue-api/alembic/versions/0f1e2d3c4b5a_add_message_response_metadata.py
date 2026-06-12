# ============================================================
# File Name   : 0f1e2d3c4b5a_add_message_response_metadata.py
# Description:
#   为消息增加回答元数据存储字段。
#
# Responsibilities:
#   - 保存问数回答解释包等结构化前端元数据。
#   - 降级时移除消息回答元数据字段。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""add_message_response_metadata

Revision ID: 0f1e2d3c4b5a
Revises: f6a7b8c9d0e1
Create Date: 2026-06-09 21:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "0f1e2d3c4b5a"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("message")}
    if "response_metadata" not in columns:
        op.add_column("message", sa.Column("response_metadata", sa.JSON(), nullable=True, comment='回答元数据（解释包、可视化提示等）'))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("message")}
    if "response_metadata" in columns:
        op.drop_column("message", "response_metadata")
