"""add_analysis_blueprints

Revision ID: 8c4d2e6f7a90
Revises: 7f1a2b3c4d5e
Create Date: 2026-06-05 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c4d2e6f7a90"
down_revision: Union[str, None] = "7f1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_blueprint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_keywords", sa.JSON(), nullable=True),
        sa.Column("trigger_examples", sa.JSON(), nullable=True),
        sa.Column("when_to_use", sa.Text(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("implementation_type", sa.String(length=30), nullable=True),
        sa.Column("call_template", sa.Text(), nullable=True),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("attribution_hints", sa.Text(), nullable=True),
        sa.Column("raw_sql", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("owner", sa.String(length=50), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("last_test_result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analysis_blueprint_id"), "analysis_blueprint", ["id"], unique=False)
    op.create_index(
        "ix_analysis_blueprint_dataset_status",
        "analysis_blueprint",
        ["dataset_id", "status"],
        unique=False,
    )

    op.create_table(
        "blueprint_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blueprint_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("published_by", sa.String(length=50), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["blueprint_id"], ["analysis_blueprint.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blueprint_version_id"), "blueprint_version", ["id"], unique=False)
    op.create_index(
        "ix_blueprint_version_blueprint_version",
        "blueprint_version",
        ["blueprint_id", "version"],
        unique=False,
    )

    op.create_table(
        "blueprint_usage_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blueprint_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("extracted_params", sa.JSON(), nullable=True),
        sa.Column("execution_success", sa.Boolean(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("user_feedback", sa.String(length=10), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["blueprint_id"], ["analysis_blueprint.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blueprint_usage_log_id"), "blueprint_usage_log", ["id"], unique=False)
    op.create_index(
        "ix_blueprint_usage_log_blueprint_created",
        "blueprint_usage_log",
        ["blueprint_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_blueprint_usage_log_blueprint_created", table_name="blueprint_usage_log")
    op.drop_index(op.f("ix_blueprint_usage_log_id"), table_name="blueprint_usage_log")
    op.drop_table("blueprint_usage_log")
    op.drop_index("ix_blueprint_version_blueprint_version", table_name="blueprint_version")
    op.drop_index(op.f("ix_blueprint_version_id"), table_name="blueprint_version")
    op.drop_table("blueprint_version")
    op.drop_index("ix_analysis_blueprint_dataset_status", table_name="analysis_blueprint")
    op.drop_index(op.f("ix_analysis_blueprint_id"), table_name="analysis_blueprint")
    op.drop_table("analysis_blueprint")
