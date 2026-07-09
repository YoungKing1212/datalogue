# ============================================================
# File Name   : oracle.py
# Description:
#   Oracle 数据源适配器真实实现。
#
# Responsibilities:
#   - 使用 Oracle 数据字典读取 schema 可见性和 owner 列表。
#   - 复用通用 SQLAlchemy adapter 的连接、表结构和同步能力。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from sqlalchemy import text

from app.domains.data_source.adapters.base import DatasourceAdapter
from app.core.models.datasource import Datasource


class OracleAdapter(DatasourceAdapter):
    """Oracle 适配器，优先使用 SQLAlchemy Inspector，失败时回退数据字典。"""

    def schema_readable(self, conn) -> bool:
        try:
            conn.execute(text("SELECT owner FROM all_tables WHERE rownum = 1")).fetchone()
            return True
        except Exception:
            return False

    def get_schemas(self, ds: Datasource) -> list[str]:
        engine = self.create_engine(ds)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT DISTINCT owner
                        FROM all_tables
                        WHERE owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS')
                        ORDER BY owner
                        """
                    )
                ).fetchall()
                return [str(row[0]) for row in rows]
        finally:
            engine.dispose()


__all__ = ["OracleAdapter"]
