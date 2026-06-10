# ============================================================
# File Name   : e3f4a5b6c7d8_add_llm_model_config.py
# Description:
#   新增 LLM 模型配置和角色绑定表。
#
# Responsibilities:
#   - 创建 llm_model_config 表用于保存前端配置的模型连接。
#   - 创建 llm_role_binding 表用于保存问数任务角色与模型绑定。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

"""add_llm_model_config

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-10 13:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "llm_model_config" not in tables:
        op.create_table(
            "llm_model_config",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=50), server_default="litellm", nullable=False),
            sa.Column("base_url", sa.String(length=500), nullable=False),
            sa.Column("model", sa.String(length=200), nullable=False),
            sa.Column("api_key_enc", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("request_timeout_seconds", sa.Float(), server_default="60", nullable=False),
            sa.Column("last_test_result", sa.JSON(), nullable=True),
            sa.Column("last_error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_llm_model_config_id"), "llm_model_config", ["id"], unique=False)

    if "llm_role_binding" not in tables:
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
        )
        op.create_index(op.f("ix_llm_role_binding_id"), "llm_role_binding", ["id"], unique=False)
        op.create_index(op.f("ix_llm_role_binding_role"), "llm_role_binding", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_role_binding_role"), table_name="llm_role_binding")
    op.drop_index(op.f("ix_llm_role_binding_id"), table_name="llm_role_binding")
    op.drop_table("llm_role_binding")
    op.drop_index(op.f("ix_llm_model_config_id"), table_name="llm_model_config")
    op.drop_table("llm_model_config")
