# ============================================================
# File Name   : test_column_labels.py
# Description:
#   查询结果列名展示映射测试。
#
# Responsibilities:
#   - 验证指标、维度和字段的语义化展示名。
#   - 覆盖未知列的兜底展示逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""build_column_labels 单元测试 — 用内存 SQLite 验证维度/指标/字段标注映射规则。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import (
    SemanticDataset,
    SemanticDimension,
    SemanticMetric,
    Datasource,
    SourceTable,
    SourceColumn,
    DatasetSourceTable,
)
from app.models.base import TimestampMixin
from app.utils.column_labels import build_column_labels


@pytest.fixture
def db():
    """内存 SQLite + 全表创建 + 关闭时清理。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_dataset_with_semantics(db):
    """构造一个带 1 个数据源、1 个数据集、2 维度 + 1 指标的最小场景。"""
    ds_src = Datasource(name="t", db_type="mysql", host="x", port=3306,
                        database_name="testdb", username="u", password_enc="x")
    db.add(ds_src)
    db.flush()
    ds = SemanticDataset(name="d1", datasource_id=ds_src.id)
    db.add(ds)
    db.flush()
    db.add_all([
        SemanticDimension(dataset_id=ds.id, name="dim_person_name", display_name="姓名",
                          column_name="person_name", table_name="t_user"),
        SemanticDimension(dataset_id=ds.id, name="dim_order_status", display_name="订单状态",
                          column_name="order_status", table_name="t_order"),
        SemanticMetric(dataset_id=ds.id, name="refund_amt", display_name="退款金额",
                       expr="SUM(refund_apply_amt)", table_name="t_refund",
                       time_field="apply_time"),
    ])
    db.commit()
    return ds.id


class TestBuildColumnLabels:
    """验证映射规则：维度 column_name → display_name；指标 name → display_name。"""

    def test_none_dataset_id_returns_empty(self, db):
        assert build_column_labels(db, None) == {}

    def test_invalid_dataset_id_returns_empty(self, db):
        assert build_column_labels(db, 99999) == {}

    def test_dimension_column_mapped(self, db):
        """维度：DDL 列名 person_name → 姓名。"""
        ds_id = _make_dataset_with_semantics(db)
        labels = build_column_labels(db, ds_id)
        assert labels["person_name"] == "姓名"
        assert labels["order_status"] == "订单状态"

    def test_metric_name_mapped(self, db):
        """指标：语义层 name refund_amt → 退款金额。"""
        ds_id = _make_dataset_with_semantics(db)
        labels = build_column_labels(db, ds_id)
        assert labels["refund_amt"] == "退款金额"

    def test_ddl_columns_not_in_semantic_layer_unchanged(self, db):
        """未在语义层中的 DDL 列不应出现在映射里（前端用 fallback 显示 DDL 名）。"""
        ds_id = _make_dataset_with_semantics(db)
        labels = build_column_labels(db, ds_id)
        assert "rzrq" not in labels
        assert "account" not in labels

    def test_dataset_with_no_metrics_or_dims(self, db):
        """空数据集（无指标无维度）→ 空映射，函数不能崩。"""
        ds_src = Datasource(name="t", db_type="mysql", host="x", port=3306,
                            database_name="testdb", username="u", password_enc="x")
        db.add(ds_src)
        db.flush()
        ds = SemanticDataset(name="empty", datasource_id=ds_src.id)
        db.add(ds)
        db.commit()
        assert build_column_labels(db, ds.id) == {}

    # ── 字段标注 (SourceColumn.effective_desc) 兜底映射 ─────────

    def _make_dataset_with_annotated_source_cols(self, db):
        """构造带 AI 标注 source_column 的数据集。"""
        ds_src = Datasource(name="t", db_type="mysql", host="x", port=3306,
                            database_name="testdb", username="u", password_enc="x")
        db.add(ds_src)
        db.flush()
        ds = SemanticDataset(name="d2", datasource_id=ds_src.id)
        db.add(ds)
        db.flush()
        st = SourceTable(datasource_id=ds_src.id, schema_name="public",
                         table_name="t_user", status="active", desc_source="unknown")
        db.add(st)
        db.flush()
        # 1) AI 标注的有意义描述 → 应入映射
        db.add(SourceColumn(table_id=st.id, column_name="person_name",
                            data_type="varchar", effective_desc="姓名",
                            desc_source="ai", ordinal_position=1))
        # 2) 用户标注覆盖 AI → 应入映射
        db.add(SourceColumn(table_id=st.id, column_name="order_status",
                            data_type="int", effective_desc="订单状态",
                            desc_source="user", ordinal_position=2))
        # 3) DB 注释 → 应入映射
        db.add(SourceColumn(table_id=st.id, column_name="create_time",
                            data_type="datetime", effective_desc="创建时间",
                            desc_source="db_comment", ordinal_position=3))
        # 4) unknown 状态 → 不入映射（无意义）
        db.add(SourceColumn(table_id=st.id, column_name="raw_blob",
                            data_type="text", effective_desc="未识别",
                            desc_source="unknown", ordinal_position=4))
        # 5) fallback 兜底 → 不入映射（占位文案）
        db.add(SourceColumn(table_id=st.id, column_name="noise_col",
                            data_type="int", effective_desc="t_user.noise_col",
                            desc_source="fallback", ordinal_position=5))
        db.flush()
        # 关联 source_table 到 dataset
        db.add(DatasetSourceTable(dataset_id=ds.id, source_table_id=st.id))
        db.commit()
        return ds.id

    def test_source_column_ai_desc_mapped(self, db):
        """AI 标注的字段描述应被映射。"""
        ds_id = self._make_dataset_with_annotated_source_cols(db)
        labels = build_column_labels(db, ds_id)
        assert labels["person_name"] == "姓名"

    def test_source_column_user_desc_mapped(self, db):
        """用户标注的字段描述应被映射。"""
        ds_id = self._make_dataset_with_annotated_source_cols(db)
        labels = build_column_labels(db, ds_id)
        assert labels["order_status"] == "订单状态"

    def test_source_column_db_comment_mapped(self, db):
        """DB 注释的字段描述应被映射。"""
        ds_id = self._make_dataset_with_annotated_source_cols(db)
        labels = build_column_labels(db, ds_id)
        assert labels["create_time"] == "创建时间"

    def test_source_column_unknown_or_fallback_excluded(self, db):
        """unknown / fallback 状态的描述不应被映射（避免脏数据）。"""
        ds_id = self._make_dataset_with_annotated_source_cols(db)
        labels = build_column_labels(db, ds_id)
        assert "raw_blob" not in labels
        assert "noise_col" not in labels

    def test_metric_overrides_source_column(self, db):
        """指标 display_name 应覆盖 source_column 的 effective_desc（最高优先）。"""
        ds_id = self._make_dataset_with_annotated_source_cols(db)
        ds = db.get(SemanticDataset, ds_id)
        # 假设 metric.name == 'person_name'（与 source_column 同名）
        db.add(SemanticMetric(dataset_id=ds.id, name="person_name",
                              display_name="员工姓名", expr="person_name",
                              table_name="t_user"))
        db.commit()
        labels = build_column_labels(db, ds_id)
        # 指标 display_name 应该赢
        assert labels["person_name"] == "员工姓名"

    def test_unselected_source_table_excluded(self, db):
        """未关联到数据集的 source_table 下的列不应被映射。"""
        # 主数据集
        ds_id = self._make_dataset_with_annotated_source_cols(db)
        # 额外建一个未被关联的 source_table + 标注
        ds = db.get(SemanticDataset, ds_id)
        st_extra = SourceTable(datasource_id=ds.datasource_id, schema_name="public",
                               table_name="t_extra", status="active", desc_source="unknown")
        db.add(st_extra)
        db.flush()
        db.add(SourceColumn(table_id=st_extra.id, column_name="secret",
                            data_type="text", effective_desc="秘密字段",
                            desc_source="ai", ordinal_position=1))
        db.commit()
        labels = build_column_labels(db, ds_id)
        # 未关联的表里的列不应进映射
        assert "secret" not in labels
