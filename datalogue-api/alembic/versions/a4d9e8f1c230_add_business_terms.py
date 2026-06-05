# ============================================================
# File Name   : a4d9e8f1c230_add_business_terms.py
# Description:
#   增加业务术语治理相关表。
#
# Responsibilities:
#   - 创建业务术语、资产关联和变更日志表。
#   - 支持术语治理存储的迁移回滚。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add_business_terms

Revision ID: a4d9e8f1c230
Revises: 9b7c1d2e3f40
Create Date: 2026-06-05 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a4d9e8f1c230"
down_revision: Union[str, None] = "9b7c1d2e3f40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    def has_table(name: str) -> bool:
        return inspector.has_table(name)

    def has_index(table_name: str, index_name: str) -> bool:
        if not has_table(table_name):
            return False
        return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))

    if not has_table("business_term"):
        op.create_table(
        "business_term",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("term_type", sa.String(length=30), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("forbidden_aliases", sa.JSON(), nullable=True),
        sa.Column("examples", sa.JSON(), nullable=True),
        sa.Column("owner", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "name", name="uix_business_term_dataset_name"),
        )
    if not has_index("business_term", "ix_business_term_id"):
        op.create_index(op.f("ix_business_term_id"), "business_term", ["id"], unique=False)
    if not has_index("business_term", "ix_business_term_dataset_status"):
        op.create_index(
        "ix_business_term_dataset_status",
        "business_term",
        ["dataset_id", "status"],
        unique=False,
        )

    if not has_table("business_term_asset_link"):
        op.create_table(
        "business_term_asset_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(length=30), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("asset_name", sa.String(length=150), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["term_id"], ["business_term.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "term_id", "asset_type", "asset_id", name="uix_business_term_asset_link"
        ),
        )
    if not has_index("business_term_asset_link", "ix_business_term_asset_link_id"):
        op.create_index(
        op.f("ix_business_term_asset_link_id"),
        "business_term_asset_link",
        ["id"],
        unique=False,
        )

    if not has_table("business_term_relation"):
        op.create_table(
        "business_term_relation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("source_term_id", sa.Integer(), nullable=False),
        sa.Column("target_term_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_term_id"], ["business_term.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_term_id"], ["business_term.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        )
    if not has_index("business_term_relation", "ix_business_term_relation_id"):
        op.create_index(
        op.f("ix_business_term_relation_id"),
        "business_term_relation",
        ["id"],
        unique=False,
        )

    if not has_table("business_term_change_log"):
        op.create_table(
        "business_term_change_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["term_id"], ["business_term.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        )
    if not has_index("business_term_change_log", "ix_business_term_change_log_id"):
        op.create_index(
        op.f("ix_business_term_change_log_id"),
        "business_term_change_log",
        ["id"],
        unique=False,
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_business_term_change_log_id"), table_name="business_term_change_log")
    op.drop_table("business_term_change_log")
    op.drop_index(op.f("ix_business_term_relation_id"), table_name="business_term_relation")
    op.drop_table("business_term_relation")
    op.drop_index(op.f("ix_business_term_asset_link_id"), table_name="business_term_asset_link")
    op.drop_table("business_term_asset_link")
    op.drop_index("ix_business_term_dataset_status", table_name="business_term")
    op.drop_index(op.f("ix_business_term_id"), table_name="business_term")
    op.drop_table("business_term")
