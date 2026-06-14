# ============================================================
# File Name   : test_phase3_equivalence.py
# Description:
#   Phase 3 fixture 等价性测试：加载 tests/fixtures/phase3_routing_fixtures.jsonl
#   跑 _classify_entry_intent 与 frozen expected_output 比对。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.lead_agent_routing import _classify_entry_intent


def test_phase3_fixtures_equivalent():
    """加载 Phase 3 冻结 fixture，逐条跑 _classify_entry_intent 与 expected_output 比对。"""
    fixtures_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "phase3_routing_fixtures.jsonl"
    )
    if not fixtures_path.exists():
        pytest.skip("Phase 3 fixtures 未生成（先跑 scripts/capture_phase3_fixtures.py）")

    failures = []
    for line in fixtures_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fixture = json.loads(line)
        name = fixture["name"]
        state = fixture["input_state"]
        expected = fixture["expected_output"]
        actual = _classify_entry_intent(
            db=None,
            question=state.get("question") or "",
            intent=state.get("intent") or "query",
            entities=state.get("entities") or {},
            dataset_id=state.get("dataset_id"),
            history=state.get("history") or [],
            multiturn_context=state.get("multiturn_context") or {},
            clarification_response=state.get("clarification_response"),
            lead_agent_context=state.get("lead_agent_context") or {},
        )
        if actual.get("entry_intent") != expected.get("entry_intent"):
            failures.append(
                f"{name}: entry_intent expected={expected.get('entry_intent')!r} "
                f"actual={actual.get('entry_intent')!r}"
            )
        if actual.get("entry_route") != expected.get("entry_route"):
            failures.append(
                f"{name}: entry_route expected={expected.get('entry_route')!r} "
                f"actual={actual.get('entry_route')!r}"
            )

    assert not failures, (
        f"Phase 3 fixture 与 _classify_entry_intent 不等价 ({len(failures)} 失败):\n  "
        + "\n  ".join(failures)
    )
