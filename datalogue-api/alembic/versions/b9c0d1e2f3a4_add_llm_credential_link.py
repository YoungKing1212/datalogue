# ============================================================
# File Name   : b9c0d1e2f3a4_add_llm_credential_link.py
# Description:
#   为数据库 LLM 配置保存 AgentScope credential 的真实关联。
#
# Responsibilities:
#   - 新增真实 credential ID 与类型，消除按本地主键推导凭据的旧路径。
#   - 允许升级期旧记录暂未绑定，由设置页保存时回填。
#
# Author      : yangkai
# Created On  : 2026-07-14
# ============================================================

"""add llm credential link

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-14 16:58:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def _has_column(column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns("llm_model_config")}


def _has_index(index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes("llm_model_config"))


def upgrade() -> None:
    if not _has_column("credential_id"):
        op.add_column(
            "llm_model_config",
            sa.Column("credential_id", sa.String(length=200), nullable=True, comment="AgentScope credential 真实 ID"),
        )
    if not _has_column("credential_type"):
        op.add_column(
            "llm_model_config",
            sa.Column("credential_type", sa.String(length=100), nullable=True, comment="AgentScope credential 类型"),
        )
    if not _has_index("uq_llm_model_config_credential_id"):
        op.create_index(
            "uq_llm_model_config_credential_id",
            "llm_model_config",
            ["credential_id"],
            unique=True,
        )


def downgrade() -> None:
    if _has_index("uq_llm_model_config_credential_id"):
        op.drop_index("uq_llm_model_config_credential_id", table_name="llm_model_config")
    if _has_column("credential_type"):
        op.drop_column("llm_model_config", "credential_type")
    if _has_column("credential_id"):
        op.drop_column("llm_model_config", "credential_id")
