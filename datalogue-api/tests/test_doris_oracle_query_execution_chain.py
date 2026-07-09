# ============================================================
# File Name   : test_doris_oracle_query_execution_chain.py
# Description:
#   Doris/Oracle 数据源问数链路的 query_execution 回归测试。
# ============================================================

from types import SimpleNamespace

from app.core.models.datasource import Datasource
from app.core.models.dataset import DatasetSourceTable, SemanticDataset, SourceColumn, SourceTable
from app.domains.bi.agent.runtime_context import build_bi_runtime_context
from app.domains.query_execution.preview import preview_dataset_sql
from app.services import analysis_blueprint


class _FakeContext:
    query_executor = None


class _FakeBridge:
    def __init__(self):
        self.toolkit = SimpleNamespace(context=_FakeContext())


def _add_dataset_with_selected_table(db_session, *, db_type="doris", dialect="doris"):
    ds = Datasource(
        name="测试数据源",
        db_type=db_type,
        dialect=dialect,
        host="localhost",
        port=9030,
        database_name="demo",
        username="user",
        password_enc="enc",
        status="connected",
    )
    db_session.add(ds)
    db_session.flush()
    dataset = SemanticDataset(
        name="测试数据集",
        datasource_id=ds.id,
        tables_json={},
        status="active",
        query_constraints={"enabled": True, "default_limit": 10, "max_limit": 100},
    )
    db_session.add(dataset)
    db_session.flush()
    table = SourceTable(
        datasource_id=ds.id,
        schema_name="public",
        table_name="orders",
        status="active",
    )
    db_session.add(table)
    db_session.flush()
    db_session.add(SourceColumn(table_id=table.id, column_name="order_id", ordinal_position=1))
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.commit()
    db_session.refresh(ds)
    db_session.refresh(dataset)
    return ds, dataset


def test_build_bi_runtime_context_normalizes_stale_doris_dialect(db_session):
    _ds, dataset = _add_dataset_with_selected_table(db_session, db_type="doris", dialect="doris")

    runtime_context = build_bi_runtime_context(
        db_session,
        dataset_id=dataset.id,
        question="查看订单",
        bridge=_FakeBridge(),
    )

    kwargs = runtime_context["session_kwargs"]
    assert kwargs["dialect"] == "mysql"
    assert kwargs["current_datasource_dialect"] == "mysql"
    assert kwargs["allowed_tables"] == ["orders", "public.orders"]


def test_preview_dataset_sql_normalizes_doris_before_guard(monkeypatch, db_session):
    _ds, dataset = _add_dataset_with_selected_table(db_session, db_type="doris", dialect="doris")
    captured = {}

    def fake_guard(sql, *, dialect, query_constraints, allowed_tables):
        captured["dialect"] = dialect
        captured["allowed_tables"] = allowed_tables
        return SimpleNamespace(
            ok=False,
            normalized_sql=None,
            code="STOP_BEFORE_ENGINE",
            error="stop",
            keyword=None,
            warnings=[],
        )

    monkeypatch.setattr("app.domains.query_execution.preview.guard_readonly_sql", fake_guard)

    result = preview_dataset_sql(db_session, dataset=dataset, sql="SELECT order_id FROM orders")

    assert result["error"] == "stop"
    assert captured["dialect"] == "mysql"
    assert captured["allowed_tables"] == ["orders", "public.orders"]


def test_analysis_blueprint_timeout_treats_stale_doris_as_mysql(monkeypatch):
    datasource = Datasource(
        name="Doris stale",
        db_type="doris",
        dialect="doris",
        host="localhost",
        port=9030,
        database_name="demo",
        username="user",
        password_enc="enc",
    )
    executed = []

    class FakeConn:
        def execute(self, stmt):
            executed.append(str(stmt))

    cleanup = analysis_blueprint._apply_database_timeout(FakeConn(), datasource, 7)

    assert cleanup is None
    assert executed == ["SET SESSION max_execution_time = 7000"]
