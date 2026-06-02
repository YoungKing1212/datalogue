"""add_source_tables_and_extend_metric_dim

Revision ID: ab6832e0a3dd
Revises: add_ds_status
Create Date: 2026-06-01 13:02:05.447309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab6832e0a3dd'
down_revision: Union[str, None] = 'add_ds_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # source_table and source_column already exist in the database
    # (created manually in a previous session), so we only add columns here.
    op.add_column('semantic_dimension', sa.Column('table_name', sa.String(length=100), nullable=True))
    op.add_column('semantic_dimension', sa.Column('join_to', sa.String(length=100), nullable=True))
    op.add_column('semantic_dimension', sa.Column('join_key', sa.String(length=100), nullable=True))
    op.add_column('semantic_dimension', sa.Column('hierarchy', sa.JSON(), nullable=True))
    op.add_column('semantic_metric', sa.Column('table_name', sa.String(length=100), nullable=True))
    op.add_column('semantic_metric', sa.Column('time_field', sa.String(length=100), nullable=True))
    op.add_column('semantic_metric', sa.Column('granularity', sa.String(length=20), nullable=True))
    op.add_column('semantic_metric', sa.Column('format_str', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('semantic_metric', 'format_str')
    op.drop_column('semantic_metric', 'granularity')
    op.drop_column('semantic_metric', 'time_field')
    op.drop_column('semantic_metric', 'table_name')
    op.drop_column('semantic_dimension', 'hierarchy')
    op.drop_column('semantic_dimension', 'join_key')
    op.drop_column('semantic_dimension', 'join_to')
    op.drop_column('semantic_dimension', 'table_name')
