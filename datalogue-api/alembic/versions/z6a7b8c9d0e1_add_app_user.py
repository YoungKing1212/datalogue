# ============================================================
# File Name   : z6a7b8c9d0e1_add_app_user.py
# Description:
#   新增平台用户认证表。
#
# Responsibilities:
#   - 创建 app_user 表及唯一索引。
#   - 提供可回滚的降级逻辑。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

"""add app user

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-07-09 00:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("username", sa.String(length=64), nullable=False, comment="登录用户名"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="用户邮箱"),
        sa.Column("hashed_password", sa.String(length=255), nullable=False, comment="密码哈希"),
        sa.Column("full_name", sa.String(length=100), nullable=True, comment="用户姓名"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
            comment="账号状态。字典：true=可用；false=禁用",
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="是否管理员。字典：true=管理员；false=普通用户",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="平台用户表",
    )
    op.create_index(op.f("ix_app_user_id"), "app_user", ["id"], unique=False)
    op.create_index(op.f("ix_app_user_username"), "app_user", ["username"], unique=True)
    op.create_index(op.f("ix_app_user_email"), "app_user", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_user_email"), table_name="app_user")
    op.drop_index(op.f("ix_app_user_username"), table_name="app_user")
    op.drop_index(op.f("ix_app_user_id"), table_name="app_user")
    op.drop_table("app_user")
