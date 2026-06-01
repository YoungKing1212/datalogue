# 数据源连接服务 — 根据 db_type 创建真实数据库连接，支持连接测试和 Schema 提取

from typing import List, Dict, Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core.security import decrypt_password
from app.models.datasource import Datasource


# 数据库驱动映射：db_type -> SQLAlchemy URL 前缀
def _build_url(ds: Datasource) -> str:
    """根据数据源配置构建 SQLAlchemy 连接 URL。"""
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
    url = _build_url(ds)
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def test_connection(ds: Datasource) -> Dict[str, Any]:
    """测试数据源连接是否可用，返回版本信息和延迟。"""
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

            return {
                "ok": True,
                "message": "连接成功",
                "version": version,
            }
    except Exception as e:
        return {
            "ok": False,
            "message": f"连接失败: {str(e)}",
        }
    finally:
        engine.dispose()


def get_schemas(ds: Datasource) -> List[str]:
    """获取数据源中的所有 schema（MySQL 中为数据库列表）。"""
    engine = create_engine_for_datasource(ds)
    try:
        inspector = inspect(engine)
        schemas = inspector.get_schema_names()
        # 过滤掉系统 schema
        system_schemas = {'information_schema', 'mysql', 'performance_schema', 'sys', 'pg_catalog', 'pg_toast'}
        return [s for s in schemas if s not in system_schemas]
    finally:
        engine.dispose()


def get_schema(ds: Datasource, schema_name: str = None) -> List[Dict[str, Any]]:
    """使用 SQLAlchemy inspect 反射获取指定 schema 的表和字段元信息。"""
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

        return tables
    finally:
        engine.dispose()
