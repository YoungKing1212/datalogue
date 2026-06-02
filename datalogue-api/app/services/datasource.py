# 数据源连接服务 — 根据 db_type 创建真实数据库连接，支持连接测试和 Schema 提取

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core.security import decrypt_password
from app.models.datasource import Datasource

logger = logging.getLogger(__name__)


# 数据库驱动映射：db_type -> SQLAlchemy URL 前缀
def _build_url(ds: Datasource) -> str:
    """根据数据源配置构建 SQLAlchemy 连接 URL。"""
    logger.info(f"构建连接URL: ds_id={ds.id}, type={ds.db_type}")
    password = decrypt_password(str(ds.password_enc))
    db_type = ds.db_type.lower()

    if db_type in ("postgres", "postgresql"):
        return (
            f"postgresql+psycopg2://{ds.username}:{password}@{ds.host}:{ds.port}/{ds.database_name}"
        )
    elif db_type == "mysql":
        return f"mysql+pymysql://{ds.username}:{password}@{ds.host}:{ds.port}/{ds.database_name}"
    elif db_type == "oracle":
        return f"oracle+cx_oracle://{ds.username}:{password}@{ds.host}:{ds.port}/{ds.database_name}"
    elif db_type == "sqlite":
        return f"sqlite:///{ds.database_name}"
    else:
        # 默认按 PostgreSQL 处理
        return (
            f"postgresql+psycopg2://{ds.username}:{password}@{ds.host}:{ds.port}/{ds.database_name}"
        )


def create_engine_for_datasource(ds: Datasource) -> Engine:
    """为指定数据源创建 SQLAlchemy Engine。"""
    logger.info(f"创建数据库引擎: ds_id={ds.id}, host={ds.host}")
    url = _build_url(ds)
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def test_connection(ds: Datasource) -> Dict[str, Any]:
    """测试数据源连接是否可用，返回版本信息和延迟。"""
    logger.info(f"测试连接: ds_id={ds.id}, host={ds.host}:{ds.port}")
    engine = create_engine_for_datasource(ds)
    try:
        with engine.connect() as conn:
            # 执行简单查询测试连通性
            result = conn.execute(text("SELECT 1"))
            result.scalar()

            # 尝试获取数据库版本
            version = None
            db_type = ds.db_type.lower()
            if db_type in ("postgres", "postgresql"):
                version = conn.execute(text("SELECT version()")).scalar()
            elif db_type == "mysql":
                version = conn.execute(text("SELECT version()")).scalar()

            logger.info(f"连接成功: version={version}")
            return {
                "ok": True,
                "message": "连接成功",
                "version": version,
            }
    except Exception as e:
        logger.error(f"连接失败: {e}")
        return {
            "ok": False,
            "message": f"连接失败: {str(e)}",
        }
    finally:
        engine.dispose()


def sync_source_tables(ds: Datasource) -> Dict[str, Any]:
    """连接数据源，拉取所有表和字段信息，返回结构化数据供 API 层写入 source_table / source_column。
    
    返回 {"tables": [{table_name, schema_name, table_comment, row_count_approx, columns: [...]}]}
    """
    logger.info(f"同步表结构: ds_id={ds.id}, type={ds.db_type}")
    engine = create_engine_for_datasource(ds)
    db_type = ds.db_type.lower()
    result_tables = []

    try:
        with engine.connect() as conn:
            if db_type in ("postgres", "postgresql"):
                # PostgreSQL: get all tables in all non-system schemas
                table_rows = conn.execute(text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE table_type = 'BASE TABLE' 
                    AND table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                    ORDER BY table_schema, table_name
                """)).fetchall()

                for schema_name, table_name in table_rows:
                    # Row count
                    row_count = conn.execute(text(
                        "SELECT reltuples::bigint FROM pg_class WHERE relname = :t AND relkind = 'r'"
                    ), {"t": table_name}).scalar()

                    # Table comment
                    table_comment = conn.execute(text("""
                        SELECT obj_description(
                            (quote_ident(:s) || '.' || quote_ident(:t))::regclass
                        )
                    """), {"s": schema_name, "t": table_name}).scalar()

                    # Columns
                    col_rows = conn.execute(text("""
                        SELECT 
                            c.column_name, c.data_type, c.is_nullable, c.column_default,
                            c.ordinal_position,
                            pgd.description as column_comment
                        FROM information_schema.columns c
                        LEFT JOIN pg_catalog.pg_description pgd 
                            ON pgd.objsubid = c.ordinal_position
                            AND pgd.objoid = (
                                SELECT oid FROM pg_catalog.pg_class 
                                WHERE relname = :t AND relnamespace = (
                                    SELECT oid FROM pg_catalog.pg_namespace WHERE nspname = :s
                                )
                            )
                        WHERE c.table_schema = :s AND c.table_name = :t
                        ORDER BY c.ordinal_position
                    """), {"s": schema_name, "t": table_name}).fetchall()

                    columns = []
                    for col in col_rows:
                        col_name, data_type, is_nullable, col_default, ordinal_pos, col_comment = col
                        sample_vals = _sample_column_values(conn, schema_name, table_name, col_name, db_type)
                        columns.append({
                            "column_name": col_name,
                            "data_type": data_type,
                            "column_comment": col_comment,
                            "is_nullable": is_nullable,
                            "column_default": col_default,
                            "ordinal_position": ordinal_pos,
                            "sample_values": sample_vals,
                        })

                    result_tables.append({
                        "table_name": table_name,
                        "schema_name": schema_name,
                        "table_comment": table_comment,
                        "row_count_approx": row_count,
                        "columns": columns,
                    })

            elif db_type == "mysql":
                # MySQL: get all tables in the current database
                table_rows = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_type = 'BASE TABLE' 
                    AND table_schema = DATABASE()
                    ORDER BY table_name
                """)).fetchall()

                for (table_name,) in table_rows:
                    # Row count
                    row_count = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()

                    # Table comment
                    table_comment_row = conn.execute(text("""
                        SELECT table_comment FROM information_schema.tables 
                        WHERE table_schema = DATABASE() AND table_name = :t
                    """), {"t": table_name}).fetchone()
                    table_comment = table_comment_row[0] if table_comment_row else None

                    # Columns
                    col_rows = conn.execute(text("""
                        SELECT column_name, data_type, is_nullable, column_default,
                               ordinal_position, column_comment
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE() AND table_name = :t
                        ORDER BY ordinal_position
                    """), {"t": table_name}).fetchall()

                    columns = []
                    for col in col_rows:
                        col_name, data_type, is_nullable, col_default, ordinal_pos, col_comment = col
                        sample_vals = _sample_column_values(conn, None, table_name, col_name, db_type)
                        columns.append({
                            "column_name": col_name,
                            "data_type": data_type,
                            "column_comment": col_comment,
                            "is_nullable": is_nullable,
                            "column_default": col_default,
                            "ordinal_position": ordinal_pos,
                            "sample_values": sample_vals,
                        })

                    result_tables.append({
                        "table_name": table_name,
                        "schema_name": ds.database_name,
                        "table_comment": table_comment,
                        "row_count_approx": row_count,
                        "columns": columns,
                    })

            elif db_type == "sqlite":
                # SQLite: get all tables
                table_rows = conn.execute(text("""
                    SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """)).fetchall()

                for (table_name,) in table_rows:
                    # Row count
                    row_count = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()

                    # Columns via PRAGMA
                    col_rows = conn.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()

                    columns = []
                    for col in col_rows:
                        # PRAGMA table_info returns: (cid, name, type, notnull, dflt_value, pk)
                        _, col_name, data_type, notnull, col_default, _ = col
                        sample_vals = _sample_column_values(conn, None, table_name, col_name, db_type)
                        columns.append({
                            "column_name": col_name,
                            "data_type": data_type,
                            "column_comment": None,
                            "is_nullable": "NO" if notnull else "YES",
                            "column_default": col_default,
                            "ordinal_position": None,
                            "sample_values": sample_vals,
                        })

                    result_tables.append({
                        "table_name": table_name,
                        "schema_name": "main",
                        "table_comment": None,
                        "row_count_approx": row_count,
                        "columns": columns,
                    })

    finally:
        engine.dispose()

    logger.info(f"同步完成: 共 {len(result_tables)} 张表")
    return {"tables": result_tables, "synced_at": datetime.utcnow().isoformat()}


def _sample_column_values(conn, schema: Optional[str], table: str, column: str, db_type: str, limit: int = 5) -> List[str]:
    """从表中抽样获取某字段的非空唯一值。"""
    logger.debug(f"抽样字段: {table}.{column}")
    try:
        if db_type in ("postgres", "postgresql"):
            q = text(f'SELECT DISTINCT "{column}" FROM "{schema}"."{table}" WHERE "{column}" IS NOT NULL LIMIT :limit')
        elif db_type == "mysql":
            q = text(f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL LIMIT :limit")
        elif db_type == "sqlite":
            q = text(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT :limit')
        else:
            return []
        rows = conn.execute(q, {"limit": limit}).fetchall()
        return [str(r[0]) for r in rows if r[0] is not None]
    except Exception:
        logger.warning(f"抽样字段失败: {table}.{column}")
        return []


def get_schemas(ds: Datasource) -> List[str]:
    """获取数据源中的所有 schema（MySQL 中为数据库列表）。"""
    logger.info(f"获取schema列表: ds_id={ds.id}")
    engine = create_engine_for_datasource(ds)
    try:
        inspector = inspect(engine)
        schemas = inspector.get_schema_names()
        # 过滤掉系统 schema
        system_schemas = {'information_schema', 'mysql', 'performance_schema', 'sys', 'pg_catalog', 'pg_toast'}
        result = [s for s in schemas if s not in system_schemas]
        logger.info(f"返回 {len(result)} 个schema")
        return result
    finally:
        engine.dispose()


def get_schema(ds: Datasource, schema_name: str = None) -> List[Dict[str, Any]]:
    """使用 SQLAlchemy inspect 反射获取指定 schema 的表和字段元信息。"""
    logger.info(f"获取schema详情: ds_id={ds.id}, schema_name={schema_name}")
    engine = create_engine_for_datasource(ds)
    db_type = ds.db_type.lower()
    try:
        inspector = inspect(engine)
        tables = []

        with engine.connect() as conn:
            for table_name in inspector.get_table_names(schema=schema_name):
                columns = []
                for col in inspector.get_columns(table_name, schema=schema_name):
                    columns.append(
                        {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col.get("nullable", True),
                            "default": str(col.get("default")) if col.get("default") else None,
                        }
                    )

                pk = inspector.get_pk_constraint(table_name, schema=schema_name)
                pk_columns = pk.get("constrained_columns", []) if pk else []

                fks = inspector.get_foreign_keys(table_name, schema=schema_name)
                fk_list = []
                for fk in fks:
                    fk_list.append(
                        {
                            "name": fk.get("name"),
                            "constrained_columns": fk.get("constrained_columns", []),
                            "referred_table": fk.get("referred_table"),
                            "referred_columns": fk.get("referred_columns", []),
                        }
                    )

                row_count = None
                size = None
                try:
                    if db_type in ("postgres", "postgresql"):
                        row_count = conn.execute(
                            text(
                                "SELECT reltuples::bigint FROM pg_class WHERE relname = :t AND relkind = 'r'"
                            ),
                            {"t": table_name},
                        ).scalar()
                        size_val = conn.execute(
                            text("SELECT pg_size_pretty(pg_table_size(:t::regclass))"),
                            {"t": table_name},
                        ).scalar()
                        size = size_val
                    elif db_type == "mysql":
                        # MySQL information_schema.TABLE_ROWS 对 InnoDB 是估算值，经常不准确，
                        # 改用 COUNT(*) 获取准确行数
                        try:
                            row_count = conn.execute(
                                text(f"SELECT COUNT(*) FROM `{table_name}`")
                            ).scalar()
                        except Exception:
                            row_count = None
                        size_val = conn.execute(
                            text("""
                            SELECT ROUND((data_length + index_length) / 1024 / 1024, 2)
                            FROM information_schema.tables WHERE table_schema = :db AND table_name = :t
                        """),
                            {"db": ds.database_name, "t": table_name},
                        ).scalar()
                        if size_val:
                            size = f"{size_val} MB"
                except Exception:
                    pass

                ddl = None
                try:
                    if db_type in ("postgres", "postgresql"):
                        ddl = conn.execute(
                            text("""
                            SELECT definition FROM pg_views WHERE viewname = :t AND schemaname = 'public'
                        """),
                            {"t": table_name},
                        ).scalar()
                        if not ddl:
                            col_info = conn.execute(
                                text("""
                                SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
                                FROM information_schema.columns WHERE table_name = :t AND table_schema = 'public'
                                ORDER BY ordinal_position
                            """),
                                {"t": table_name},
                            ).fetchall()
                            pk_info = conn.execute(
                                text("""
                                SELECT kcu.column_name FROM information_schema.table_constraints tc
                                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                                WHERE tc.table_name = :t AND tc.constraint_type = 'PRIMARY KEY'
                            """),
                                {"t": table_name},
                            ).fetchall()
                            pk_cols = [r[0] for r in pk_info]
                            lines = [f"CREATE TABLE {table_name} ("]
                            for ci in col_info:
                                col_name, data_type, max_len, nullable, default_val = ci
                                line = f"  {col_name} {data_type}"
                                if max_len:
                                    line += f"({max_len})"
                                if col_name in pk_cols:
                                    line += " PRIMARY KEY"
                                if nullable == "NO":
                                    line += " NOT NULL"
                                elif default_val:
                                    line += f" DEFAULT {default_val}"
                                lines.append(line)
                            lines.append(");")
                            ddl = "\n".join(lines)
                    elif db_type == "mysql":
                        result = conn.execute(text("SHOW CREATE TABLE " + table_name)).fetchone()
                        if result:
                            ddl = result[1]
                except Exception:
                    ddl = None

                tables.append(
                    {
                        "name": table_name,
                        "columns": columns,
                        "primary_key": pk_columns,
                        "foreign_keys": fk_list,
                        "row_count": row_count,
                        "size": size,
                        "ddl": ddl,
                    }
                )

        logger.info(f"返回 {len(tables)} 张表")
        return tables
    finally:
        engine.dispose()
