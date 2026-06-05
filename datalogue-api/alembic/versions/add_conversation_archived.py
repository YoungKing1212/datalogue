# ============================================================
# File Name   : add_conversation_archived.py
# Description:
#   为会话增加归档状态支持。
#
# Responsibilities:
#   - 新增会话归档字段以支持列表过滤。
#   - 在降级时移除归档状态字段。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add archived column to conversation

Revision ID: add_conversation_archived
Revises: 468af34bcb43
Create Date: 2026-06-02

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_conversation_archived'
down_revision = '468af34bcb43'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversation',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.create_index('ix_conversation_archived', 'conversation', ['archived'])


def downgrade() -> None:
    op.drop_index('ix_conversation_archived', table_name='conversation')
    op.drop_column('conversation', 'archived')
