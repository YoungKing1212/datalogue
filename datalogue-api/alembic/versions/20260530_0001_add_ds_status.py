# ============================================================
# File Name   : 20260530_0001_add_ds_status.py
# Description:
#   为语义数据集增加生命周期状态字段。
#
# Responsibilities:
#   - 新增带默认值的数据集状态列。
#   - 在降级时移除状态列。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add status column to datasource

Revision ID: add_ds_status
Revises: 20260528_0001_init_models
Create Date: 2026-05-30

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_ds_status'
down_revision = '20260528_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('datasource', sa.Column('status', sa.String(length=20), nullable=True, default='disconnected', comment='连接状态（connected/disconnected）'))


def downgrade() -> None:
    op.drop_column('datasource', 'status')