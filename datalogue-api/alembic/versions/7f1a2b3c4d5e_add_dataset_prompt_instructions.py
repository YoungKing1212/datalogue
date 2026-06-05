# ============================================================
# File Name   : 7f1a2b3c4d5e_add_dataset_prompt_instructions.py
# Description:
#   为数据集增加自定义提示词约束字段。
#
# Responsibilities:
#   - 持久化数据集级 LLM 指令文本。
#   - 在降级时移除提示词约束存储。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add_dataset_prompt_instructions

Revision ID: 7f1a2b3c4d5e
Revises: e47d3004182b
Create Date: 2026-06-03 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f1a2b3c4d5e'
down_revision: Union[str, None] = 'e47d3004182b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 数据集级 LLM 约束（自由文本），问数时由 build_schema_prompt
    # 拼到 schema_context，所有语义相关 LLM 节点可见。
    op.add_column(
        'semantic_dataset',
        sa.Column('prompt_instructions', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('semantic_dataset', 'prompt_instructions')
