from app.services.subagent_planning.asset_recall import (
    build_candidate_assets_from_context,
    recall_candidate_assets,
)


def test_build_candidate_assets_from_structured_context_keeps_six_types():
    context = {
        "schema_structured": {
            "dataset_name": "生产日志",
            "metrics": [{"id": 1, "name": "日志数量", "description": "日志总数"}],
            "dimensions": [{"id": 2, "name": "用户", "expr": "user_name"}],
            "terms": [{"id": 3, "name": "失败日志", "display_name": "失败日志", "aliases": ["异常日志"]}],
            "blueprints": [
                {
                    "id": 4,
                    "name": "个人日报查询",
                    "description": "查询个人日报",
                    "when_to_use": "用户询问个人日报时使用",
                    "implementation_type": "sql_template",
                    "parameters": [{"name": "user_name", "required": True}],
                    "sql_template": "select * from daily_report where user_name = :user_name",
                }
            ],
            "fields": [
                {
                    "table_name": "user_logs",
                    "column_name": "created_at",
                    "name": "created_at",
                    "data_type": "datetime",
                    "semantic": "日志创建时间",
                }
            ],
            "tables_json": {
                "selected_tables": [
                    {"name": "user_logs", "description": "用户日志表"},
                ]
            },
        },
        "dataset_context_debug": {"dataset_id": 10},
    }

    assets = build_candidate_assets_from_context(
        question="查询10条用户日志",
        dataset_id=10,
        context=context,
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    types = {asset["asset_type"] for asset in assets["assets"]}

    assert {"blueprint", "metric", "dimension", "term", "field", "table"}.issubset(types)
    assert assets["summary"]["blueprint_count"] == 1
    assert assets["summary"]["field_count"] == 1
    assert assets["recall_debug"]["schema_source"] == "lightweight_schema_recall"


def test_recall_candidate_assets_uses_lightweight_token_budget(db_session, monkeypatch):
    captured = {}

    def fake_build_context(db, dataset_id, *, question, token_budget, blueprint_context="", matched_assets=None):
        captured["dataset_id"] = dataset_id
        captured["question"] = question
        captured["token_budget"] = token_budget
        return {
            "schema_structured": {
                "dataset_name": "生产日志",
                "metrics": [],
                "dimensions": [],
                "terms": [],
                "blueprints": [],
                "fields": [],
                "tables_json": {},
            },
            "dataset_context_debug": {"dataset_id": dataset_id},
        }

    monkeypatch.setattr(
        "app.services.subagent_planning.asset_recall.build_dataset_query_context",
        fake_build_context,
    )

    result = recall_candidate_assets(
        db_session,
        dataset_id=10,
        question="查询10条用户日志",
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    assert captured == {"dataset_id": 10, "question": "查询10条用户日志", "token_budget": 2500}
    assert result["summary"]["blueprint_count"] == 0


def test_table_assets_fallback_to_field_table_names_when_tables_json_empty():
    context = {
        "schema_structured": {
            "tables_json": {},
            "fields": [
                {"table_name": "user_logs", "column_name": "id"},
                {"table_name": "user_logs", "column_name": "created_at"},
            ],
        }
    }

    result = build_candidate_assets_from_context(
        question="查询用户日志",
        dataset_id=10,
        context=context,
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    tables = [asset for asset in result["assets"] if asset["asset_type"] == "table"]

    assert [table["name"] for table in tables] == ["user_logs"]
    assert tables[0]["metadata"] == {"table_name": "user_logs", "source": "fields"}


def test_malformed_structured_entries_are_skipped():
    context = {
        "schema_structured": {
            "blueprints": [None, {}, "bad"],
            "metrics": [None, {}],
            "dimensions": ["bad"],
            "terms": [{}],
            "fields": [{}, {"table_name": "user_logs"}],
        }
    }

    result = build_candidate_assets_from_context(
        question="查询用户日志",
        dataset_id=10,
        context=context,
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    assert all(asset["asset_id"] for asset in result["assets"])
    assert all(asset["name"] for asset in result["assets"])
    assert not any(asset["asset_id"] == "table:None.column:None" for asset in result["assets"])


def test_realistic_display_names_synonyms_and_trigger_examples_score():
    context = {
        "schema_structured": {
            "blueprints": [
                {"id": 1, "name": "日报", "trigger_examples": ["查询个人工作日志"]},
            ],
            "metrics": [
                {"id": 2, "name": "log_count", "display_name": "日志数量", "synonyms": ["记录数"]},
            ],
            "dimensions": [],
            "terms": [],
            "fields": [
                {
                    "table_name": "user_logs",
                    "column_name": "status",
                    "display_name": "日志状态",
                    "synonyms": ["失败状态"],
                }
            ],
            "tables_json": {},
        }
    }

    result = build_candidate_assets_from_context(
        question="最近10条失败状态日志",
        dataset_id=10,
        context=context,
        manifest_version="v1",
        bound_schema_version="schema-1",
    )

    scored = [asset for asset in result["assets"] if asset["asset_type"] in {"field", "blueprint", "metric"}]

    assert any(asset["confidence"] > 0 for asset in scored)
    assert any(asset["match_signals"] for asset in scored)
