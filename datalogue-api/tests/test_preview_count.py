# ============================================================
# File Name   : test_preview_count.py
# Description:
#   preview_dataset_sql 前置 COUNT(*) 与总量回写回归测试。
#
# Responsibilities:
#   - 验证执行明细 SQL 前会先执行 COUNT(*)。
#   - 验证总量超过 10,000 时只取前 10,000 行，但 row_count 回写真实总量。
#   - 验证 COUNT 失败时会降级为直接执行。
#
# Author      : yangkai
# Created On  : 2026-07-10
# ============================================================

from types import SimpleNamespace

from app.core.models.datasource import Datasource
from app.core.models.dataset import DatasetSourceTable, SemanticDataset, SourceColumn, SourceTable
from app.domains.query_execution.preview import preview_dataset_sql


class _FakeResultProxy:
    """模拟 SQLAlchemy ResultProxy，支持 keys() 和可迭代行。"""

    def __init__(self, keys, rows):
        self._keys = keys
        self._rows = rows

    def keys(self):
        return self._keys

    def __iter__(self):
        for row in self._rows:
            yield row

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConnection:
    """模拟数据库连接；根据 SQL 内容返回 COUNT 或明细结果。"""

    def __init__(self, count_value, detail_rows, detail_keys):
        self.count_value = count_value
        self.detail_rows = detail_rows
        self.detail_keys = detail_keys

    def execute(self, sql, parameters=None):
        text = str(sql)
        if "COUNT(*)" in text.upper():
            return _FakeResultProxy(["count"], [(self.count_value,)])
        return _FakeResultProxy(self.detail_keys, self.detail_rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeEngine:
    def __init__(self, connection):
        self._connection = connection

    def connect(self):
        return self._connection

    def dispose(self):
        pass


def _add_dataset_with_selected_table(db_session, *, query_constraints=None):
    ds = Datasource(
        name="测试数据源",
        db_type="postgres",
        dialect="postgres",
        host="localhost",
        port=5432,
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
        query_constraints=query_constraints
        or {"enabled": True, "default_limit": 10000, "max_limit": 10000},
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


def _row_mapping(row):
    return SimpleNamespace(_mapping={key: value for key, value in zip(row._keys, row)})


def _make_connection(count_value, detail_rows, detail_keys):
    # 把明细行包装成有 _mapping 属性的对象
    wrapped_detail_rows = []
    for values in detail_rows:
        mapping = {key: value for key, value in zip(detail_keys, values)}
        wrapped_detail_rows.append(SimpleNamespace(_mapping=mapping))
    return _FakeConnection(count_value, wrapped_detail_rows, detail_keys)


def test_preview_returns_visible_and_total_row_count_when_under_cap(monkeypatch, db_session):
    """未截断时，实际返回行数和未限制前总量一致。"""
    _ds, dataset = _add_dataset_with_selected_table(db_session)

    connection = _make_connection(
        count_value=150,
        detail_rows=[(i,) for i in range(150)],
        detail_keys=["order_id"],
    )
    monkeypatch.setattr(
        "app.domains.query_execution.preview.create_engine_for_datasource",
        lambda _datasource: _FakeEngine(connection),
    )

    result = preview_dataset_sql(db_session, dataset=dataset, sql="SELECT order_id FROM orders")

    assert result["error"] is None
    assert result["row_count"] == 150
    assert result["total_row_count"] == 150
    assert len(result["rows"]) == 150
    assert "LIMIT 10000" in result["sql"]


def test_preview_clamps_to_10000_when_total_exceeds_cap(monkeypatch, db_session):
    """总量超过 10,000 时，row_count 记录实际结果，total_row_count 记录候选总量。"""
    _ds, dataset = _add_dataset_with_selected_table(db_session)

    connection = _make_connection(
        count_value=25000,
        detail_rows=[(i,) for i in range(10000)],
        detail_keys=["order_id"],
    )
    monkeypatch.setattr(
        "app.domains.query_execution.preview.create_engine_for_datasource",
        lambda _datasource: _FakeEngine(connection),
    )

    result = preview_dataset_sql(db_session, dataset=dataset, sql="SELECT order_id FROM orders")

    assert result["error"] is None
    assert result["row_count"] == 10000
    assert result["total_row_count"] == 25000
    assert len(result["rows"]) == 10000


def test_preview_preserves_smaller_explicit_limit_when_total_exceeds_cap(
    monkeypatch, db_session
):
    """Top-N 查询的显式 LIMIT 不能被预览上限反向放大。"""
    _ds, dataset = _add_dataset_with_selected_table(db_session)

    connection = _make_connection(
        count_value=2774751,
        detail_rows=[(48387,)],
        detail_keys=["oil_prod_mon"],
    )
    monkeypatch.setattr(
        "app.domains.query_execution.preview.create_engine_for_datasource",
        lambda _datasource: _FakeEngine(connection),
    )

    result = preview_dataset_sql(
        db_session,
        dataset=dataset,
        sql="SELECT oil_prod_mon FROM orders ORDER BY oil_prod_mon DESC LIMIT 1",
    )

    assert result["error"] is None
    assert result["row_count"] == 1
    assert result["total_row_count"] == 2774751
    assert len(result["rows"]) == 1
    assert "LIMIT 1" in result["sql"]


def test_preview_falls_back_when_count_fails(monkeypatch, db_session):
    """COUNT 执行失败时降级为直接执行，row_count 使用实际返回行数。"""
    _ds, dataset = _add_dataset_with_selected_table(db_session)

    class _FailingCountConnection:
        def execute(self, sql, parameters=None):
            text = str(sql)
            if "COUNT(*)" in text.upper():
                raise RuntimeError("count failed")
            keys = ["order_id"]
            rows = [
                SimpleNamespace(_mapping={"order_id": 1}),
                SimpleNamespace(_mapping={"order_id": 2}),
                SimpleNamespace(_mapping={"order_id": 3}),
            ]
            return _FakeResultProxy(keys, rows)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        "app.domains.query_execution.preview.create_engine_for_datasource",
        lambda _datasource: _FakeEngine(_FailingCountConnection()),
    )

    result = preview_dataset_sql(db_session, dataset=dataset, sql="SELECT order_id FROM orders")

    assert result["error"] is None
    assert result["row_count"] == 3
    assert result["total_row_count"] == 3
    assert len(result["rows"]) == 3
