# ============================================================
# File Name   : 468af34bcb43_add_annotation_columns.py
# Description:
#   为源表和源字段增加 AI/人工标注字段。
#
# Responsibilities:
#   - 扩展源表与源字段的业务描述信息。
#   - 支持标注字段的迁移回滚。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add_annotation_columns

Revision ID: 468af34bcb43
Revises: 2bc2a6cac055
Create Date: 2026-06-01 19:41:13.439721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '468af34bcb43'
down_revision: Union[str, None] = '2bc2a6cac055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # source_table
    op.add_column('source_table', sa.Column('ai_description', sa.Text(), nullable=True, comment='AI 生成的表描述'))
    op.add_column('source_table', sa.Column('user_description', sa.Text(), nullable=True, comment='人工填写的表描述'))
    op.add_column('source_table', sa.Column('effective_desc', sa.Text(), nullable=True, comment='最终生效的表描述（人工优先）'))
    op.add_column('source_table', sa.Column('desc_source', sa.String(length=20), nullable=True, server_default='unknown', comment='描述来源（ai/user/unknown）'))
    op.add_column('source_table', sa.Column('annotated_at', sa.DateTime(), nullable=True, comment='最近标注时间'))

    # source_column
    op.add_column('source_column', sa.Column('ai_description', sa.Text(), nullable=True, comment='AI 生成的字段描述'))
    op.add_column('source_column', sa.Column('ai_semantic_role', sa.String(length=30), nullable=True, comment='AI 建议的语义角色（metric/dimension/time等）'))
    op.add_column('source_column', sa.Column('ai_suggested_agg', sa.String(length=20), nullable=True, comment='AI 建议的聚合方式（sum/count/avg等）'))
    op.add_column('source_column', sa.Column('user_description', sa.Text(), nullable=True, comment='人工填写的字段描述'))
    op.add_column('source_column', sa.Column('user_semantic_role', sa.String(length=30), nullable=True, comment='人工指定的语义角色'))
    op.add_column('source_column', sa.Column('effective_desc', sa.Text(), nullable=True, comment='最终生效的字段描述（人工优先）'))
    op.add_column('source_column', sa.Column('desc_source', sa.String(length=20), nullable=True, server_default='unknown', comment='描述来源（ai/user/unknown）'))
    op.add_column('source_column', sa.Column('annotated_at', sa.DateTime(), nullable=True, comment='最近标注时间'))


def downgrade() -> None:
    # source_column
    op.drop_column('source_column', 'annotated_at')
    op.drop_column('source_column', 'desc_source')
    op.drop_column('source_column', 'effective_desc')
    op.drop_column('source_column', 'user_semantic_role')
    op.drop_column('source_column', 'user_description')
    op.drop_column('source_column', 'ai_suggested_agg')
    op.drop_column('source_column', 'ai_semantic_role')
    op.drop_column('source_column', 'ai_description')

    # source_table
    op.drop_column('source_table', 'annotated_at')
    op.drop_column('source_table', 'desc_source')
    op.drop_column('source_table', 'effective_desc')
    op.drop_column('source_table', 'user_description')
    op.drop_column('source_table', 'ai_description')
