# ============================================================
# File Name   : test_phase7_equivalence.py
# Description:
#   Phase 7 fixture 等价性测试：加载 tests/fixtures/phase7_semantic_asset_fixtures.jsonl，
#   逐条跑 DatasetSubAgent.resolve_metric，与旧 semantic_asset_resolution_node 冻结的
#   expected_output 比对关键字段。
#
#   25 条 fixture 覆盖 5 状态：not_applicable / resolved / needs_clarification /
#   missing_metric / error + 边界。比对核心字段：status / semantic_asset_resolution 关键子集 /
#   metric_resolution 兼容字段 / route_payload.kind + ambiguities 数。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.dataset_subagent import DatasetSubAgent


# 从 route_payload.kind 推断 status（用于断言 status 新字段）
_KIND_TO_STATUS = {
    "metric_resolve_clarification": "needs_clarification",
    "metric_resolve_resolved": "resolved",
    "metric_resolve_missing": "missing_metric",
    "metric_resolve_error": "error",
    "not_applicable": "not_applicable",
}


def _setup_sub_agent(dataset_id: int = 1) -> DatasetSubAgent:
    """构造一个不带真实 DB 的 DatasetSubAgent（resolve_metric 只读 state，不查 DB）。"""
    return DatasetSubAgent(db=None, dataset_id=dataset_id)  # type: ignore[arg-type]


def _assert_expected(name: str, actual: dict, expected: dict) -> list[str]:
    """比对 actual vs expected 的关键语义字段（不要求精确逐字段相同）。"""
    failures: list[str] = []

    def _check(key, exp, act):
        if exp != act:
            failures.append(f"{name}: {key} expected={exp!r} actual={act!r}")

    # 1) status：Phase 7 新增字段
    exp_kind = (expected.get("route_payload") or {}).get("kind")
    exp_status = _KIND_TO_STATUS.get(exp_kind)
    if exp_status is not None:
        _check("status", exp_status, actual.get("status"))

    # 2) route_payload.kind
    if exp_kind is not None:
        act_kind = (actual.get("route_payload") or {}).get("kind")
        _check("route_payload.kind", exp_kind, act_kind)

    # 3) semantic_asset_resolution 关键子集
    exp_sa = expected.get("semantic_asset_resolution") or {}
    act_sa = actual.get("semantic_asset_resolution") or {}

    # 资产总数
    _check(
        "semantic_asset_resolution.assets.count",
        len(exp_sa.get("assets") or []),
        len(act_sa.get("assets") or []),
    )

    # 各 bucket 数
    for bucket in ("terms", "metrics", "dimensions", "fields", "blueprints"):
        _check(
            f"semantic_asset_resolution.{bucket}.count",
            len(exp_sa.get(bucket) or []),
            len(act_sa.get(bucket) or []),
        )

    # ambiguities 数
    _check(
        "semantic_asset_resolution.ambiguities.count",
        len(exp_sa.get("ambiguities") or []),
        len(act_sa.get("ambiguities") or []),
    )

    # unresolved 数
    _check(
        "semantic_asset_resolution.unresolved.count",
        len(exp_sa.get("unresolved") or []),
        len(act_sa.get("unresolved") or []),
    )

    # 4) metric_resolution 兼容字段
    exp_mr = expected.get("metric_resolution") or {}
    act_mr = actual.get("metric_resolution") or {}
    if "metrics" in exp_mr:
        _check(
            "metric_resolution.metrics.count",
            len(exp_mr.get("metrics") or []),
            len(act_mr.get("metrics") or []),
        )
    if "dimensions" in exp_mr:
        _check(
            "metric_resolution.dimensions.count",
            len(exp_mr.get("dimensions") or []),
            len(act_mr.get("dimensions") or []),
        )
    if "all_matched" in exp_mr:
        _check("metric_resolution.all_matched", exp_mr["all_matched"], act_mr.get("all_matched"))
    if "unresolved" in exp_mr:
        _check(
            "metric_resolution.unresolved",
            exp_mr.get("unresolved"),
            act_mr.get("unresolved"),
        )

    # 5) selected_metric_id（仅 resolved 时）
    if "selected_metric_id" in expected:
        _check(
            "selected_metric_id",
            expected["selected_metric_id"],
            actual.get("selected_metric_id"),
        )

    # 6) resolved_question（仅 resolved / not_applicable 时为 question 原文）
    if "resolved_question" in expected:
        _check(
            "resolved_question",
            expected["resolved_question"],
            actual.get("resolved_question"),
        )

    return failures


def test_phase7_fixtures_equivalent():
    """加载 Phase 7 冻结 fixture，逐条跑 DatasetSubAgent.resolve_metric 与 expected_output 比对。"""
    fixtures_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "phase7_semantic_asset_fixtures.jsonl"
    )
    if not fixtures_path.exists():
        pytest.skip("Phase 7 fixtures 未生成")

    failures: list[str] = []
    sub_agent = _setup_sub_agent()

    for line in fixtures_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fixture = json.loads(line)
        name = fixture["name"]
        input_spec = fixture["input"]

        actual = sub_agent.resolve_metric(
            question=input_spec.get("question") or "",
            entities=input_spec.get("entities") or {},
            schema_structured=input_spec.get("schema_structured"),
        )
        failures.extend(_assert_expected(name, actual, fixture["expected_output"]))

    assert not failures, (
        f"Phase 7 fixture 与 DatasetSubAgent.resolve_metric 不等价 ({len(failures)} 失败):\n  "
        + "\n  ".join(failures)
    )


def test_phase7_sub_agent_exposes_resolve_metric():
    """DatasetSubAgent 公开 API smoke test。"""
    assert hasattr(DatasetSubAgent, "resolve_metric"), "DatasetSubAgent 缺少 resolve_metric"
    assert callable(DatasetSubAgent.resolve_metric), "resolve_metric 不可调用"


def test_phase7_resolve_metric_not_applicable_no_schema():
    """无 schema → not_applicable 透明通过。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_metric(question="随便问", schema_structured=None)
    assert out["status"] == "not_applicable"
    assert out["route_payload"]["kind"] == "not_applicable"
    assert out["semantic_asset_resolution"]["assets"] == []
    assert out["metric_resolution"]["all_matched"] is True


def test_phase7_resolve_metric_resolved_metric_exact():
    """resolved 分支：metric exact 命中，返回 selected_metric_id 与 metric_resolution。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_metric(
        question="GMV",
        schema_structured={
            "metrics": [{"id": 1, "name": "GMV"}],
            "dimensions": [], "terms": [], "fields": [], "blueprints": [],
        },
    )
    assert out["status"] == "resolved"
    assert out["route_payload"]["kind"] == "metric_resolve_resolved"
    assert out["selected_metric_id"] == 1
    assert out["resolved_question"] == "GMV"
    assert len(out["semantic_asset_resolution"]["metrics"]) == 1
    assert out["metric_resolution"]["all_matched"] is True


def test_phase7_resolve_metric_needs_clarification_two_close_metrics():
    """needs_clarification 分支：2 个 metric 置信度接近 → 早退。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_metric(
        question="GMV",
        schema_structured={
            "metrics": [
                {"id": 1, "name": "GMV", "synonyms": ["GMV 总额"]},
                {"id": 2, "name": "GMV 总额", "synonyms": ["GMV"]},
            ],
            "dimensions": [], "terms": [], "fields": [], "blueprints": [],
        },
    )
    assert out["status"] == "needs_clarification"
    assert out["route_payload"]["kind"] == "metric_resolve_clarification"
    assert len(out["semantic_asset_resolution"]["ambiguities"]) >= 1
    assert out["selected_metric_id"] is None


def test_phase7_resolve_metric_missing_metric_early_return():
    """missing_metric 分支：metric 缺 id/name → 错误早退。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_metric(
        question="GMV",
        schema_structured={
            "metrics": [{"name": "GMV"}],  # 缺 id
            "dimensions": [], "terms": [], "fields": [], "blueprints": [],
        },
    )
    assert out["status"] == "missing_metric"
    assert out["route_payload"]["kind"] == "metric_resolve_missing"
    assert out["route_payload"]["invalid_count"] == 1
    assert "error" in out and "id 或 name" in out["error"]


def test_phase7_resolve_metric_term_linked_asset_resolution():
    """term 命中后通过 asset_links 扩展到 metric/dimension。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_metric(
        question="成交总额",
        schema_structured={
            "metrics": [{"id": 10, "name": "GMV", "synonyms": ["总成交额"]}],
            "dimensions": [{"id": 20, "name": "订单日期"}],
            "terms": [
                {
                    "id": 100,
                    "name": "成交总额",
                    "synonyms": ["GMV"],
                    "asset_links": [
                        {"asset_type": "metric", "asset_id": 10},
                        {"asset_type": "dimension", "asset_id": 20},
                    ],
                }
            ],
            "fields": [],
            "blueprints": [],
        },
    )
    assert out["status"] == "resolved"
    # term + linked metric + linked dimension = 3 assets
    assert len(out["semantic_asset_resolution"]["assets"]) >= 2
    assert any(a["asset_type"] == "term" for a in out["semantic_asset_resolution"]["assets"])
    assert any(a["asset_type"] == "metric" for a in out["semantic_asset_resolution"]["assets"])
    assert any(a["asset_type"] == "dimension" for a in out["semantic_asset_resolution"]["assets"])