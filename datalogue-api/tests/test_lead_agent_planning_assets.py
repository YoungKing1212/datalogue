# ============================================================
# File Name   : test_lead_agent_planning_assets.py
# Description:
#   LeadAgent 渐进式资产注入过滤层与投影层单元测试。
#
# Responsibilities:
#   - 验证 AssetFilterConfig 默认值与配置合并。
#   - 验证 filter_lead_planner_assets 的去重、白名单、阈值、Top-K、
#     元信息脱敏与 match_signals 截断逻辑。
#   - 验证 project_assets_for_lead_planner 的输出结构与摘要。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from app.core.config import Settings
from app.services.lead_agent_planning.asset_filter import filter_lead_planner_assets
from app.services.lead_agent_planning.asset_filter_config import (
    AssetFilterConfig,
    build_filter_config,
)
from app.services.lead_agent_planner_projection import (
    project_assets_for_lead_planner,
)


def _asset(
    asset_type: str,
    asset_id: str,
    name: str,
    confidence: float,
    metadata: dict | None = None,
    signals: list | None = None,
) -> dict:
    return {
        "asset_type": asset_type,
        "asset_id": asset_id,
        "name": name,
        "display_name": name,
        "source": "test",
        "confidence": confidence,
        "usage": "candidate",
        "match_reason": "test",
        "metadata": metadata or {},
        "match_signals": signals or [],
    }


def test_settings_default_progressive_asset_fields():
    assert Settings.model_fields["LEAD_AGENT_USE_PROGRESSIVE_ASSETS"].default is False
    assert Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT"].default == 3
    assert Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_FIELD"].default == 10
    assert (
        Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT"].default
        == 0.60
    )
    assert (
        Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_FIELD"].default == 0.25
    )
    assert (
        Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_GLOBAL_MIN_CONFIDENCE"].default == 0.20
    )
    assert (
        Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_TOKEN_BUDGET_SKILL_SELECTION"].default
        == 600
    )
    assert (
        Settings.model_fields["LEAD_AGENT_PROGRESSIVE_ASSET_TOKEN_BUDGET_TOOL_PLANNING"].default
        == 800
    )


def test_asset_filter_config_defaults():
    config = AssetFilterConfig()
    assert config.topk_blueprint == 3
    assert config.topk_field == 10
    assert config.min_confidence_blueprint == 0.60
    assert config.global_min_confidence == 0.20
    assert config.metadata_whitelist == {"table_name", "column_name", "parameters", "expr"}
    assert config.max_signals_per_asset == 3
    assert config.get_topk("blueprint") == 3
    assert config.get_min_confidence("metric") == 0.35
    assert config.get_topk("unknown_type") == 10
    assert config.get_min_confidence("unknown_type") == 0.25


def test_build_filter_config_from_settings():
    settings = Settings(
        LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT=2,
        LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT=0.75,
        LEAD_AGENT_PROGRESSIVE_ASSET_METADATA_WHITELIST="table_name",
    )
    config = build_filter_config(settings=settings)
    assert config.topk_blueprint == 2
    assert config.min_confidence_blueprint == 0.75
    assert config.metadata_whitelist == {"table_name"}


def test_build_filter_config_explicit_overrides_take_precedence():
    settings = Settings(
        LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT=2,
    )
    config = build_filter_config(
        settings=settings,
        explicit_overrides={"topk_blueprint": 5, "min_confidence_blueprint": 0.90},
    )
    assert config.topk_blueprint == 5
    assert config.min_confidence_blueprint == 0.90


def test_filter_lead_planner_assets_deduplicates_by_type_and_id():
    assets = [
        _asset("blueprint", "bp_1", "日报查询", 0.8),
        _asset("blueprint", "bp_1", "日报查询", 0.5),
        _asset("blueprint", "bp_2", "周报查询", 0.7),
    ]
    result = filter_lead_planner_assets({"assets": assets})
    assert len(result) == 2
    assert {a["asset_id"] for a in result} == {"bp_1", "bp_2"}
    assert next(a for a in result if a["asset_id"] == "bp_1")["confidence"] == 0.8


def test_filter_lead_planner_assets_skips_unknown_types():
    assets = [
        _asset("blueprint", "bp_1", "日报查询", 0.8),
        _asset("custom_type", "c_1", "自定义资产", 0.9),
    ]
    result = filter_lead_planner_assets(assets)
    assert len(result) == 1
    assert result[0]["asset_type"] == "blueprint"


def test_filter_lead_planner_assets_global_min_confidence():
    # 把 metric 类型阈值临时放低，使全局最小置信度成为唯一门槛
    config = AssetFilterConfig(min_confidence_metric=0.10)
    assets = [
        _asset("metric", "m_1", "销售额", 0.25),
        _asset("metric", "m_2", "利润额", 0.15),
    ]
    result = filter_lead_planner_assets(assets, config=config)
    assert len(result) == 1
    assert result[0]["asset_id"] == "m_1"


def test_filter_lead_planner_assets_type_min_confidence():
    assets = [
        _asset("blueprint", "bp_1", "弱匹配蓝图", 0.55),
        _asset("blueprint", "bp_2", "强匹配蓝图", 0.85),
    ]
    result = filter_lead_planner_assets(assets)
    assert len(result) == 1
    assert result[0]["asset_id"] == "bp_2"


def test_filter_lead_planner_assets_topk_per_type():
    assets = [_asset("metric", f"m_{i}", f"指标{i}", 0.5 - i * 0.01) for i in range(8)]
    result = filter_lead_planner_assets(assets)
    assert len(result) == 5
    # 结果按置信度全局降序
    assert result[0]["asset_id"] == "m_0"
    assert result[-1]["asset_id"] == "m_4"


def test_filter_lead_planner_assets_sanitizes_metadata():
    assets = [
        _asset(
            "field",
            "f_1",
            "订单金额",
            0.5,
            metadata={
                "table_name": "orders",
                "column_name": "amount",
                "raw_sql": "SELECT * FROM orders",
                "internal_context": "不应泄露",
            },
        )
    ]
    config = AssetFilterConfig(metadata_whitelist={"table_name", "column_name"})
    result = filter_lead_planner_assets(assets, config=config)
    assert result[0]["metadata"] == {"table_name": "orders", "column_name": "amount"}


def test_filter_lead_planner_assets_trims_match_signals():
    signals = [
        {"type": "exact", "value": "销售额", "score": 0.55, "extra": "drop"},
        {"type": "contains", "value": "销售", "score": 0.30, "extra": "drop"},
        {"type": "synonym", "value": "营收", "score": 0.20, "extra": "drop"},
        {"type": "alias", "value": "收入", "score": 0.10, "extra": "drop"},
    ]
    assets = [_asset("metric", "m_1", "销售额", 0.9, signals=signals)]
    config = AssetFilterConfig(max_signals_per_asset=2)
    result = filter_lead_planner_assets(assets, config=config)
    projected_signals = result[0]["match_signals"]
    assert len(projected_signals) == 2
    assert projected_signals[0]["type"] == "exact"
    assert projected_signals[1]["type"] == "contains"
    # 只保留 type/value/score
    assert set(projected_signals[0].keys()) == {"type", "value", "score"}


def test_filter_lead_planner_assets_sorts_by_confidence_descending():
    assets = [
        _asset("term", "t_1", "术语A", 0.3),
        _asset("blueprint", "bp_1", "蓝图A", 0.9),
        _asset("metric", "m_1", "指标A", 0.6),
    ]
    result = filter_lead_planner_assets(assets)
    confidences = [a["confidence"] for a in result]
    assert confidences == sorted(confidences, reverse=True)


def test_project_assets_for_lead_planner_produces_summary():
    assets = [
        _asset("blueprint", "bp_1", "日报", 0.85, metadata={"parameters": ["user"]}),
        _asset("metric", "m_1", "销售额", 0.6),
        _asset("field", "f_1", "amount", 0.4, metadata={"table_name": "orders"}),
    ]
    projection = project_assets_for_lead_planner(
        assets,
        stage="skill_selection",
        token_budget=800,
        question="查询昨日销售额",
    )
    assert projection["stage"] == "skill_selection"
    assert projection["token_budget"] == 800
    assert projection["question"] == "查询昨日销售额"
    assert projection["projected_at"]
    assert len(projection["assets"]) == 3
    assert projection["summary"]["total"] == 3
    assert projection["summary"]["counts_by_type"] == {
        "blueprint": 1,
        "metric": 1,
        "field": 1,
    }
    assert projection["summary"]["top_asset_types"][0]["asset_type"] == "blueprint"
    assert projection["summary"]["token_estimate"] > 0


def test_project_assets_for_lead_planner_respects_token_budget():
    # 构造多条资产，人为把预算压到只能容纳 1 条
    assets = [_asset("metric", f"m_{i}", f"指标{i}", 0.9 - i * 0.01) for i in range(10)]
    projection = project_assets_for_lead_planner(
        assets,
        stage="tool_planning",
        token_budget=1,
    )
    assert len(projection["assets"]) == 1
    assert projection["summary"]["dropped_by_budget"] == 9
