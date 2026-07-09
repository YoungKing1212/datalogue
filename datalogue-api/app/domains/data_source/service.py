# ============================================================
# File Name   : datasource.py
# Description:
#   多数据源连接、能力注册和结构探查服务。
#
# Responsibilities:
#   - 统一管理不同数据源类型的 SQLAlchemy 连接能力。
#   - 提供连接测试、Schema 拉取、表字段同步和字段样例采集。
#   - 将驱动缺失、权限不足、Schema 不可读等异常转成稳定诊断。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from __future__ import annotations

import importlib
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, NoSuchModuleError, OperationalError, SQLAlchemyError

from app.core.security import decrypt_password
from app.models.datasource import Datasource

logger = logging.getLogger(__name__)


SYSTEM_SCHEMAS = {
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
    "pg_catalog",
    "pg_toast",
}


DIAGNOSTIC_META = {
    "UNSUPPORTED_DB_TYPE": ("config", False, "请选择当前系统已注册的数据源类型。"),
    "DRIVER_MISSING": ("driver", False, "安装对应数据库驱动后重试，或改用已安装驱动的数据源。"),
    "CONNECTION_FAILED": ("connection", True, "检查主机、端口、网络、服务状态和连接参数。"),
    "AUTH_FAILED": ("auth", False, "检查用户名、密码和认证方式配置。"),
    "PERMISSION_DENIED": ("permission", False, "确认当前数据源账号具备读取库、schema、表和字段的权限。"),
    "SCHEMA_UNREADABLE": ("schema", False, "检查元数据读取权限，或缩小 schema 范围后重试。"),
    "SAMPLE_UNREADABLE": ("sample", True, "字段结构已同步，样例可稍后按表或字段重新采集。"),
    "DIALECT_UNSUPPORTED": ("dialect", False, "按目标数据源方言调整 SQL 或补充方言适配规则。"),
    "SQL_GUARD_BLOCKED": ("security", False, "仅允许执行当前数据集授权表上的单条只读查询。"),
    "QUERY_TIMEOUT": ("performance", True, "缩小查询范围、增加过滤条件或调大超时时间。"),
    "UNKNOWN_DATASOURCE_ERROR": ("unknown", True, "查看原始错误并按连接、权限或驱动问题继续排查。"),
}


@dataclass(frozen=True)
class DatasourceDiagnostic:
    """数据源链路的统一诊断结构。"""

    code: str
    message: str
    category: str
    retryable: bool
    suggested_action: str
    raw_error: str | None = None


@dataclass(frozen=True)
class DatasourceCapability:
    """描述一种数据源类型在当前系统中的能力边界。"""

    db_type: str
    label: str
    dialect: str
    driver: str | None
    driver_module: str | None
    sqlalchemy_driver: str
    default_port: int
    default_schema: str | None = None
    stable: bool = False
    required_options: tuple[str, ...] = ()
    optional_options: tuple[str, ...] = ()
    supports_sqlalchemy: bool = True
    test_sql: str = "SELECT 1"


@dataclass(frozen=True)
class DatasourceContext:
    """问数链路使用的规范化数据源上下文。"""

    datasource_id: int | None
    db_type: str
    dialect: str
    driver: str | None
    default_schema: str | None
    allowed_tables: list[str]
    query_timeout_seconds: int
    schema_version: str | None = None


def _diagnostic(code: str, message: str, raw_error: Any = None) -> dict[str, Any]:
    category, retryable, suggested_action = DIAGNOSTIC_META.get(
        code, DIAGNOSTIC_META["UNKNOWN_DATASOURCE_ERROR"]
    )
    return asdict(
        DatasourceDiagnostic(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            suggested_action=suggested_action,
            raw_error=str(raw_error) if raw_error not in (None, "") else None,
        )
    )


def _classify_exception(exc: Exception, default_code: str = "UNKNOWN_DATASOURCE_ERROR") -> dict[str, Any]:
    """把常见数据库异常归类为稳定错误码。"""
    message = str(exc)
    lower = message.lower()
    if isinstance(exc, (NoSuchModuleError, ModuleNotFoundError, ImportError)):
        return _diagnostic("DRIVER_MISSING", "数据源驱动未安装或 SQLAlchemy 方言不可用", message)
    if any(marker in lower for marker in ("permission denied", "access denied", "not authorized", "权限")):
        return _diagnostic("PERMISSION_DENIED", "数据源账号权限不足", message)
    if any(marker in lower for marker in ("authentication", "password", "login failed", "ora-01017")):
        return _diagnostic("AUTH_FAILED", "数据源认证失败", message)
    if any(marker in lower for marker in ("timeout", "timed out", "ora-01013", "query execution was interrupted")):
        return _diagnostic("QUERY_TIMEOUT", "数据源请求超时", message)
    if isinstance(exc, (OperationalError, DBAPIError, SQLAlchemyError)):
        return _diagnostic("CONNECTION_FAILED", "数据源连接或执行失败", message)
    return _diagnostic(default_code, "数据源操作失败", message)


class DatasourceAdapter:
    """SQLAlchemy 优先的数据源适配器基类。"""

    capability: DatasourceCapability

    def __init__(self, capability: DatasourceCapability):
        self.capability = capability

    def normalize_db_type(self, value: str | None) -> str:
        return normalize_db_type(value)

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
            service_name = options.get("service_name") or ds.database_name
            sid = options.get("sid")
            if sid:
                return f"oracle+oracledb://{username}:{password}@{host}:{port}/?sid={quote_plus(str(sid))}"
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
        elif db_type == "mysql":
            connect_args["connect_timeout"] = timeout
        elif db_type in {"postgres", "postgresql"}:
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
            if db_type in {"postgres", "postgresql", "mysql"}:
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

    def sync_source_tables(self, ds: Datasource) -> dict[str, Any]:
        tables = self.get_schema(ds, schema_name=ds.default_schema or self.capability.default_schema)
        result_tables: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for table in tables:
            columns = []
            for idx, col in enumerate(table.get("columns") or [], start=1):
                try:
                    columns.append(
                        {
                            "column_name": col.get("name"),
                            "data_type": col.get("type"),
                            "column_comment": col.get("comment"),
                            "is_nullable": "YES" if col.get("nullable", True) else "NO",
                            "column_default": col.get("default"),
                            "ordinal_position": idx,
                            "sample_values": self.sample_column_values(
                                ds,
                                table.get("schema_name"),
                                table["name"],
                                col.get("name"),
                            ),
                        }
                    )
                except Exception as exc:
                    skipped.append(
                        {
                            "table": table.get("name"),
                            "column": col.get("name"),
                            "diagnostic": _diagnostic(
                                "SAMPLE_UNREADABLE",
                                "字段样例采集失败",
                                exc,
                            ),
                        }
                    )
                    columns.append(
                        {
                            "column_name": col.get("name"),
                            "data_type": col.get("type"),
                            "column_comment": col.get("comment"),
                            "is_nullable": "YES" if col.get("nullable", True) else "NO",
                            "column_default": col.get("default"),
                            "ordinal_position": idx,
                            "sample_values": [],
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
            "ddl": self._ddl(conn, table_name, db_type),
        }

    def _row_count(self, conn, schema: str | None, table: str, db_type: str) -> int | None:
        try:
            if db_type == "mysql":
                return conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
            if db_type == "sqlite":
                return conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            if db_type in {"postgres", "postgresql"}:
                return conn.execute(
                    text("SELECT reltuples::bigint FROM pg_class WHERE relname = :t AND relkind = 'r'"),
                    {"t": table},
                ).scalar()
        except Exception:
            return None
        return None

    def _ddl(self, conn, table: str, db_type: str) -> str | None:
        try:
            if db_type == "mysql":
                result = conn.execute(text(f"SHOW CREATE TABLE `{table}`")).fetchone()
                return result[1] if result else None
        except Exception:
            return None
        return None


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


CAPABILITIES: dict[str, DatasourceCapability] = {
    "mysql": DatasourceCapability(
        db_type="mysql",
        label="MySQL",
        dialect="mysql",
        driver="pymysql",
        driver_module="pymysql",
        sqlalchemy_driver="mysql+pymysql",
        default_port=3306,
        stable=True,
        test_sql="SELECT 1",
    ),
    "postgres": DatasourceCapability(
        db_type="postgres",
        label="PostgreSQL",
        dialect="postgres",
        driver="psycopg2",
        driver_module="psycopg2",
        sqlalchemy_driver="postgresql+psycopg2",
        default_port=5432,
        default_schema="public",
        stable=True,
        test_sql="SELECT 1",
    ),
    "sqlite": DatasourceCapability(
        db_type="sqlite",
        label="SQLite",
        dialect="sqlite",
        driver=None,
        driver_module=None,
        sqlalchemy_driver="sqlite",
        default_port=0,
        default_schema="main",
        stable=True,
        test_sql="SELECT 1",
    ),
    "oracle": DatasourceCapability(
        db_type="oracle",
        label="Oracle",
        dialect="oracle",
        driver="oracledb",
        driver_module="oracledb",
        sqlalchemy_driver="oracle+oracledb",
        default_port=1521,
        required_options=("service_name",),
        optional_options=("sid",),
        test_sql="SELECT 1 FROM DUAL",
    ),
    "hive": DatasourceCapability(
        db_type="hive",
        label="Hive",
        dialect="hive",
        driver="pyhive",
        driver_module="pyhive.hive",
        sqlalchemy_driver="hive",
        default_port=10000,
        default_schema="default",
        optional_options=("auth", "protocol", "kerberos_service_name"),
        test_sql="SELECT 1",
    ),
    "clickhouse": DatasourceCapability(
        db_type="clickhouse",
        label="ClickHouse",
        dialect="clickhouse",
        driver="clickhouse-sqlalchemy",
        driver_module="clickhouse_sqlalchemy",
        sqlalchemy_driver="clickhouse+native",
        default_port=9000,
    ),
    "sqlserver": DatasourceCapability(
        db_type="sqlserver",
        label="SQL Server",
        dialect="tsql",
        driver="pyodbc",
        driver_module="pyodbc",
        sqlalchemy_driver="mssql+pyodbc",
        default_port=1433,
        optional_options=("driver_name", "instance"),
    ),
    "trino": DatasourceCapability(
        db_type="trino",
        label="Trino",
        dialect="trino",
        driver="trino",
        driver_module="trino",
        sqlalchemy_driver="trino",
        default_port=8080,
        optional_options=("catalog", "schema"),
    ),
    "presto": DatasourceCapability(
        db_type="presto",
        label="Presto",
        dialect="presto",
        driver="pyhive",
        driver_module="pyhive.presto",
        sqlalchemy_driver="presto",
        default_port=8080,
        optional_options=("catalog", "schema"),
    ),
    "bigquery": DatasourceCapability(
        db_type="bigquery",
        label="BigQuery",
        dialect="bigquery",
        driver="sqlalchemy-bigquery",
        driver_module="sqlalchemy_bigquery",
        sqlalchemy_driver="bigquery",
        default_port=0,
        optional_options=("project", "dataset", "credentials_path"),
    ),
}


ALIASES = {
    "postgresql": "postgres",
    "pg": "postgres",
    "mssql": "sqlserver",
    "sql_server": "sqlserver",
}


ADAPTERS: dict[str, DatasourceAdapter] = {
    key: DatasourceAdapter(capability) for key, capability in CAPABILITIES.items()
}
ADAPTERS["oracle"] = OracleAdapter(CAPABILITIES["oracle"])
ADAPTERS["hive"] = HiveAdapter(CAPABILITIES["hive"])


def normalize_db_type(value: str | None) -> str:
    """归一化数据源类型标识。"""
    normalized = str(value or "postgres").strip().lower()
    return ALIASES.get(normalized, normalized)


def get_capabilities() -> list[dict[str, Any]]:
    """返回前端创建表单可使用的数据源能力列表。"""
    items: list[dict[str, Any]] = []
    for capability in CAPABILITIES.values():
        adapter = ADAPTERS[capability.db_type]
        if not capability.driver_module:
            driver_status = "builtin"
            install_hint = None
        elif adapter.driver_available():
            driver_status = "installed"
            install_hint = None
        else:
            driver_status = "missing"
            install_hint = (
                "请在有网构建机执行 datalogue-api/scripts/download_enterprise_wheels.sh，"
                "再在内网使用 pip install --no-index --find-links ./wheelhouse "
                "-r requirements-enterprise.txt 安装。"
            )
        items.append(
            {
                "db_type": capability.db_type,
                "label": capability.label,
                "dialect": capability.dialect,
                "driver": capability.driver,
                "driver_module": capability.driver_module,
                "driver_status": driver_status,
                "install_hint": install_hint,
                "default_port": capability.default_port,
                "default_schema": capability.default_schema,
                "stable": capability.stable,
                "required_options": list(capability.required_options),
                "optional_options": list(capability.optional_options),
                "supports_sqlalchemy": capability.supports_sqlalchemy,
            }
        )
    return items


def get_adapter(db_type: str | None) -> DatasourceAdapter:
    """按 db_type 获取适配器，不支持时抛出稳定诊断异常。"""
    normalized = normalize_db_type(db_type)
    adapter = ADAPTERS.get(normalized)
    if not adapter:
        raise ValueError(f"Unsupported datasource type: {db_type}")
    return adapter


def _connection_options(ds: Datasource) -> dict[str, Any]:
    value = getattr(ds, "connection_options", None)
    return value if isinstance(value, dict) else {}


def enrich_datasource_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """创建或更新数据源前补齐 dialect、driver、默认端口等字段。"""
    db_type = normalize_db_type(data.get("db_type"))
    data["db_type"] = db_type
    capability = CAPABILITIES.get(db_type)
    if not capability:
        return data
    if not data.get("dialect"):
        data["dialect"] = capability.dialect
    if not data.get("driver"):
        data["driver"] = capability.driver
    if data.get("port") in (None, 0) and capability.default_port:
        data["port"] = capability.default_port
    if not data.get("default_schema"):
        data["default_schema"] = capability.default_schema
    if data.get("connection_options") is None:
        data["connection_options"] = {}
    if data.get("connect_timeout_seconds") is None:
        data["connect_timeout_seconds"] = 10
    if data.get("query_timeout_seconds") is None:
        data["query_timeout_seconds"] = 30
    return data


def build_datasource_context(
    ds: Datasource | None,
    *,
    allowed_tables: list[str] | None = None,
    schema_version: str | None = None,
) -> dict[str, Any] | None:
    """构建问数链路透传的数据源上下文。"""
    if ds is None:
        return None
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    capability = CAPABILITIES.get(db_type)
    dialect = getattr(ds, "dialect", None) or (capability.dialect if capability else db_type)
    context = DatasourceContext(
        datasource_id=getattr(ds, "id", None),
        db_type=db_type,
        dialect=dialect,
        driver=getattr(ds, "driver", None) or (capability.driver if capability else None),
        default_schema=getattr(ds, "default_schema", None)
        or (capability.default_schema if capability else None),
        allowed_tables=allowed_tables or [],
        query_timeout_seconds=int(getattr(ds, "query_timeout_seconds", None) or 30),
        schema_version=schema_version,
    )
    return asdict(context)


def create_engine_for_datasource(ds: Datasource) -> Engine:
    """为指定数据源创建 SQLAlchemy Engine。"""
    adapter = get_adapter(getattr(ds, "db_type", None))
    return adapter.create_engine(ds)


def test_connection(ds: Datasource) -> dict[str, Any]:
    """测试数据源连接，返回统一诊断结构。"""
    try:
        adapter = get_adapter(getattr(ds, "db_type", None))
    except ValueError as exc:
        diagnostic = _diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc)
        return {"ok": False, "message": diagnostic["message"], **diagnostic}
    try:
        if not adapter.driver_available():
            diagnostic = _diagnostic(
                "DRIVER_MISSING",
                f"{adapter.capability.label} 驱动未安装",
                adapter.capability.driver_module,
            )
            return {
                "ok": False,
                "message": diagnostic["message"],
                "db_type": adapter.capability.db_type,
                "dialect": adapter.capability.dialect,
                "driver": adapter.capability.driver,
                "driver_status": "missing",
                "schema_readable": False,
                "diagnostic": diagnostic,
                **diagnostic,
            }
        return adapter.test_connection(ds)
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="CONNECTION_FAILED")
        return {
            "ok": False,
            "message": diagnostic["message"],
            "db_type": adapter.capability.db_type,
            "dialect": adapter.capability.dialect,
            "driver": adapter.capability.driver,
            "driver_status": "available" if adapter.driver_available() else "missing",
            "schema_readable": False,
            "diagnostic": diagnostic,
            **diagnostic,
        }


def sync_source_tables(ds: Datasource) -> dict[str, Any]:
    """连接数据源，拉取所有表和字段信息。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).sync_source_tables(ds)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def get_schemas(ds: Datasource) -> list[str]:
    """获取数据源中的 schema/database 列表。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).get_schemas(ds)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def get_schema(ds: Datasource, schema_name: str = None) -> list[dict[str, Any]]:
    """获取指定 schema 的表和字段元信息。"""
    try:
        return get_adapter(getattr(ds, "db_type", None)).get_schema(ds, schema_name=schema_name)
    except ValueError as exc:
        raise RuntimeError(_diagnostic("UNSUPPORTED_DB_TYPE", "当前数据源类型尚未注册", exc))
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="SCHEMA_UNREADABLE")
        raise RuntimeError(diagnostic)


def quote_identifier(name: str, db_type: str | None) -> str:
    """按数据源类型引用标识符。"""
    if not name:
        return name
    normalized = normalize_db_type(db_type)
    if normalized == "mysql":
        return f"`{name}`"
    if normalized in {"hive", "trino", "presto", "bigquery", "clickhouse"}:
        return f"`{name}`"
    if normalized == "sqlserver":
        return f"[{name}]"
    return f'"{name}"'


def _table_ref(schema: str | None, table: str, db_type: str | None) -> str:
    table_q = quote_identifier(table, db_type)
    if schema and normalize_db_type(db_type) not in {"mysql", "sqlite"}:
        return f"{quote_identifier(schema, db_type)}.{table_q}"
    return table_q


def preview_table(ds: Datasource, schema: str | None, table: str, limit: int = 5) -> dict[str, Any]:
    """从数据源实时查询某张表的前 N 条数据。"""
    db_type = normalize_db_type(getattr(ds, "db_type", None))
    engine = create_engine_for_datasource(ds)
    try:
        with engine.connect() as conn:
            table_ref = _table_ref(schema, table, db_type)
            sql = f"SELECT * FROM {table_ref} LIMIT :limit"
            if db_type == "oracle":
                sql = f"SELECT * FROM {table_ref} FETCH FIRST :limit ROWS ONLY"
            result = conn.execute(text(sql), {"limit": int(limit or 5)})
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return {"columns": columns, "rows": rows}
    except Exception as exc:
        diagnostic = _classify_exception(exc, default_code="UNKNOWN_DATASOURCE_ERROR")
        raise RuntimeError(diagnostic)
    finally:
        engine.dispose()


def _sample_column_values(
    conn,
    schema: Optional[str],
    table: str,
    column: str,
    db_type: str,
    limit: int = 5,
) -> list[str]:
    """从表中抽样获取某字段的非空唯一值。"""
    try:
        table_ref = _table_ref(schema, table, db_type)
        column_ref = quote_identifier(column, db_type)
        if normalize_db_type(db_type) == "oracle":
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
    except Exception as exc:
        logger.warning("抽样字段失败: %s.%s error=%s", table, column, exc)
        return []
