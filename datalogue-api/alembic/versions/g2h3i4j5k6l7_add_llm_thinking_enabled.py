# ============================================================
# File Name   : g2h3i4j5k6l7_add_llm_thinking_enabled.py
# Description:
#   为 LLM 模型配置新增 Think 模式开关。
#
# Responsibilities:
#   - 在 llm_model_config 表中保存是否允许模型输出思考过程。
#   - 默认关闭 Think 模式，避免回答和 Langfuse trace 泄露推理草稿。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

"""add_llm_thinking_enabled

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-11 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("llm_model_config", "thinking_enabled"):
        op.add_column(
            "llm_model_config",
            sa.Column("thinking_enabled", sa.Boolean(), server_default=sa.false(), nullable=False, comment='是否开启 Think 模式（输出推理过程）'),
        )


def downgrade() -> None:
    if _has_column("llm_model_config", "thinking_enabled"):
        op.drop_column("llm_model_config", "thinking_enabled")
