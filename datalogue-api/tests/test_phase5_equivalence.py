# ============================================================
# File Name   : test_phase5_equivalence.py
# Description:
#   Phase 5 fixture 等价性测试：加载 tests/fixtures/phase5_analysis_blueprint_fixtures.jsonl，
#   用 in-memory SQLite + ORM 跑 DatasetSubAgent.resolve_analysis_blueprint，比对
#   fixture 中契约化的 expected_output 字段。
#
#   25 条 fixture 覆盖 6 状态：not_applicable / not_found / semantic_plan / executed /
#   clarification / error。比对核心 8 字段（route_payload / answer / error / sql_result /
#   sql / sql_list / should_retry / generation_mode / blueprint_context）+ 从
#   route_payload.kind 反推 status。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.security import encrypt_password
from app.models.datasource import Datasource
from app.models.dataset import AnalysisBlueprint, SemanticDataset
from app.services.dataset_subagent import DatasetSubAgent


# 从 route_payload.kind 推断 status（用于断言新字段 status）
_KIND_TO_STATUS = {
    "analysis_blueprint": "executed",
    "analysis_blueprint_semantic": "semantic_plan",
    "clarification": "clarification",
    "analysis_blueprint_error": "error",
    "not_found": "not_found",
    "not_applicable": "not_applicable",
}

# 旧节点的 3 字段 fallback（not_applicable 类旧 fixture 只有这 3 字段）
_OLD_NODE_FALLBACK_FIELDS = {"error", "should_retry", "sql_result"}
_NON_SEMANTIC_SQL_RESULT_FIELDS = {"execution_time_ms"}


def _setup_session(dataset_id: int = 1):
    """构造 in-memory ORM session + 临时文件 SQLite 数据源（让 executed 路线能跑 SQL）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    ds = Datasource(
        id=1,
        name="bp-test-ds",
        db_type="sqlite",
        host="",
        port=0,
        database_name=tmp_db.name,
        username="",
        password_enc=encrypt_password("test"),
    )
    session.add(ds)
    session.commit()
    session.refresh(ds)

    dataset = SemanticDataset(
        id=dataset_id,
        name="bp-test-dataset",
        datasource_id=ds.id,
        status="active",
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)

    return engine, session, dataset, Path(tmp_db.name)


def _make_blueprint(session, dataset_id, **kwargs) -> AnalysisBlueprint:
    bp = AnalysisBlueprint(dataset_id=dataset_id, **kwargs)
    session.add(bp)
    session.commit()
    session.refresh(bp)
    return bp


def _assert_expected(name: str, actual: dict, expected: dict, session) -> list[str]:
    """比对 actual vs expected 的关键语义字段。

    Phase 5 改写后新 DatasetSubAgent 的返回 shape 与原节点不同（多了 status / blueprint_id /
    blueprint_name / execution_time_ms / answer 等），所以本测试只比对语义关键字段：
    - status：从 expected.route_payload.kind 推
    - route_payload.kind
    - generation_mode（executed vs semantic_plan）
    - blueprint_context（semantic_plan 才有）
    - sql_result / sql / sql_list / error / answer（仅当 expected 显式提供）
    - should_retry（仅当 expected 显式提供）
    """
    failures: list[str] = []

    def _check(key, exp, act):
        if exp != act:
            failures.append(f"{name}: {key} expected={exp!r} actual={act!r}")

    # 1) status：Phase 5 新增字段
    exp_kind = (expected.get("route_payload") or {}).get("kind")
    exp_status = _KIND_TO_STATUS.get(exp_kind) if exp_kind else None
    if exp_status is not None:
        _check("status", exp_status, actual.get("status"))

    # 2) route_payload.kind
    if exp_kind is not None:
        act_kind = (actual.get("route_payload") or {}).get("kind")
        _check("route_payload.kind", exp_kind, act_kind)

    # 3) generation_mode
    if "generation_mode" in expected:
        _check("generation_mode", expected["generation_mode"], actual.get("generation_mode"))

    # 4) blueprint_context（仅当 expected 显式提供）
    if "blueprint_context" in expected:
        _check("blueprint_context", expected["blueprint_context"], actual.get("blueprint_context"))

    # 5) error / answer / should_retry（仅当 expected 显式提供）
    for key in ("error", "answer", "should_retry"):
        if key in expected:
            _check(key, expected[key], actual.get(key))

    def _normalize_sql_result(value):
        """移除执行耗时等非语义字段，避免毫秒级抖动破坏 fixture 等价性。"""
        if not isinstance(value, dict):
            return value
        return {
            key: item
            for key, item in value.items()
            if key not in _NON_SEMANTIC_SQL_RESULT_FIELDS
        }

    # 6) sql_result / sql / sql_list：仅当 expected 显式非 None
    for key in ("sql_result", "sql", "sql_list"):
        if expected.get(key) is not None:
            if key == "sql_result":
                _check(
                    key,
                    _normalize_sql_result(expected[key]),
                    _normalize_sql_result(actual.get(key)),
                )
            else:
                _check(key, expected[key], actual.get(key))

    return failures


def test_phase5_fixtures_equivalent():
    """加载 Phase 5 冻结 fixture，逐条跑 DatasetSubAgent.resolve_analysis_blueprint 与 expected_output 比对。"""
    fixtures_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "phase5_analysis_blueprint_fixtures.jsonl"
    )
    if not fixtures_path.exists():
        pytest.skip("Phase 5 fixtures 未生成")

    failures: list[str] = []
    tmp_files: list[Path] = []

    try:
        for line in fixtures_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            fixture = json.loads(line)
            name = fixture["name"]
            input_spec = fixture["input"]

            # 每个 fixture 用独立 session + 临时数据源
            engine, session, dataset, tmp_path = _setup_session(
                dataset_id=input_spec.get("dataset_id") or 1
            )
            tmp_files.append(tmp_path)

            # 按 fixture 的 blueprint_seed 字段还原蓝图（保持与 capture 时一致）
            if "blueprint_seed" in fixture and input_spec.get("blueprint_id"):
                seed = dict(fixture["blueprint_seed"])
                # seed 自带 dataset_id 时用它（用于跨 dataset 蓝图场景）
                bp_dataset_id = seed.pop("dataset_id", dataset.id)
                _make_blueprint(session, dataset_id=bp_dataset_id, **seed)
            # 无 seed 时（not_found 类）不种蓝图，保持 db 中查无状态

            sub_agent = DatasetSubAgent(db=session, dataset_id=dataset.id)
            actual = sub_agent.resolve_analysis_blueprint(
                blueprint_id=input_spec.get("blueprint_id"),
                question=input_spec.get("question") or "",
                entry_route=input_spec.get("entry_route"),
                original_question=input_spec.get("original_question"),
                resolved_question=input_spec.get("resolved_question"),
                time_context=input_spec.get("time_context"),
            )

            failures.extend(_assert_expected(name, actual, fixture["expected_output"], session))

            session.close()
            engine.dispose()
    finally:
        for p in tmp_files:
            p.unlink(missing_ok=True)

    assert not failures, (
        f"Phase 5 fixture 与 DatasetSubAgent.resolve_analysis_blueprint 不等价 ({len(failures)} 失败):\n  "
        + "\n  ".join(failures)
    )
