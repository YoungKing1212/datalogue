# ============================================================
# File Name   : hive.py
# Description:
#   Hive 数据源适配器真实实现。
#
# Responsibilities:
#   - 使用 Hive SHOW/DESCRIBE 语句读取库、表和字段元数据。
#   - 在 DESCRIBE 单表失败时保留表结构同步主流程，仅记录字段读取降级。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.domains.data_source.adapters.base import DatasourceAdapter
from app.core.models.datasource import Datasource

logger = logging.getLogger(__name__)


class HiveAdapter(DatasourceAdapter):
    """Hive 的 SQLAlchemy 兼容适配器，补充 SHOW 语句元数据读取。"""

    def get_schemas(self, ds: Datasource) -> list[str]:
        engine = self.create_engine(ds)
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("SHOW DATABASES")).fetchall()
                return [str(row[0]) for row in rows]
        finally:
            engine.dispose()

    def get_schema(self, ds: Datasource, schema_name: str | None = None) -> list[dict[str, Any]]:
        schema = schema_name or ds.default_schema or ds.database_name or "default"
        engine = self.create_engine(ds)
        try:
            with engine.connect() as conn:
                table_rows = conn.execute(text(f"SHOW TABLES IN `{schema}`")).fetchall()
                tables = []
                for row in table_rows:
                    table_name = str(row[0])
                    columns = []
                    try:
                        col_rows = conn.execute(text(f"DESCRIBE `{schema}`.`{table_name}`")).fetchall()
                        for col in col_rows:
                            col_name = str(col[0] or "").strip()
                            if not col_name or col_name.startswith("#"):
                                continue
                            columns.append(
                                {
                                    "name": col_name,
                                    "type": str(col[1] or ""),
                                    "nullable": True,
                                    "default": None,
                                    "comment": str(col[2] or "") or None,
                                }
                            )
                    except Exception as exc:
                        logger.warning("Hive DESCRIBE 失败: table=%s error=%s", table_name, exc)
                    tables.append(
                        {
                            "name": table_name,
                            "schema_name": schema,
                            "columns": columns,
                            "primary_key": [],
                            "foreign_keys": [],
                            "row_count": None,
                            "size": None,
                            "ddl": None,
                        }
                    )
                return tables
        finally:
            engine.dispose()


__all__ = ["HiveAdapter"]
