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
    op.add_column('datasource', sa.Column('status', sa.String(length=20), nullable=True, default='disconnected'))


def downgrade() -> None:
    op.drop_column('datasource', 'status')