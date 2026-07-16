# ============================================================
# File Name   : e2f3a4b5c6d7_add_dataset_schema_name.py
# Description:
#   为语义数据集增加物理 Schema 绑定字段。
#
# Responsibilities:
#   - 新增 semantic_dataset.schema_name 并回填历史数据集。
#   - 优先沿用已选表 Schema，缺失时按数据源类型推导安全默认值。
#
# Author      : yangkai
# Created On  : 2026-07-16
# ============================================================

"""add dataset schema name

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-16 12:41:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("semantic_dataset", sa.Column("schema_name", sa.String(length=100), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE semantic_dataset AS dataset
            SET schema_name = COALESCE(
                (
                    SELECT MIN(source_table.schema_name)
                    FROM dataset_source_table AS link
                    JOIN source_table ON source_table.id = link.source_table_id
                    WHERE link.dataset_id = dataset.id
                ),
                NULLIF(TRIM(datasource.default_schema), ''),
                CASE
                    WHEN LOWER(datasource.db_type) = 'sqlite' THEN 'main'
                    WHEN LOWER(datasource.db_type) IN ('postgres', 'postgresql', 'pg') THEN 'public'
                    WHEN LOWER(datasource.db_type) = 'oracle' THEN UPPER(datasource.username)
                    ELSE NULLIF(TRIM(datasource.database_name), '')
                END,
                'public'
            )
            FROM datasource
            WHERE datasource.id = dataset.datasource_id
            """
        )
    )
    op.alter_column("semantic_dataset", "schema_name", existing_type=sa.String(length=100), nullable=False)


def downgrade() -> None:
    op.drop_column("semantic_dataset", "schema_name")
