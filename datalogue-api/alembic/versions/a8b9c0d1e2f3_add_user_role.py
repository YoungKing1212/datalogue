# ============================================================
# File Name   : a8b9c0d1e2f3_add_user_role.py
# Description:
#   为平台用户补充角色字段。
#
# Responsibilities:
#   - 新增 app_user.role（admin/user）列并补中文字段注释。
#   - 为历史超级管理员记录回填 admin 角色。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

"""add user role

Revision ID: a8b9c0d1e2f3
Revises: z6a7b8c9d0e1
Create Date: 2026-07-09 16:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
            server_default="user",
            comment="用户角色。字典：admin=管理员；user=普通用户",
        ),
    )

    op.execute("UPDATE app_user SET role = 'admin' WHERE is_superuser = true")


def downgrade() -> None:
    op.drop_column("app_user", "role")
