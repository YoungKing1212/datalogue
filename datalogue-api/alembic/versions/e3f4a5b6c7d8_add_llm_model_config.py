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
            sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
            sa.Column("name", sa.String(length=100), nullable=False, comment='配置名称'),
            sa.Column("provider", sa.String(length=50), server_default="litellm", nullable=False, comment='供应商（litellm/openai等）'),
            sa.Column("base_url", sa.String(length=500), nullable=False, comment='API 基础地址'),
            sa.Column("model", sa.String(length=200), nullable=False, comment='模型标识符'),
            sa.Column("api_key_enc", sa.Text(), nullable=True, comment='加密存储的 API 密钥'),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False, comment='状态（active/inactive）'),
            sa.Column("description", sa.Text(), nullable=True, comment='配置描述'),
            sa.Column("request_timeout_seconds", sa.Float(), server_default="60", nullable=False, comment='请求超时秒数'),
            sa.Column("last_test_result", sa.JSON(), nullable=True, comment='最近连通性测试结果'),
            sa.Column("last_error_message", sa.Text(), nullable=True, comment='最近错误信息'),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment='创建时间'),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment='更新时间'),
            sa.PrimaryKeyConstraint("id"),
            comment='LLM 模型配置表',
        )
        op.create_index(op.f("ix_llm_model_config_id"), "llm_model_config", ["id"], unique=False)

    if "llm_role_binding" not in tables:
        op.create_table(
            "llm_role_binding",
            sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
            sa.Column("role", sa.String(length=50), nullable=False, comment='任务角色名（sql_generator/report_generator等）'),
            sa.Column("model_config_id", sa.Integer(), nullable=True, comment='绑定的模型配置 ID'),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment='创建时间'),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment='更新时间'),
            sa.ForeignKeyConstraint(["model_config_id"], ["llm_model_config.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("role"),
            comment='LLM 角色绑定表',
        )
        op.create_index(op.f("ix_llm_role_binding_id"), "llm_role_binding", ["id"], unique=False)
        op.create_index(op.f("ix_llm_role_binding_role"), "llm_role_binding", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_role_binding_role"), table_name="llm_role_binding")
    op.drop_index(op.f("ix_llm_role_binding_id"), table_name="llm_role_binding")
    op.drop_table("llm_role_binding")
    op.drop_index(op.f("ix_llm_model_config_id"), table_name="llm_model_config")
    op.drop_table("llm_model_config")
