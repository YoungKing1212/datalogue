"""add_column_review_conversion

Revision ID: 9b7c1d2e3f40
Revises: 8c4d2e6f7a90
Create Date: 2026-06-05 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b7c1d2e3f40"
down_revision: Union[str, None] = "8c4d2e6f7a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_column", sa.Column("ai_confidence", sa.Float(), nullable=True))
    op.add_column("source_column", sa.Column("ai_reason", sa.Text(), nullable=True))
    op.add_column("source_column", sa.Column("suggested_synonyms", sa.JSON(), nullable=True))
    op.add_column("source_column", sa.Column("suggested_enum_values", sa.JSON(), nullable=True))
    op.add_column(
        "source_column",
        sa.Column("review_status", sa.String(length=30), nullable=True, server_default="pending_review"),
    )
    op.add_column("source_column", sa.Column("converted_metric_id", sa.Integer(), nullable=True))
    op.add_column("source_column", sa.Column("converted_dimension_id", sa.Integer(), nullable=True))
    op.add_column("source_column", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_source_column_converted_metric",
        "source_column",
        "semantic_metric",
        ["converted_metric_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_source_column_converted_dimension",
        "source_column",
        "semantic_dimension",
        ["converted_dimension_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_source_column_review_status",
        "source_column",
        ["review_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_column_review_status", table_name="source_column")
    op.drop_constraint(
        "fk_source_column_converted_dimension",
        "source_column",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_source_column_converted_metric",
        "source_column",
        type_="foreignkey",
    )
    op.drop_column("source_column", "reviewed_at")
    op.drop_column("source_column", "converted_dimension_id")
    op.drop_column("source_column", "converted_metric_id")
    op.drop_column("source_column", "review_status")
    op.drop_column("source_column", "suggested_enum_values")
    op.drop_column("source_column", "suggested_synonyms")
    op.drop_column("source_column", "ai_reason")
    op.drop_column("source_column", "ai_confidence")
