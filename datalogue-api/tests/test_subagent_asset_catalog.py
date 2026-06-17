from app.services.subagent_planning.asset_catalog import (
    ALLOWED_CATALOG_ASSET_TYPES,
    build_allowed_asset_scope,
    project_lightweight_asset_catalog,
)


def _asset(asset_type, asset_id, *, metadata=None, confidence=0.8):
    return {
        "asset_type": asset_type,
        "asset_id": asset_id,
        "name": str(asset_id),
        "display_name": f"{asset_id} 展示名",
        "source": "schema",
        "confidence": confidence,
        "match_signals": [
            {"type": "exact", "value": str(asset_id), "score": confidence},
            {"type": "contains", "value": "额外信号", "score": 0.1},
        ],
        "metadata": metadata or {},
    }


def test_project_lightweight_asset_catalog_keeps_only_planner_catalog_types():
    raw = {
        "dataset_id": 10,
        "assets": [
            _asset(
                "table",
                "plan_task_daily_record",
                metadata={"comment": "任务日报表", "fields": [{"name": "id"}]},
                confidence=0.95,
            ),
            _asset(
                "metric",
                "task_count",
                metadata={"description": "任务数", "expr": "count(*)"},
                confidence=0.8,
            ),
            _asset("dimension", "department", metadata={"description": "部门"}, confidence=0.7),
            _asset(
                "blueprint",
                "daily_report",
                metadata={"description": "日报分析", "sql": "select 1"},
                confidence=0.6,
            ),
            _asset("field", "table:t.column:id", metadata={"column_comment": "主键"}, confidence=0.99),
            _asset("term", "用户", metadata={"description": "业务术语"}, confidence=0.98),
        ],
        "recall_debug": {"manifest_version": "manifest-v1", "bound_schema_version": "schema-v1"},
    }

    projected = project_lightweight_asset_catalog(raw)

    assert [asset["asset_type"] for asset in projected["assets"]] == [
        "table",
        "metric",
        "dimension",
        "blueprint",
    ]
    assert [asset["confidence"] for asset in projected["assets"]] == [0.95, 0.8, 0.7, 0.6]
    table_asset = projected["assets"][0]
    assert table_asset["description"] == "任务日报表"
    assert table_asset["schema_version"] == "schema-v1"
    assert table_asset["manifest_version"] == "manifest-v1"
    assert "fields" not in table_asset
    assert "metadata" not in table_asset
    assert len(table_asset["match_signals"]) == 2


def test_project_lightweight_asset_catalog_limits_match_signals():
    raw = {
        "assets": [
            _asset(
                "table",
                "wide_table",
                metadata={"comment": "宽表"},
                confidence=0.9,
            )
        ]
    }
    raw["assets"][0]["match_signals"] = [
        {"type": "exact", "value": "a", "score": 0.9},
        {"type": "contains", "value": "b", "score": 0.7},
        {"type": "synonym", "value": "c", "score": 0.6},
        {"type": "table_context", "value": "d", "score": 0.5},
    ]

    projected = project_lightweight_asset_catalog(raw, max_signals_per_asset=3)

    assert len(projected["assets"][0]["match_signals"]) == 3


def test_project_lightweight_asset_catalog_does_not_leak_expr_or_sql_text():
    raw = {
        "assets": [
            _asset("metric", "task_count", metadata={"expr": "count(*)"}, confidence=0.8),
            _asset(
                "blueprint",
                "daily_report",
                metadata={"sql": "select * from payroll"},
                confidence=0.7,
            ),
        ]
    }

    projected = project_lightweight_asset_catalog(raw)

    assert [asset["description"] for asset in projected["assets"]] == [None, None]
    catalog_text = str(projected)
    assert "count(*)" not in catalog_text
    assert "select * from payroll" not in catalog_text


def test_build_allowed_asset_scope_uses_type_and_asset_id():
    catalog = {
        "assets": [
            {"asset_type": "table", "asset_id": "plan_task_daily_record"},
            {"asset_type": "metric", "asset_id": 12},
        ]
    }

    scope = build_allowed_asset_scope(catalog)

    assert scope == {("table", "plan_task_daily_record"), ("metric", "12")}
    assert ALLOWED_CATALOG_ASSET_TYPES == {"metric", "dimension", "table", "blueprint"}
