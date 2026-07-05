# ============================================================
# File Name   : v2w3x4y5z6a7_drop_llm_role_binding.py
# Description:
#   删除旧的 LLM 模型角色映射表，保留模型配置表。
#
# Responsibilities:
#   - 在升级时删除 llm_role_binding 表。
#   - 在降级时按旧结构恢复 llm_role_binding 表。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

"""drop llm role binding

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-07-05 13:58:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "v2w3x4y5z6a7"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("llm_role_binding"):
        op.drop_table("llm_role_binding")


def downgrade() -> None:
    if _has_table("llm_role_binding"):
        return
    op.create_table(
        "llm_role_binding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("model_config_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_config_id"], ["llm_model_config.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role"),
        comment="旧版 LLM 任务角色到模型配置的映射表",
    )
    op.create_index(op.f("ix_llm_role_binding_id"), "llm_role_binding", ["id"], unique=False)
    op.create_index(op.f("ix_llm_role_binding_role"), "llm_role_binding", ["role"], unique=False)
