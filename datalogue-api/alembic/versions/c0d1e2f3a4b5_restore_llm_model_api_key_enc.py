# ============================================================
# File Name   : c0d1e2f3a4b5_restore_llm_model_api_key_enc.py
# Description:
#   恢复 LLM 模型配置的 AES-GCM 密钥密文字段。
#
# Responsibilities:
#   - 让 llm_model_config 成为模型 API Key 的加密持久化真相源。
#   - 支持 AgentScope credential 丢失后的安全自动补建。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

"""restore encrypted LLM model API key storage

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-07-15 12:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def _has_column(column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns("llm_model_config")}


def upgrade() -> None:
    if not _has_column("api_key_enc"):
        op.add_column(
            "llm_model_config",
            sa.Column(
                "api_key_enc", sa.Text(), nullable=True, comment="AES-GCM 加密的模型 API Key"
            ),
        )


def downgrade() -> None:
    if _has_column("api_key_enc"):
        op.drop_column("llm_model_config", "api_key_enc")
