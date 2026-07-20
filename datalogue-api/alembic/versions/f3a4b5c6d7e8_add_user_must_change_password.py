# ============================================================
# File Name   : f3a4b5c6d7e8_add_user_must_change_password.py
# Description:
#   为平台用户增加强制修改密码状态。
#
# Responsibilities:
#   - 支持管理员重置随机临时密码后的首次登录改密约束。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

"""add user must change password

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("app_user", "must_change_password")
