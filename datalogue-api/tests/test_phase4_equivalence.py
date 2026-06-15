# ============================================================
# File Name   : test_phase4_equivalence.py
# Description:
#   Phase 4 fixture 等价性测试：加载 tests/fixtures/phase4_term_clarification_fixtures.jsonl，
#   用真实 DB session + seed PendingClarification 跑 resolve_term_clarification，
#   比对 fixture 中契约化的 expected_output 字段（status / selected_term_id /
#   resolved_question / answer / entry_intent / entry_route / entry_reason /
#   route_payload / clarification_resolution_result + DB 副作用）。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, PendingClarification
from app.services.lead_agent_routing import resolve_term_clarification


def _seed_pending(db_session, conv, sample_dataset, seed_spec: dict) -> PendingClarification:
    """根据 fixture input.pending_seed 在 DB 中 seed 一条 PendingClarification。"""
    if seed_spec is None:
        return None
    expires_in_minutes = seed_spec.get("expires_in_minutes", 30)
    pending = PendingClarification(
        id=seed_spec.get("id"),
        conversation_id=conv.id,
        dataset_id=seed_spec.get("dataset_id", sample_dataset.id),
        clarification_type="term_conflict",
        status="pending",
        original_question=seed_spec.get("original_question", "销售额是多少"),
        conflict_payload={"kind": "term_conflict_clarification"},
        candidates=seed_spec["candidates"],
        expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
    )
    db_session.add(pending)
    db_session.commit()
    db_session.refresh(pending)
    return pending


def _assert_expected(actual: dict, expected: dict, name: str, db_session, seeded_pending) -> list[str]:
    """逐字段比对 actual vs expected，收集所有失败项。"""
    failures: list[str] = []

    def _check(key, exp, act):
        if exp != act:
            failures.append(
                f"{name}: {key} expected={exp!r} actual={act!r}"
            )

    # 基础字段
    _check("status", expected.get("status"), actual.get("status"))
    _check("selected_term_id", expected.get("selected_term_id"), actual.get("selected_term_id"))
    _check("resolved_question", expected.get("resolved_question"), actual.get("resolved_question"))
    # answer：仅当 expected 显式提供时严格比对（resolved 不返回 answer）
    if "answer" in expected:
        _check("answer", expected["answer"], actual.get("answer"))
    # answer_contains：用于 unresolved 分支（answer 含动态候选清单，不便硬编码）
    exp_answer_contains = expected.get("answer_contains")
    if exp_answer_contains is not None:
        act_answer = actual.get("answer") or ""
        if exp_answer_contains not in act_answer:
            failures.append(
                f"{name}: answer_contains expected to contain {exp_answer_contains!r} actual={act_answer!r}"
            )
    _check("entry_intent", expected.get("entry_intent"), actual.get("entry_intent"))
    _check("entry_route", expected.get("entry_route"), actual.get("entry_route"))
    _check("entry_reason", expected.get("entry_reason"), actual.get("entry_reason"))

    # route_payload：fixture 中简化为 kind / clarification_id / candidates 列表
    exp_route = expected.get("route_payload", {})
    act_route = actual.get("route_payload") or {}
    if "kind" in exp_route:
        _check("route_payload.kind", exp_route["kind"], act_route.get("kind"))
    if "clarification_id" in exp_route:
        _check(
            "route_payload.clarification_id",
            exp_route["clarification_id"],
            act_route.get("clarification_id"),
        )
    if "candidates" in exp_route and isinstance(exp_route["candidates"], list):
        _check(
            "route_payload.candidates_count",
            len(exp_route["candidates"]),
            len(act_route.get("candidates", [])),
        )

    # clarification_resolution_result：fixture 简化为 status 子字段
    exp_crr = expected.get("clarification_resolution_result", {})
    act_crr = actual.get("clarification_resolution_result") or {}
    if "status" in exp_crr:
        _check(
            "clarification_resolution_result.status",
            exp_crr["status"],
            act_crr.get("status"),
        )
    if "clarification_id" in exp_crr:
        _check(
            "clarification_resolution_result.clarification_id",
            exp_crr["clarification_id"],
            act_crr.get("clarification_id"),
        )

    # DB 副作用
    if seeded_pending is not None and "expected_pending_status_after" in expected:
        db_session.refresh(seeded_pending)
        _check(
            "pending.status_after",
            expected["expected_pending_status_after"],
            seeded_pending.status,
        )

    return failures


def test_phase4_fixtures_equivalent():
    """加载 Phase 4 冻结 fixture，逐条跑 resolve_term_clarification 与 expected_output 比对。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.models.datasource import Datasource
    from app.models.dataset import SemanticDataset as Dataset

    fixtures_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "phase4_term_clarification_fixtures.jsonl"
    )
    if not fixtures_path.exists():
        pytest.skip("Phase 4 fixtures 未生成")

    # 内存 SQLite + ORM session，避免污染真实 DB
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session: Session = SessionLocal()

    try:
        # 共享一个 Datasource + SemanticDataset，dataset_id=1
        ds = Datasource(
            id=1,
            name="ds",
            db_type="postgres",
            host="localhost",
            port=5432,
            database_name="test",
            username="u",
            password_enc="x",
        )
        db_session.add(ds)
        db_session.commit()
        db_session.refresh(ds)
        sample_dataset = Dataset(
            id=1, name="test-ds", datasource_id=ds.id, status="active",
        )
        db_session.add(sample_dataset)
        db_session.commit()
        db_session.refresh(sample_dataset)

        failures: list[str] = []
        for line in fixtures_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            fixture = json.loads(line)
            name = fixture["name"]
            input_spec = fixture["input"]
            expected = fixture["expected_output"]

            # 每个 fixture 用独立 conv
            conv = Conversation(
                title=f"Phase4-{name}",
                thread_id=f"thread-{name}",
                dataset_id=sample_dataset.id,
            )
            db_session.add(conv)
            db_session.commit()
            db_session.refresh(conv)

            seeded = _seed_pending(db_session, conv, sample_dataset, input_spec.get("pending_seed"))

            actual = resolve_term_clarification(
                db=db_session,
                question=input_spec.get("question") or "",
                conversation_id=conv.id,
                dataset_id=input_spec.get("dataset_id", sample_dataset.id),
                clarification_response=input_spec.get("clarification_response"),
            )
            failures.extend(_assert_expected(actual, expected, name, db_session, seeded))

            # 清理 fixture 间的 conv / pending 隔离
            if seeded is not None:
                db_session.delete(seeded)
            db_session.delete(conv)
            db_session.commit()

        assert not failures, (
            f"Phase 4 fixture 与 resolve_term_clarification 不等价 ({len(failures)} 失败):\n  "
            + "\n  ".join(failures)
        )
    finally:
        db_session.close()
        engine.dispose()
