from app.services.subagent_planning.asset_detail import (
    AssetDetailRequest,
    AssetDetailService,
    validate_asset_detail_requests,
)


def _table_asset(field_count):
    fields = [
        {
            "table_name": "wide_table",
            "column_name": f"field_{index}",
            "data_type": "varchar",
            "column_comment": f"字段 {index}",
        }
        for index in range(field_count)
    ]
    fields[0]["column_name"] = "created_at"
    fields[0]["data_type"] = "datetime"
    fields[0]["column_comment"] = "创建时间"
    fields[1]["column_name"] = "user_id"
    fields[1]["column_comment"] = "用户ID"
    return {
        "asset_type": "table",
        "asset_id": "wide_table",
        "name": "wide_table",
        "metadata": {"table_name": "wide_table", "comment": "测试宽表"},
        "confidence": 0.9,
    }, fields


def test_validate_asset_detail_requests_rejects_assets_outside_scope():
    requests = [
        AssetDetailRequest(
            asset_type="table",
            asset_id="not_recalled",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="需要看字段",
        )
    ]
    results = validate_asset_detail_requests(requests, allowed_scope={("table", "wide_table")}, max_requests=5)
    assert results.valid_requests == []
    assert results.errors[0].error_code == "asset_not_in_recall_scope"


def test_table_full_schema_returns_full_for_normal_table():
    table_asset, fields = _table_asset(12)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        full_field_limit=120,
        compact_field_limit=300,
    )
    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="生成 SQL",
        )
    )
    assert result.coverage == "full"
    assert result.payload["field_count"] == 12
    assert result.payload["returned_field_count"] == 12
    assert len(result.payload["fields"]) == 12


def test_table_full_schema_returns_compacted_for_medium_wide_table():
    table_asset, fields = _table_asset(121)
    for field in fields:
        field["business_desc"] = "用于业务解释的字段说明"
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        full_field_limit=120,
        compact_field_limit=300,
    )
    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="生成 SQL",
        )
    )
    assert result.coverage == "full_compacted"
    assert result.payload["field_count"] == 121
    assert result.payload["returned_field_count"] == 121
    assert len(result.payload["fields"]) == 121
    assert "business_desc" not in result.payload["fields"][0]


def test_table_full_schema_returns_too_large_without_fields_for_wide_table():
    table_asset, fields = _table_asset(301)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        full_field_limit=120,
        compact_field_limit=300,
    )
    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="生成 SQL",
        )
    )
    assert result.coverage == "too_large"
    assert result.payload["field_count"] == 301
    assert result.payload["returned_field_count"] == 0
    assert result.payload["fields"] == []
    assert result.payload["available_detail_requests"] == ["field_search"]


def test_table_full_schema_fails_closed_when_asset_missing_from_candidates():
    secret_fields = [
        {
            "table_name": "secret_table",
            "column_name": "secret_col",
            "data_type": "varchar",
            "column_comment": "敏感字段",
        }
    ]
    service = AssetDetailService(
        candidate_assets={"assets": [], "context": {"schema_structured": {"fields": secret_fields}}},
    )
    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="secret_table",
            detail_level="full_schema",
            purpose="sql_generation",
            reason="生成 SQL",
        )
    )
    assert result.coverage == "empty"
    assert result.error_code == "asset_not_found"
    assert "asset_missing" in result.risk_flags
    assert "fields" not in result.payload
    assert "secret_col" not in str(result.payload)


def test_field_search_defaults_top_k_and_caps_to_maximum_with_boost():
    table_asset, fields = _table_asset(80)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        field_search_default_top_k=30,
        field_search_max_top_k=50,
    )
    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="field_search",
            purpose="sql_generation",
            reason="搜索字段",
            query="用户 时间 状态",
            top_k=99,
        )
    )
    assert result.coverage == "partial"
    assert result.payload["requested_top_k"] == 99
    assert result.payload["capped_top_k"] == 50
    assert result.payload["returned_count"] <= 50
    created_at = next(item for item in result.payload["fields"] if item["name"] == "created_at")
    assert created_at["boosted"] is True
    assert created_at["boost_reason"] == "time_field_candidate"
    assert "text_score" in created_at
    assert "final_score" in created_at


def test_field_search_returns_empty_when_query_has_no_textual_match():
    table_asset, fields = _table_asset(80)
    service = AssetDetailService(
        candidate_assets={"assets": [table_asset], "context": {"schema_structured": {"fields": fields}}},
        field_search_default_top_k=30,
        field_search_max_top_k=50,
    )
    result = service.get_detail(
        AssetDetailRequest(
            asset_type="table",
            asset_id="wide_table",
            detail_level="field_search",
            purpose="sql_generation",
            reason="搜索字段",
            query="完全无关",
        )
    )
    assert result.coverage == "empty"
    assert result.payload["returned_count"] == 0
    assert result.payload["fields"] == []
