# ============================================================
# File Name   : base.py
# Description:
#   数据源 SQLAlchemy 适配器基类真实实现。
#
# Responsibilities:
#   - 统一构造数据源连接 URL 和 SQLAlchemy Engine。
#   - 提供通用连接测试、schema 读取、表字段同步和样例采集逻辑。
#   - 供专用适配器继承扩展，避免服务层承载 adapter 类体。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

import importlib
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core.security import decrypt_password
from app.domains.data_source.capabilities import DatasourceCapability
from app.domains.data_source.diagnostics import _diagnostic
from app.core.models.datasource import Datasource

SYSTEM_SCHEMAS = {
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
    "pg_catalog",
    "pg_toast",
}


def _connection_options(ds: Datasource) -> dict[str, Any]:
    """读取连接扩展参数；非 dict 时按空配置处理，保持旧 API 容错。"""
    value = getattr(ds, "connection_options", None)
    return value if isinstance(value, dict) else {}


def _normalize_db_type(value: str | None) -> str:
    """延迟使用注册表归一化，避免 registry 导入 adapter 时出现循环导入。"""
    from app.domains.data_source.adapters.registry import normalize_db_type

    return normalize_db_type(value)


def is_mysql_protocol_type(db_type: str | None) -> bool:
    """判断数据源是否走 MySQL 协议语义；Doris 第一阶段复用 MySQL 通路。"""
    return _normalize_db_type(db_type) in {"mysql", "doris"}


def _quote_identifier(name: str, db_type: str | None) -> str:
    """adapter 内部采样查询使用的标识符引用规则，与服务层 preview 规则保持一致。"""
    if not name:
        return name
    normalized = _normalize_db_type(db_type)
    if is_mysql_protocol_type(normalized) or normalized in {"hive", "trino", "presto", "bigquery", "clickhouse"}:
        return f"`{name}`"
    if normalized == "sqlserver":
        return f"[{name}]"
    return f'"{name}"'


def _table_ref(schema: str | None, table: str, db_type: str | None) -> str:
    """生成带 Schema 的表引用；SQLite 保持 main 连接内的单表引用。"""
    table_q = _quote_identifier(table, db_type)
    if schema and _normalize_db_type(db_type) != "sqlite":
        return f"{_quote_identifier(schema, db_type)}.{table_q}"
    return table_q


def _sample_column_values(
    conn,
    schema: str | None,
    table: str,
    column: str,
    db_type: str,
    limit: int = 5,
) -> list[str]:
    """从表中抽样获取某字段的非空唯一值；失败时由调用方决定降级方式。"""
    table_ref = _table_ref(schema, table, db_type)
    column_ref = _quote_identifier(column, db_type)
    if _normalize_db_type(db_type) == "oracle":
        q = text(
            f"SELECT DISTINCT {column_ref} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL FETCH FIRST :limit ROWS ONLY"
        )
    else:
        q = text(
            f"SELECT DISTINCT {column_ref} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL LIMIT :limit"
        )
    rows = conn.execute(q, {"limit": limit}).fetchall()
    return [str(r[0]) for r in rows if r[0] is not None]


def _sample_table_values(
    conn,
    schema: str | None,
    table: str,
    columns: list[str],
    db_type: str,
    *,
    value_limit: int = 5,
    scan_limit: int = 50,
) -> dict[str, list[str]]:
    """单次扫描一张表，为全部字段提取少量去重样例，避免逐字段重复连接和查询。"""
    if not columns:
        return {}
    table_ref = _table_ref(schema, table, db_type)
    column_refs = ", ".join(_quote_identifier(column, db_type) for column in columns)
    if _normalize_db_type(db_type) == "oracle":
        query = text(f"SELECT {column_refs} FROM {table_ref} FETCH FIRST :limit ROWS ONLY")
    else:
        query = text(f"SELECT {column_refs} FROM {table_ref} LIMIT :limit")
    rows = conn.execute(query, {"limit": scan_limit}).mappings().all()
    samples = {column: [] for column in columns}
    for row in rows:
        for column in columns:
            value = row.get(column)
            if value is None:
                continue
            rendered = str(value)
            if rendered not in samples[column] and len(samples[column]) < value_limit:
                samples[column].append(rendered)
    return samples


class DatasourceAdapter:
    """SQLAlchemy 优先的数据源适配器基类。"""

    capability: DatasourceCapability

    def __init__(self, capability: DatasourceCapability):
        self.capability = capability

    def normalize_db_type(self, value: str | None) -> str:
        return _normalize_db_type(value)

    def driver_available(self) -> bool:
        if not self.capability.driver_module:
            return True
        try:
            importlib.import_module(self.capability.driver_module)
            return True
        except ImportError:
            return False

    def build_url(self, ds: Datasource) -> str:
        password = decrypt_password(str(ds.password_enc))
        username = quote_plus(str(ds.username or ""))
        password = quote_plus(password)
        host = ds.host
        port = ds.port
        database = quote_plus(str(ds.database_name or ""))
        db_type = self.capability.db_type
        if db_type == "sqlite":
            return f"sqlite:///{ds.database_name}"
        if db_type == "oracle":
            options = _connection_options(ds)
            service_name = options.get("service_name")
            sid = options.get("sid")
            if service_name:
                return (
                    f"oracle+oracledb://{username}:{password}@{host}:{port}/"
                    f"?service_name={quote_plus(str(service_name))}"
                )
            if sid:
                return f"oracle+oracledb://{username}:{password}@{host}:{port}/?sid={quote_plus(str(sid))}"
            service_name = ds.database_name
            return (
                f"oracle+oracledb://{username}:{password}@{host}:{port}/"
                f"?service_name={quote_plus(str(service_name))}"
            )
        if db_type == "hive":
            auth = _connection_options(ds).get("auth")
            suffix = f"?auth={quote_plus(str(auth))}" if auth else ""
            return f"hive://{username}:{password}@{host}:{port}/{database}{suffix}"
        if db_type in {"trino", "presto"}:
            options = _connection_options(ds)
            catalog = options.get("catalog") or database
            schema = options.get("schema") or ds.default_schema or "default"
            return f"{db_type}://{username}:{password}@{host}:{port}/{catalog}/{schema}"
        if db_type == "bigquery":
            project = _connection_options(ds).get("project") or ds.database_name
            dataset = ds.default_schema or _connection_options(ds).get("dataset") or ""
            return f"bigquery://{project}/{dataset}"
        return (
            f"{self.capability.sqlalchemy_driver}://"
            f"{username}:{password}@{host}:{port}/{database}"
        )

    def create_engine(self, ds: Datasource) -> Engine:
        if not self.driver_available():
            raise ModuleNotFoundError(self.capability.driver_module or self.capability.sqlalchemy_driver)
        connect_args: dict[str, Any] = {}
        timeout = int(getattr(ds, "connect_timeout_seconds", None) or 10)
        db_type = self.capability.db_type
        if db_type == "sqlite":
            connect_args["check_same_thread"] = False
        elif is_mysql_protocol_type(db_type) or db_type in {"postgres", "postgresql"}:
            connect_args["connect_timeout"] = timeout
        elif db_type == "oracle":
            connect_args["tcp_connect_timeout"] = timeout
        url = self.build_url(ds)
        return create_engine(url, pool_pre_ping=True, pool_recycle=3600, connect_args=connect_args)

    def test_connection(self, ds: Datasource) -> dict[str, Any]:
        started_at = time.monotonic()
        engine = self.create_engine(ds)
        try:
            with engine.connect() as conn:
                conn.execute(text(self.capability.test_sql)).scalar()
                version = self.version(conn)
                schema_readable = self.schema_readable(conn)
            return {
                "ok": True,
                "code": None,
                "message": "连接成功",
                "version": version,
                "latency_ms": int((time.monotonic() - started_at) * 1000),
                "db_type": self.capability.db_type,
                "dialect": self.capability.dialect,
                "driver": self.capability.driver,
                "driver_status": "available",
                "schema_readable": schema_readable,
                "diagnostic": None,
            }
        finally:
            engine.dispose()

    def version(self, conn) -> str | None:
        try:
            db_type = self.capability.db_type
            if is_mysql_protocol_type(db_type) or db_type in {"postgres", "postgresql"}:
                return str(conn.execute(text("SELECT version()")).scalar())
            if db_type == "sqlite":
                return str(conn.execute(text("SELECT sqlite_version()")).scalar())
            if db_type == "oracle":
                return str(conn.execute(text("SELECT * FROM v$version WHERE rownum = 1")).scalar())
            if db_type in {"hive", "trino", "presto", "clickhouse", "sqlserver"}:
                return None
        except Exception:
            return None
        return None

    def schema_readable(self, conn) -> bool:
        try:
            inspect(conn).get_table_names(schema=self.capability.default_schema)
            return True
        except Exception:
            return False

    def get_schemas(self, ds: Datasource) -> list[str]:
        engine = self.create_engine(ds)
        try:
            inspector = inspect(engine)
            schemas = inspector.get_schema_names()
            result = [s for s in schemas if str(s).lower() not in SYSTEM_SCHEMAS]
            if not result and self.capability.default_schema:
                result = [self.capability.default_schema]
            return result
        finally:
            engine.dispose()

    def get_schema(self, ds: Datasource, schema_name: str | None = None) -> list[dict[str, Any]]:
        engine = self.create_engine(ds)
        db_type = self.capability.db_type
        schema = schema_name or ds.default_schema or self.capability.default_schema
        try:
            inspector = inspect(engine)
            tables = []
            with engine.connect() as conn:
                for table_name in inspector.get_table_names(schema=schema):
                    tables.append(self._table_schema(conn, inspector, ds, schema, table_name, db_type))
            return tables
        finally:
            engine.dispose()

    def sync_source_tables(
        self,
        ds: Datasource,
        schema_name: str | None = None,
    ) -> dict[str, Any]:
        schema = schema_name or ds.default_schema or self.capability.default_schema
        tables = self.get_schema(ds, schema_name=schema)
        result_tables: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for table in tables:
            raw_columns = table.get("columns") or []
            column_names = [str(col.get("name")) for col in raw_columns if col.get("name")]
            try:
                # Doris 宽表若逐字段建连采样会长时间阻塞；每张表只执行一次受限扫描。
                samples_by_column = self.sample_table_values(
                    ds,
                    table.get("schema_name"),
                    table["name"],
                    column_names,
                )
            except Exception as exc:
                skipped.append(
                    {
                        "table": table.get("name"),
                        "column": "*",
                        "diagnostic": _diagnostic("SAMPLE_UNREADABLE", "字段样例批量采集失败", exc),
                    }
                )
                samples_by_column = {}
            columns = []
            for idx, col in enumerate(raw_columns, start=1):
                column_name = col.get("name")
                columns.append(
                    {
                        "column_name": column_name,
                        "data_type": col.get("type"),
                        "column_comment": col.get("comment"),
                        "is_nullable": "YES" if col.get("nullable", True) else "NO",
                        "column_default": col.get("default"),
                        "ordinal_position": idx,
                        "sample_values": samples_by_column.get(str(column_name), []),
                    }
                )
            result_tables.append(
                {
                    "table_name": table["name"],
                    "schema_name": table.get("schema_name") or ds.default_schema or ds.database_name,
                    "table_comment": table.get("comment"),
                    "row_count_approx": table.get("row_count"),
                    "columns": columns,
                }
            )
        return {
            "tables": result_tables,
            "synced_at": datetime.utcnow().isoformat(),
            "skipped": skipped,
            "errors": [],
        }

    def sample_column_values(
        self,
        ds: Datasource,
        schema: str | None,
        table: str,
        column: str | None,
        limit: int = 5,
    ) -> list[str]:
        if not column:
            return []
        engine = self.create_engine(ds)
        try:
            with engine.connect() as conn:
                return _sample_column_values(
                    conn,
                    schema,
                    table,
                    column,
                    self.capability.db_type,
                    limit=limit,
                )
        finally:
            engine.dispose()

    def sample_table_values(
        self,
        ds: Datasource,
        schema: str | None,
        table: str,
        columns: list[str],
    ) -> dict[str, list[str]]:
        """使用单个连接批量采集整表字段样例。"""
        engine = self.create_engine(ds)
        try:
            with engine.connect() as conn:
                return _sample_table_values(
                    conn,
                    schema,
                    table,
                    columns,
                    self.capability.db_type,
                )
        finally:
            engine.dispose()

    def _table_schema(self, conn, inspector, ds, schema, table_name, db_type) -> dict[str, Any]:
        columns = []
        for col in inspector.get_columns(table_name, schema=schema):
            columns.append(
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": str(col.get("default")) if col.get("default") else None,
                    "comment": col.get("comment"),
                }
            )
        pk = inspector.get_pk_constraint(table_name, schema=schema)
        fks = inspector.get_foreign_keys(table_name, schema=schema)
        return {
            "name": table_name,
            "schema_name": schema or ds.default_schema or ds.database_name,
            "columns": columns,
            "primary_key": pk.get("constrained_columns", []) if pk else [],
            "foreign_keys": [
                {
                    "name": fk.get("name"),
                    "constrained_columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table"),
                    "referred_columns": fk.get("referred_columns", []),
                }
                for fk in fks
            ],
            "row_count": self._row_count(conn, schema, table_name, db_type),
            "size": None,
            "ddl": self._ddl(conn, schema, table_name, db_type),
        }

    def _row_count(self, conn, schema: str | None, table: str, db_type: str) -> int | None:
        try:
            if is_mysql_protocol_type(db_type):
                table_ref = _table_ref(schema, table, db_type)
                value = conn.execute(text(f"SELECT COUNT(*) FROM {table_ref}")).scalar()
                return int(value) if value is not None else None
            if db_type == "sqlite":
                value = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                return int(value) if value is not None else None
            if db_type in {"postgres", "postgresql"}:
                value = conn.execute(
                    text("SELECT reltuples::bigint FROM pg_class WHERE relname = :t AND relkind = 'r'"),
                    {"t": table},
                ).scalar()
                return int(value) if value is not None else None
        except Exception:
            return None
        return None

    def _ddl(self, conn, schema: str | None, table: str, db_type: str) -> str | None:
        try:
            if is_mysql_protocol_type(db_type):
                table_ref = _table_ref(schema, table, db_type)
                result = conn.execute(text(f"SHOW CREATE TABLE {table_ref}")).fetchone()
                return result[1] if result else None
        except Exception:
            return None
        return None


__all__ = ["DatasourceAdapter", "is_mysql_protocol_type"]
