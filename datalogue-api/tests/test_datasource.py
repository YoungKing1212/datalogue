# ============================================================
# File Name   : test_datasource.py
# Description:
#   数据源 API 和服务测试。
#
# Responsibilities:
#   - 验证数据源增删改查和连接检查。
#   - 覆盖结构同步和数据预览辅助逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
数据源管理 API 测试
"""

import importlib.util
from pathlib import Path

from app.core.models.datasource import Datasource
from app.core.security import encrypt_password
from app.domains.data_source import service as datasource_service


class TestDatasourceAPI:
    """测试 /api/datasource 路由"""

    def test_list_datasources_empty(self, client):
        """空数据源列表应返回 []"""
        resp = client.get("/api/datasource")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_datasource(self, client):
        """创建数据源"""
        payload = {
            "name": "MySQL 生产库",
            "db_type": "mysql",
            "host": "192.168.1.10",
            "port": 3306,
            "database_name": "production",
            "username": "admin",
            "password": "secret123",
        }
        resp = client.post("/api/datasource", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "MySQL 生产库"
        assert data["db_type"] == "mysql"
        assert data["host"] == "192.168.1.10"
        assert data["port"] == 3306
        assert data["dialect"] == "mysql"
        assert data["driver"] == "pymysql"
        assert data["id"] is not None
        # 密码不应返回
        assert "password" not in data
        assert "password_enc" not in data

    def test_get_datasource(self, client):
        """获取单个数据源详情"""
        # 先创建
        payload = {
            "name": "Test DB",
            "db_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database_name": "test",
            "username": "user",
            "password": "pass",
        }
        created = client.post("/api/datasource", json=payload).json()

        resp = client.get(f"/api/datasource/{created['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test DB"

    def test_get_datasource_not_found(self, client):
        """获取不存在的数据源应返回 404"""
        resp = client.get("/api/datasource/99999")
        assert resp.status_code == 404

    def test_update_datasource(self, client):
        """更新数据源"""
        payload = {
            "name": "Old Name",
            "db_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database_name": "db",
            "username": "user",
            "password": "pass",
        }
        created = client.post("/api/datasource", json=payload).json()

        resp = client.put(
            f"/api/datasource/{created['id']}",
            json={"name": "New Name", "host": "newhost"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["host"] == "newhost"
        assert data["port"] == 5432  # 未修改字段保持原值

    def test_delete_datasource(self, client):
        """删除数据源"""
        payload = {
            "name": "To Delete",
            "db_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database_name": "db",
            "username": "user",
            "password": "pass",
        }
        created = client.post("/api/datasource", json=payload).json()

        resp = client.delete(f"/api/datasource/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 确认已删除
        resp = client.get(f"/api/datasource/{created['id']}")
        assert resp.status_code == 404

    def test_list_datasources_with_data(self, client):
        """创建后列表应包含数据"""
        for i in range(3):
            client.post(
                "/api/datasource",
                json={
                    "name": f"DB {i}",
                    "db_type": "postgres",
                    "host": "localhost",
                    "port": 5432,
                    "database_name": f"db{i}",
                    "username": "user",
                    "password": "pass",
                },
            )

        resp = client.get("/api/datasource")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        # 默认按 id desc 排序
        assert data[0]["name"] == "DB 2"

    def test_list_datasource_capabilities(self, client):
        """能力接口应返回已注册的数据源类型。"""
        resp = client.get("/api/datasource/capabilities")
        assert resp.status_code == 200
        items = resp.json()
        db_types = {item["db_type"] for item in items}
        assert {"mysql", "doris", "postgres", "sqlite", "oracle", "hive"}.issubset(db_types)
        doris = next(item for item in items if item["db_type"] == "doris")
        assert doris["dialect"] == "mysql"
        assert doris["driver"] == "pymysql"
        assert doris["default_port"] == 9030
        sqlite = next(item for item in items if item["db_type"] == "sqlite")
        assert sqlite["driver_status"] == "builtin"
        oracle = next(item for item in items if item["db_type"] == "oracle")
        assert oracle["driver_module"] == "oracledb"
        assert oracle["driver_status"] in {"installed", "missing"}
        if oracle["driver_status"] == "missing":
            assert "wheelhouse" in oracle["install_hint"]

    def test_test_connection_returns_driver_missing_diagnostic(self, client, monkeypatch):
        """可选驱动缺失时连接测试返回结构化诊断，不抛 500。"""
        from app.domains.data_source import service as datasource_service

        monkeypatch.setattr(
            datasource_service.ADAPTERS["oracle"],
            "driver_available",
            lambda: False,
        )
        created = client.post(
            "/api/datasource",
            json={
                "name": "Oracle",
                "db_type": "oracle",
                "host": "127.0.0.1",
                "port": 1521,
                "database_name": "ORCLPDB1",
                "username": "user",
                "password": "pass",
                "connection_options": {"service_name": "ORCLPDB1"},
            },
        ).json()

        resp = client.post(f"/api/datasource/{created['id']}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["code"] == "DRIVER_MISSING"
        assert data["diagnostic"]["category"] == "driver"

    def test_create_doris_datasource_normalizes_execution_dialect(self, client):
        """Doris 对外保持 db_type=doris，但执行方言由服务端固定为 mysql。"""
        resp = client.post(
            "/api/datasource",
            json={
                "name": "Doris",
                "db_type": "doris",
                "host": "127.0.0.1",
                "port": 0,
                "database_name": "demo",
                "username": "user",
                "password": "pass",
                "dialect": "doris",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["db_type"] == "doris"
        assert data["dialect"] == "mysql"
        assert data["driver"] == "pymysql"
        assert data["port"] == 9030

    def test_update_doris_datasource_rejects_stale_dialect_on_partial_update(self, client):
        """只更新 dialect 时也结合持久化 db_type，避免 Doris 被脏写回 doris 方言。"""
        created = client.post(
            "/api/datasource",
            json={
                "name": "Doris",
                "db_type": "doris",
                "host": "127.0.0.1",
                "port": 9030,
                "database_name": "demo",
                "username": "user",
                "password": "pass",
            },
        ).json()

        resp = client.put(f"/api/datasource/{created['id']}", json={"dialect": "doris"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["db_type"] == "doris"
        assert data["dialect"] == "mysql"


def test_build_datasource_context_normalizes_doris_stale_dialect():
    """共享 datasource context 兜底历史脏数据：Doris 执行 dialect 必须是 mysql。"""
    ds = Datasource(
        id=7,
        name="Doris",
        db_type="doris",
        dialect="doris",
        driver="pymysql",
        host="127.0.0.1",
        port=9030,
        database_name="demo",
        username="user",
        password_enc=encrypt_password("pass"),
        query_timeout_seconds=45,
    )

    context = datasource_service.build_datasource_context(ds, allowed_tables=["orders"])

    assert context["datasource_id"] == 7
    assert context["db_type"] == "doris"
    assert context["dialect"] == "mysql"
    assert context["allowed_tables"] == ["orders"]
    assert context["query_timeout_seconds"] == 45


def test_datasource_capability_migration_backfills_doris_defaults():
    """历史 datasource 能力字段迁移也要把 Doris 回填为 MySQL 执行方言。"""
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "d2e3f4a5b6c7_add_datasource_capability_fields.py"
    )
    spec = importlib.util.spec_from_file_location("datasource_capability_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.CAPABILITY_DEFAULTS["doris"] == ("mysql", "pymysql", None)


def test_doris_adapter_builds_mysql_compatible_url_and_timeout(monkeypatch):
    """Doris 适配器复用 mysql+pymysql URL 和 connect_timeout。"""
    ds = Datasource(
        name="Doris",
        db_type="doris",
        host="doris.local",
        port=9030,
        database_name="warehouse",
        username="ken",
        password_enc=encrypt_password("secret"),
        connect_timeout_seconds=12,
    )
    adapter = datasource_service.ADAPTERS["doris"]
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "engine"

    monkeypatch.setattr("app.domains.data_source.adapters.base.create_engine", fake_create_engine)
    monkeypatch.setattr(adapter, "driver_available", lambda: True)

    engine = adapter.create_engine(ds)

    assert engine == "engine"
    assert captured["url"] == "mysql+pymysql://ken:secret@doris.local:9030/warehouse"
    assert captured["kwargs"]["connect_args"]["connect_timeout"] == 12


def test_oracle_adapter_build_url_prefers_explicit_service_name_over_sid():
    """Oracle 同时配置 service_name/sid 时按明确 service_name 生成 URL，避免歧义。"""
    ds = Datasource(
        name="Oracle",
        db_type="oracle",
        host="oracle.local",
        port=1521,
        database_name="fallback",
        username="ken",
        password_enc=encrypt_password("secret"),
        connection_options={"service_name": "ORCLPDB1", "sid": "ORCL"},
    )

    url = datasource_service.ADAPTERS["oracle"].build_url(ds)

    assert url == "oracle+oracledb://ken:secret@oracle.local:1521/?service_name=ORCLPDB1"


def test_oracle_adapter_build_url_supports_sid_without_service_name():
    """Oracle 仅配置 sid 时使用 SQLAlchemy oracledb SID 查询参数形式。"""
    ds = Datasource(
        name="Oracle",
        db_type="oracle",
        host="oracle.local",
        port=1521,
        database_name="fallback",
        username="ken",
        password_enc=encrypt_password("secret"),
        connection_options={"sid": "ORCL"},
    )

    url = datasource_service.ADAPTERS["oracle"].build_url(ds)

    assert url == "oracle+oracledb://ken:secret@oracle.local:1521/?sid=ORCL"


def test_preview_table_uses_mysql_protocol_sql_for_doris(monkeypatch):
    """Doris 表预览使用 MySQL 协议 SQL，并用 Schema 限定跨库表名。"""
    captured = {}

    class FakeResult:
        def keys(self):
            return ["id"]

        def fetchall(self):
            return [(1,)]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            captured["disposed"] = True

    ds = Datasource(
        name="Doris",
        db_type="doris",
        host="127.0.0.1",
        port=9030,
        database_name="demo",
        username="user",
        password_enc=encrypt_password("pass"),
    )
    monkeypatch.setattr(datasource_service, "create_engine_for_datasource", lambda _ds: FakeEngine())

    result = datasource_service.preview_table(ds, "edmadmin", "orders", 10)

    assert captured["sql"] == "SELECT * FROM `edmadmin`.`orders` LIMIT :limit"
    assert captured["params"] == {"limit": 10}
    assert captured["disposed"] is True
    assert result == {"columns": ["id"], "rows": [{"id": 1}]}


def test_sync_tables_forwards_explicit_schema(client, sample_datasource, monkeypatch):
    """DDL 同步接口把数据集选择的 Schema 原样传给数据源服务。"""

    captured = {}

    def fake_sync(ds, schema_name=None):
        captured["datasource_id"] = ds.id
        captured["schema_name"] = schema_name
        return {"tables": [], "synced_at": "2026-07-16T12:41:00", "skipped": [], "errors": []}

    monkeypatch.setattr("app.api.datasource.sync_source_tables", fake_sync)

    resp = client.post(f"/api/datasource/{sample_datasource.id}/sync-tables?schema=archive")

    assert resp.status_code == 200
    assert captured == {"datasource_id": sample_datasource.id, "schema_name": "archive"}


def test_sync_source_tables_bulk_samples_once_per_table(sample_datasource, monkeypatch):
    """宽表同步必须按表批量采样，不能为每个字段重复连接数据源。"""

    adapter = datasource_service.get_adapter("sqlite")
    monkeypatch.setattr(
        adapter,
        "get_schema",
        lambda _ds, schema_name=None: [
            {
                "name": "orders",
                "schema_name": schema_name,
                "comment": "订单表",
                "row_count": 2,
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False},
                    {"name": "region", "type": "TEXT", "nullable": True},
                ],
            }
        ],
    )
    calls = []

    def fake_bulk_sample(_ds, schema, table, columns):
        calls.append((schema, table, columns))
        return {"id": ["1", "2"], "region": ["华东"]}

    monkeypatch.setattr(adapter, "sample_table_values", fake_bulk_sample)

    result = adapter.sync_source_tables(sample_datasource, schema_name="main")

    assert calls == [("main", "orders", ["id", "region"])]
    assert result["tables"][0]["columns"][0]["sample_values"] == ["1", "2"]
    assert result["tables"][0]["columns"][1]["sample_values"] == ["华东"]


def test_preview_table_uses_oracle_fetch_first_and_schema_qualifier(monkeypatch):
    """Oracle 表预览使用 schema 限定和 FETCH FIRST，避免误走 LIMIT 分支。"""
    captured = {}

    class FakeResult:
        def keys(self):
            return ["ID"]

        def fetchall(self):
            return [(1,)]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            captured["disposed"] = True

    ds = Datasource(
        name="Oracle",
        db_type="oracle",
        host="127.0.0.1",
        port=1521,
        database_name="ORCLPDB1",
        username="user",
        password_enc=encrypt_password("pass"),
    )
    monkeypatch.setattr(datasource_service, "create_engine_for_datasource", lambda _ds: FakeEngine())

    result = datasource_service.preview_table(ds, "EDMADMIN", "ORDERS", 10)

    assert captured["sql"] == 'SELECT * FROM "EDMADMIN"."ORDERS" FETCH FIRST :limit ROWS ONLY'
    assert captured["params"] == {"limit": 10}
    assert captured["disposed"] is True
    assert result == {"columns": ["ID"], "rows": [{"ID": 1}]}
