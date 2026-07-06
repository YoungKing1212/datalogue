# ============================================================
# File Name   : y5z6a7b8c9d0_restore_llm_model_config.py
# Description:
#   恢复 Datalogue 本地 LLM 模型配置表。
#
# Responsibilities:
#   - 重新创建 llm_model_config，作为设置页和运行时模型选择的配置真相源。
#   - 保持密钥不落本地表，仍由 AgentScope credential 承载。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

"""restore llm model config

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-07-06 13:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if _has_table("llm_model_config"):
        return
    op.create_table(
        "llm_model_config",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="配置名称"),
        sa.Column("provider", sa.String(length=50), server_default="openai-compatible", nullable=False, comment="供应商"),
        sa.Column("base_url", sa.String(length=500), nullable=False, comment="API 基础地址"),
        sa.Column("model", sa.String(length=200), nullable=False, comment="模型标识符"),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False, comment="状态"),
        sa.Column("description", sa.Text(), nullable=True, comment="配置描述"),
        sa.Column("request_timeout_seconds", sa.Float(), server_default="60", nullable=False, comment="请求超时秒数"),
        sa.Column("thinking_enabled", sa.Boolean(), server_default=sa.false(), nullable=False, comment="是否开启 Think 模式"),
        sa.Column("last_test_result", sa.JSON(), nullable=True, comment="最近连通性测试结果"),
        sa.Column("last_error_message", sa.Text(), nullable=True, comment="最近错误信息"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="LLM 模型配置表；密钥由 AgentScope credential 承载",
    )
    op.create_index(op.f("ix_llm_model_config_id"), "llm_model_config", ["id"], unique=False)


def downgrade() -> None:
    if not _has_table("llm_model_config"):
        return
    if _has_index("llm_model_config", "ix_llm_model_config_id"):
        op.drop_index(op.f("ix_llm_model_config_id"), table_name="llm_model_config")
    op.drop_table("llm_model_config")
