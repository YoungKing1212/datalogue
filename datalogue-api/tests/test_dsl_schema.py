# ============================================================
# File Name   : test_dsl_schema.py
# Description:
#   NL2DSL v2 资产引用 Schema 测试。
#
# Responsibilities:
#   - 验证旧 DSL 到 v2 资产引用结构的兼容转换。
#   - 覆盖歧义和过滤字段资产引用的规范化行为。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from app.schemas.dsl import get_dsl_item_name, normalize_dsl


def test_normalize_legacy_dsl_to_asset_refs():
    """旧 DSL 字符串列表应被包装为 v2 资产引用对象。"""
    dsl = normalize_dsl(
        {
            "metrics": ["gmv"],
            "dimensions": ["region"],
            "filters": [{"field": "region", "op": "in", "values": ["华东"]}],
            "limit": 100,
        }
    )

    assert dsl["version"] == "2.0"
    assert dsl["metrics"][0]["name"] == "gmv"
    assert dsl["metrics"][0]["asset_type"] == "metric"
    assert dsl["metrics"][0].get("asset_id") is None
    assert dsl["dimensions"][0]["name"] == "region"
    assert dsl["filters"][0]["field"] == "region"
    assert get_dsl_item_name(dsl["metrics"][0]) == "gmv"


def test_normalize_dsl_keeps_asset_ids_and_ambiguities():
    """新 DSL 中的 asset_id、confidence 和 ambiguities 不应被丢弃。"""
    dsl = normalize_dsl(
        {
            "version": "2.0",
            "metrics": [
                {
                    "name": "gmv",
                    "asset_type": "metric",
                    "asset_id": 12,
                    "confidence": 0.93,
                }
            ],
            "filters": [
                {
                    "field": {
                        "name": "region",
                        "asset_type": "dimension",
                        "asset_id": 31,
                        "confidence": 0.88,
                    },
                    "op": "eq",
                    "values": ["华东"],
                }
            ],
            "ambiguities": [
                {
                    "text": "销售",
                    "reason": "同时可能指销售额和销售部门",
                    "candidates": [
                        {
                            "name": "gmv",
                            "asset_type": "metric",
                            "asset_id": 12,
                            "confidence": 0.61,
                        }
                    ],
                }
            ],
        }
    )

    assert dsl["metrics"][0]["asset_id"] == 12
    assert dsl["metrics"][0]["confidence"] == 0.93
    assert dsl["filters"][0]["field"]["asset_id"] == 31
    assert dsl["ambiguities"][0]["candidates"][0]["asset_type"] == "metric"


def test_normalize_direct_sql_does_not_require_metrics():
    """direct_sql 逃逸路径不需要 metrics。"""
    dsl = normalize_dsl({"direct_sql": "SELECT 1"})

    assert dsl["direct_sql"] == "SELECT 1"
    assert dsl["version"] == "2.0"
