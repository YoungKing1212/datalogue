# ============================================================
# File Name   : x4y5z6a7b8c9_drop_llm_model_config.py
# Description:
#   删除 Datalogue 本地 LLM 模型配置表。
#
# Responsibilities:
#   - 让模型凭证和可选模型完全由 AgentScope Service credential/model 资源管理。
#   - 升级时移除 llm_model_config，防止运行时继续读取本地模型配置层。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

"""drop llm model config

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-07-05 22:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "x4y5z6a7b8c9"
down_revision = "w3x4y5z6a7b8"
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
        if _has_index("llm_model_config", "ix_llm_model_config_id"):
            op.drop_index(op.f("ix_llm_model_config_id"), table_name="llm_model_config")
        op.drop_table("llm_model_config")


def downgrade() -> None:
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
        comment="历史 LLM 模型配置表，仅用于降级恢复结构，不再保存密钥",
    )
    op.create_index(op.f("ix_llm_model_config_id"), "llm_model_config", ["id"], unique=False)
