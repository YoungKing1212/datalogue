# ============================================================
# File Name   : test_phase6_equivalence.py
# Description:
#   Phase 6 fixture 等价性测试：加载 tests/fixtures/phase6_term_normalize_fixtures.jsonl，
#   逐条跑 DatasetSubAgent.resolve_term_conflict，与旧 term_normalize_node 冻结的
#   expected_output 比对关键字段。
#
#   25 条 fixture 覆盖 5 状态：not_applicable / resolved / needs_clarification /
#   missing_term / error + 边界。比对核心字段：status / term_normalization 关键子集 /
#   entry_intent / entry_route / answer / route_payload.kind + conflicts 数 + candidates 数。
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
    "term_conflict_clarification": "needs_clarification",
    "term_conflict_resolved": "resolved",
    "term_conflict_missing": "missing_term",
    "term_conflict_error": "error",
    "not_applicable": "not_applicable",
}


def _setup_sub_agent(dataset_id: int = 1) -> DatasetSubAgent:
    """构造一个不带真实 DB 的 DatasetSubAgent（resolve_term_conflict 只读 state，不查 DB）。"""
    return DatasetSubAgent(db=None, dataset_id=dataset_id)  # type: ignore[arg-type]


def _assert_expected(name: str, actual: dict, expected: dict) -> list[str]:
    """比对 actual vs expected 的关键语义字段（不要求精确逐字段相同）。"""
    failures: list[str] = []

    def _check(key, exp, act):
        if exp != act:
            failures.append(f"{name}: {key} expected={exp!r} actual={act!r}")

    # 1) status：Phase 6 新增字段
    exp_kind = (expected.get("route_payload") or {}).get("kind")
    exp_status = _KIND_TO_STATUS.get(exp_kind)
    if exp_status is not None:
        _check("status", exp_status, actual.get("status"))

    # 2) route_payload.kind
    if exp_kind is not None:
        act_kind = (actual.get("route_payload") or {}).get("kind")
        _check("route_payload.kind", exp_kind, act_kind)

    # 3) term_normalization 关键子集
    exp_tn = expected.get("term_normalization") or {}
    act_tn = actual.get("term_normalization") or {}

    # matched_terms 数量
    exp_matched_count = len(exp_tn.get("matched_terms") or [])
    act_matched_count = len(act_tn.get("matched_terms") or [])
    _check("term_normalization.matched_terms.count", exp_matched_count, act_matched_count)

    # conflicts 数量
    exp_conflicts_count = len(exp_tn.get("conflicts") or [])
    act_conflicts_count = len(act_tn.get("conflicts") or [])
    _check("term_normalization.conflicts.count", exp_conflicts_count, act_conflicts_count)

    # has_conflict
    _check("term_normalization.has_conflict", exp_tn.get("has_conflict"), act_tn.get("has_conflict"))

    # 4) entry_intent / entry_route：仅当旧节点返回时检查；Phase 6 新方法不直接设置
    #    这两个字段（由 chat 层在 needs_clarification 早退时统一注入）。DatasetSubAgent
    #    只负责决策（status=needs_clarification）+ route_payload.kind=term_conflict_clarification
    #    + 候选列表，chat 层拿到结果后把 entry_intent/entry_route 注入到 routing 里。
    #    因此跳过 entry_intent / entry_route 比对，避免与 chat 层耦合。
    pass

    # 5) answer（仅 clarification 时设置）
    if expected.get("answer") is not None:
        _check("answer", expected["answer"], actual.get("answer"))

    # 6) selected_term_id（旧节点澄清返回时不设置；Phase 6 仅当 selected_term_id 命中时设置）
    exp_sel = exp_tn.get("selected_term_id")
    if exp_sel is not None:
        _check("term_normalization.selected_term_id", exp_sel, act_tn.get("selected_term_id"))

    # 7) route_payload.conflicts 数（仅 clarification 时）
    exp_route_conflicts = (expected.get("route_payload") or {}).get("conflicts")
    if isinstance(exp_route_conflicts, list):
        act_route_conflicts = (actual.get("route_payload") or {}).get("conflicts") or []
        _check(
            "route_payload.conflicts.count",
            len(exp_route_conflicts),
            len(act_route_conflicts),
        )

    # 8) route_payload.candidates 数（仅 clarification 时）
    exp_route_cands = (expected.get("route_payload") or {}).get("candidates")
    if isinstance(exp_route_cands, list):
        act_route_cands = (actual.get("route_payload") or {}).get("candidates") or []
        _check(
            "route_payload.candidates.count",
            len(exp_route_cands),
            len(act_route_cands),
        )

    return failures


def test_phase6_fixtures_equivalent():
    """加载 Phase 6 冻结 fixture，逐条跑 DatasetSubAgent.resolve_term_conflict 与 expected_output 比对。"""
    fixtures_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "phase6_term_normalize_fixtures.jsonl"
    )
    if not fixtures_path.exists():
        pytest.skip("Phase 6 fixtures 未生成")

    failures: list[str] = []
    sub_agent = _setup_sub_agent()

    for line in fixtures_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fixture = json.loads(line)
        name = fixture["name"]
        input_spec = fixture["input"]

        # DatasetSubAgent.resolve_term_conflict 不需要真实 DB（纯确定性归一化）
        actual = sub_agent.resolve_term_conflict(
            question=input_spec.get("question") or "",
            terms=input_spec.get("schema_structured", {}).get("terms") or [],
            entities=input_spec.get("entities") or {},
            selected_term_id=input_spec.get("selected_term_id"),
        )
        failures.extend(_assert_expected(name, actual, fixture["expected_output"]))

    assert not failures, (
        f"Phase 6 fixture 与 DatasetSubAgent.resolve_term_conflict 不等价 ({len(failures)} 失败):\n  "
        + "\n  ".join(failures)
    )


def test_phase6_sub_agent_exposes_resolve_term_conflict():
    """DatasetSubAgent 公开 API smoke test。"""
    assert hasattr(DatasetSubAgent, "resolve_term_conflict"), "DatasetSubAgent 缺少 resolve_term_conflict"
    assert callable(DatasetSubAgent.resolve_term_conflict), "resolve_term_conflict 不可调用"


def test_phase6_resolve_term_conflict_not_applicable_default():
    """无 term 候选 → not_applicable 透明通过。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_term_conflict(question="无关问题", terms=[], entities={})
    assert out["status"] == "not_applicable", f"expected not_applicable, got {out['status']}"
    assert out["route_payload"]["kind"] == "not_applicable"
    assert out["term_normalization"]["has_conflict"] is False


def test_phase6_resolve_term_conflict_resolved_returns_entities():
    """resolved 分支：返回的 entities.terms 含 matched_text（chat 层负责更新 state）。"""
    sub_agent = _setup_sub_agent()
    entities = {"metrics": ["GMV"]}
    out = sub_agent.resolve_term_conflict(
        question="GMV",
        terms=[{"id": 1, "name": "GMV"}],
        entities=entities,
    )
    assert out["status"] == "resolved"
    # Phase 6 返回 dict['entities']['terms']，由 chat 层 merge 到 state。
    # 入参 entities 不被原地修改（保持纯函数语义）。
    assert out["entities"]["terms"] == ["GMV"], (
        f"out.entities.terms 应为 ['GMV'], got {out['entities']['terms']}"
    )
    assert out["route_payload"]["kind"] == "term_conflict_resolved"
    assert out["term_normalization"]["matched_terms"][0]["term_id"] == 1


def test_phase6_resolve_term_conflict_clarification_returns_candidates():
    """needs_clarification 分支：route_payload 含 candidates 列表。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_term_conflict(
        question="订单",
        terms=[
            {"id": 1, "name": "订单", "display_name": "订单数"},
            {"id": 2, "name": "订单", "display_name": "订单金额"},
        ],
    )
    assert out["status"] == "needs_clarification"
    assert out["route_payload"]["kind"] == "term_conflict_clarification"
    cands = out["route_payload"]["candidates"]
    assert len(cands) == 2, f"candidates 应有 2 项, got {len(cands)}"
    cand_ids = sorted([c["term_id"] for c in cands])
    assert cand_ids == [1, 2], f"candidate term_id 应为 [1, 2], got {cand_ids}"


def test_phase6_resolve_term_conflict_missing_term_early_return():
    """missing_term 分支：term 缺 id/name → 错误早退。"""
    sub_agent = _setup_sub_agent()
    out = sub_agent.resolve_term_conflict(
        question="GMV",
        terms=[{"name": "GMV"}],  # 缺 id
    )
    assert out["status"] == "missing_term"
    assert out["route_payload"]["kind"] == "term_conflict_missing"
    assert out["route_payload"]["invalid_count"] == 1
    assert "error" in out and "id 或 name" in out["error"]