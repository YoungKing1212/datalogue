"""add_step_trace_to_message

Revision ID: e47d3004182b
Revises: add_conversation_archived
Create Date: 2026-06-02 16:50:03.065758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e47d3004182b'
down_revision: Union[str, None] = 'add_conversation_archived'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('message', sa.Column('step_trace', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('message', 'step_trace')
