# ============================================================
# File Name   : test_agentic_architecture_p2_bi_boundaries.py
# Description:
#   AgentScope 架构瘦身 P2 BI 领域目录边界测试。
#
# Responsibilities:
#   - 验证 BI Toolkit、Dataset Skill 和 Toolchain 后续由 app/bi 领域包持有。
#   - 验证旧 services 路径在迁移期只作为兼容出口存在。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from app.services.subagent_planning.contracts import QueryPlan


def test_p2_bi_toolkit_new_path_owns_atomic_toolkit():
    from app.bi.toolkit import DatalogueBIAtomicToolkit, build_bi_atomic_toolkit
    from app.bi.toolkit.atomic import DatalogueBIAtomicToolkit as DirectToolkit

    assert DatalogueBIAtomicToolkit is DirectToolkit
    assert build_bi_atomic_toolkit.__module__ == "app.bi.toolkit.atomic"
    assert DirectToolkit.__module__ == "app.bi.toolkit.atomic"


def test_p2_bi_toolchain_new_path_owns_dataset_tool_call_runtime():
    from app.bi.toolchain import DatasetAgentToolCallRuntime
    from app.bi.toolchain.dataset_runtime import DatasetAgentToolCallRuntime as DirectRuntime

    assert DatasetAgentToolCallRuntime is DirectRuntime
    assert DirectRuntime.__module__ == "app.bi.toolchain.dataset_runtime"


def test_p2_bi_skill_new_path_owns_dataset_query_skill(db_session):
    from app.bi.skill import DatasetQuerySkill
    from app.bi.skill.dataset_query import DatasetQuerySkill as DirectSkill
    from app.bi.toolchain import DatasetAgentToolCallRuntime
    from app.bi.toolkit import DatalogueBIAtomicToolkit
    from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge

    def fake_dsl_generator(**_kwargs):
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.8,
            selected_assets=[],
        )

    skill = DatasetQuerySkill(db=db_session)
    toolkit = skill.build_toolkit()
    runtime = skill.build_toolchain_runtime(dsl_generator=fake_dsl_generator, toolkit=toolkit)
    bridge = skill.build_runtime_bridge(toolkit=toolkit)
    manifest = skill.capability_manifest()

    assert DatasetQuerySkill is DirectSkill
    assert DirectSkill.__module__ == "app.bi.skill.dataset_query"
    assert isinstance(toolkit, DatalogueBIAtomicToolkit)
    assert isinstance(runtime, DatasetAgentToolCallRuntime)
    assert isinstance(bridge, AgentScopeDatasetRuntimeBridge)
    assert bridge.toolkit is toolkit
    assert manifest["skill_name"] == "dataset_query"
    assert manifest["tool_names"] == toolkit.tool_names
    assert manifest["exposes_internal_sql"] is False
    manifest_text = str(manifest).lower()
    for forbidden in ("select ", " from ", "schema_context", "raw_rows", "query_plan"):
        assert forbidden not in manifest_text


def test_p2_native_handoff_factory_builds_dataset_bridge_through_skill(monkeypatch, db_session):
    from app.agents.bi_agent import native_handoff

    class FakeDatasetQuerySkill:
        calls: list[str] = []

        def __init__(self, *, db):
            self.db = db
            self.calls.append("init")

        def build_runtime_bridge(self):
            self.calls.append("build_runtime_bridge")
            return "bridge-from-skill"

    class FakeDatasetAgentFactory:
        def __init__(self, db):
            self.db = db

    monkeypatch.setattr(native_handoff, "DatasetQuerySkill", FakeDatasetQuerySkill)
    monkeypatch.setattr(native_handoff, "AgentScopeDatasetAgentFactory", FakeDatasetAgentFactory)

    native = native_handoff.AgentScopeNativeBIHandoff.from_db(db_session)

    assert native.bridge == "bridge-from-skill"
    assert FakeDatasetQuerySkill.calls.count("build_runtime_bridge") == 1


def test_p2_agent_team_runtime_does_not_use_legacy_direct_runner():
    from pathlib import Path

    runtime_source = Path(__file__).resolve().parents[1].joinpath("app", "runtime", "agent_team_runtime.py").read_text(
        encoding="utf-8"
    )

    assert "BIAgentTaskRunner" not in runtime_source
    assert "direct_query_runner_factory" not in runtime_source
    assert "AgenticDirectQueryRunner" not in runtime_source
