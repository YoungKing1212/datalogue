# ============================================================
# File Name   : i4j5k6l7m8n9_add_dataset_subagent_manifest.py
# Description:
#   新增数据集 SubAgent Manifest 版本表。
#
# Responsibilities:
#   - 保存 Manifest 自动字段、人工字段和质量信息。
#   - 支持 current 版本、历史版本和 schema 需复核状态。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

"""add_dataset_subagent_manifest

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-06-12 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _manifest_json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("dataset_subagent_manifest"):
        op.create_table(
            "dataset_subagent_manifest",
            sa.Column("dataset_id", sa.Integer(), nullable=False, comment="语义数据集 ID"),
            sa.Column("manifest_version", sa.String(length=40), nullable=False, comment="Manifest 版本号"),
            sa.Column("bound_schema_version", sa.String(length=64), nullable=False, comment="绑定的 schema hash"),
            sa.Column("manifest_json", _manifest_json_type(), nullable=False, comment="Manifest 完整内容"),
            sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False, comment="是否当前有效版本"),
            sa.Column("review_status", sa.String(length=30), server_default="draft", nullable=False, comment="复核状态"),
            sa.Column("created_by", sa.String(length=50), nullable=True, comment="创建人"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间"),
            sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("dataset_id", "manifest_version"),
            comment="数据集 SubAgent Manifest 版本表",
        )

    indexes = {index["name"] for index in inspector.get_indexes("dataset_subagent_manifest")}
    if "ix_dataset_subagent_manifest_is_current" not in indexes:
        op.create_index(
            "ix_dataset_subagent_manifest_is_current",
            "dataset_subagent_manifest",
            ["is_current"],
        )
    if "ix_dataset_subagent_manifest_review_status" not in indexes:
        op.create_index(
            "ix_dataset_subagent_manifest_review_status",
            "dataset_subagent_manifest",
            ["review_status"],
        )
    if "ix_manifest_current" not in indexes:
        dialect = op.get_bind().dialect.name
        if dialect == "postgresql":
            op.create_index(
                "ix_manifest_current",
                "dataset_subagent_manifest",
                ["dataset_id"],
                unique=True,
                postgresql_where=sa.text("is_current"),
            )
        else:
            op.create_index(
                "ix_manifest_current",
                "dataset_subagent_manifest",
                ["dataset_id", "is_current"],
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("dataset_subagent_manifest"):
        return
    indexes = [idx.get("name") for idx in inspector.get_indexes("dataset_subagent_manifest")]
    for index_name in indexes:
        if index_name:
            op.drop_index(index_name, table_name="dataset_subagent_manifest")
    op.drop_table("dataset_subagent_manifest")
