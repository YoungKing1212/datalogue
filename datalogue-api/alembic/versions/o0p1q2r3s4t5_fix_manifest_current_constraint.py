# ============================================================
# File Name   : o0p1q2r3s4t5_fix_manifest_current_constraint.py
# Description:
#   修复 dataset_subagent_manifest 表的唯一约束问题。
#
#   问题背景:
#   - 表中存在两个与 is_current 相关的唯一索引：
#     1. uix_dataset_manifest_current: 对 (dataset_id, is_current) 的 FULL 唯一约束
#        → 错误：这会阻止同一个 dataset 有多行 is_current=false
#     2. ix_manifest_current: 对 (dataset_id) WHERE is_current 的 PARTIAL 唯一索引
#        → 正确：只保证每个 dataset 最多一个当前版本
#   - 当 publish_manifest 尝试将旧 current 行标记为 is_current=false 时，
#     如果已有 draft 行 (is_current=false)，会触发 UniqueViolation。
#
#   修复方案:
#   - 删除错误的 uix_dataset_manifest_current 全量唯一约束
#   - 保留正确的 ix_manifest_current 部分唯一索引
#
# Author      : yangkai
# Created On  : 2026-06-22
# ============================================================

"""fix_manifest_current_constraint

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "o0p1q2r3s4t5"
down_revision: Union[str, None] = "n9o0p1q2r3s4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 删除错误的 (dataset_id, is_current) 全量唯一约束。
    # 该约束阻止同一数据集存在多行 is_current=false（如 draft + archived）。
    # PostgreSQL 将 UNIQUE 约束实现为约束+索引，需要用 ALTER TABLE DROP CONSTRAINT。
    # CASCADE 会同时删除约束关联的索引。
    # 正确的部分唯一索引 ix_manifest_current (dataset_id WHERE is_current) 已存在，
    # 无需重建。
    op.execute(
        "ALTER TABLE dataset_subagent_manifest "
        "DROP CONSTRAINT IF EXISTS uix_dataset_manifest_current CASCADE"
    )


def downgrade() -> None:
    # 回滚：重建全量唯一约束（仅在回滚到之前版本时使用）。
    # 注意：如果表中已有多个 is_current=false 的行，重建会失败，
    # 需要先清理数据。
    op.execute(
        "ALTER TABLE dataset_subagent_manifest "
        "ADD CONSTRAINT uix_dataset_manifest_current "
        "UNIQUE (dataset_id, is_current)"
    )
