# ============================================================
# File Name   : d1e2f3a4b5c6_drop_langgraph_checkpoint_tables.py
# Description:
#   清理旧 LangGraph checkpoint 运行时残留表。
#
# Responsibilities:
#   - 删除已经不再由当前 AgentScope 主链使用的 checkpoint 表。
#   - 避免误删 Datalogue 自有会话、Workbench、BI Agent 和审计表。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

"""drop langgraph checkpoint tables

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-07-15 16:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


_DROP_TABLE_NAMES = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
    "checkpoint_migrations",
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    for table_name in _DROP_TABLE_NAMES:
        if _has_table(table_name):
            op.drop_table(table_name)  # 只清理旧 LangGraph runtime 表；业务真相源表不在白名单内。


def downgrade() -> None:
    # 这组表由旧 LangGraph checkpoint saver 运行时创建，并非 Datalogue Alembic 的业务建表来源；
    # 降级时不伪造旧 runtime schema，避免把废弃链路重新带回当前数据库。
    return None
