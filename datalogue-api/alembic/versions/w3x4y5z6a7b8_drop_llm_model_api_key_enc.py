# ============================================================
# File Name   : w3x4y5z6a7b8_drop_llm_model_api_key_enc.py
# Description:
#   删除 Datalogue 本地 LLM 模型配置表中的历史密钥列。
#
# Responsibilities:
#   - 在升级前确认历史密钥已迁移到 AgentScope credential。
#   - 删除 llm_model_config.api_key_enc，避免本地数据库继续保存 LLM credential。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

"""drop llm model api_key_enc

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-07-05 14:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "w3x4y5z6a7b8"
down_revision = "v2w3x4y5z6a7"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("llm_model_config", "api_key_enc"):
        return
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text("SELECT COUNT(*) FROM llm_model_config WHERE api_key_enc IS NOT NULL AND api_key_enc <> ''")
    ).scalar_one()
    if remaining:
        raise RuntimeError(
            "llm_model_config.api_key_enc still contains values; "
            "call /api/llm/models on the current app first so credentials migrate to AgentScope."
        )
    with op.batch_alter_table("llm_model_config") as batch_op:
        batch_op.drop_column("api_key_enc")


def downgrade() -> None:
    if _has_column("llm_model_config", "api_key_enc"):
        return
    with op.batch_alter_table("llm_model_config") as batch_op:
        batch_op.add_column(sa.Column("api_key_enc", sa.Text(), nullable=True, comment="旧版本地加密 API 密钥"))
