# ============================================================
# File Name   : ab6832e0a3dd_add_source_tables_and_extend_metric_dim.py
# Description:
#   增加物理表元数据并扩展语义资产字段。
#
# Responsibilities:
#   - 创建源表和源字段目录表。
#   - 扩展指标、维度的表名、同义词和关联信息。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""add_source_tables_and_extend_metric_dim

Revision ID: ab6832e0a3dd
Revises: add_ds_status
Create Date: 2026-06-01 13:02:05.447309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab6832e0a3dd'
down_revision: Union[str, None] = 'add_ds_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # source_table and source_column already exist in the database
    # (created manually in a previous session), so we only add columns here.
    op.add_column('semantic_dimension', sa.Column('table_name', sa.String(length=100), nullable=True, comment='维度所属物理表名'))
    op.add_column('semantic_dimension', sa.Column('join_to', sa.String(length=100), nullable=True, comment='关联目标表名'))
    op.add_column('semantic_dimension', sa.Column('join_key', sa.String(length=100), nullable=True, comment='关联键列名'))
    op.add_column('semantic_dimension', sa.Column('hierarchy', sa.JSON(), nullable=True, comment='层级结构定义'))
    op.add_column('semantic_metric', sa.Column('table_name', sa.String(length=100), nullable=True, comment='指标所属物理表名'))
    op.add_column('semantic_metric', sa.Column('time_field', sa.String(length=100), nullable=True, comment='时间字段列名'))
    op.add_column('semantic_metric', sa.Column('granularity', sa.String(length=20), nullable=True, comment='时间粒度（day/week/month等）'))
    op.add_column('semantic_metric', sa.Column('format_str', sa.String(length=50), nullable=True, comment='数值格式化模板'))


def downgrade() -> None:
    op.drop_column('semantic_metric', 'format_str')
    op.drop_column('semantic_metric', 'granularity')
    op.drop_column('semantic_metric', 'time_field')
    op.drop_column('semantic_metric', 'table_name')
    op.drop_column('semantic_dimension', 'hierarchy')
    op.drop_column('semantic_dimension', 'join_key')
    op.drop_column('semantic_dimension', 'join_to')
    op.drop_column('semantic_dimension', 'table_name')
