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
    op.add_column('source_table', sa.Column('ai_description', sa.Text(), nullable=True))
    op.add_column('source_table', sa.Column('user_description', sa.Text(), nullable=True))
    op.add_column('source_table', sa.Column('effective_desc', sa.Text(), nullable=True))
    op.add_column('source_table', sa.Column('desc_source', sa.String(length=20), nullable=True, server_default='unknown'))
    op.add_column('source_table', sa.Column('annotated_at', sa.DateTime(), nullable=True))

    # source_column
    op.add_column('source_column', sa.Column('ai_description', sa.Text(), nullable=True))
    op.add_column('source_column', sa.Column('ai_semantic_role', sa.String(length=30), nullable=True))
    op.add_column('source_column', sa.Column('ai_suggested_agg', sa.String(length=20), nullable=True))
    op.add_column('source_column', sa.Column('user_description', sa.Text(), nullable=True))
    op.add_column('source_column', sa.Column('user_semantic_role', sa.String(length=30), nullable=True))
    op.add_column('source_column', sa.Column('effective_desc', sa.Text(), nullable=True))
    op.add_column('source_column', sa.Column('desc_source', sa.String(length=20), nullable=True, server_default='unknown'))
    op.add_column('source_column', sa.Column('annotated_at', sa.DateTime(), nullable=True))


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
