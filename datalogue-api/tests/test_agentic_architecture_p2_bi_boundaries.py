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


def test_p2_handoff_factories_build_dataset_bridge_through_skill(monkeypatch, db_session):
    from app.agents.bi_agent import handoff_adapter, native_handoff

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

    monkeypatch.setattr(handoff_adapter, "DatasetQuerySkill", FakeDatasetQuerySkill)
    monkeypatch.setattr(handoff_adapter, "AgentScopeDatasetAgentFactory", FakeDatasetAgentFactory)
    monkeypatch.setattr(native_handoff, "DatasetQuerySkill", FakeDatasetQuerySkill)
    monkeypatch.setattr(native_handoff, "AgentScopeDatasetAgentFactory", FakeDatasetAgentFactory)

    adapter = handoff_adapter.DatalogueBIHandoffAdapter.from_db(db_session)
    native = native_handoff.AgentScopeNativeBIHandoff.from_db(db_session)

    assert adapter.bridge == "bridge-from-skill"
    assert native.bridge == "bridge-from-skill"
    assert FakeDatasetQuerySkill.calls.count("build_runtime_bridge") == 2


def test_p2_bi_agent_new_path_owns_business_agent_facade(db_session):
    from app.agents.bi_agent import BIAgent
    from app.agents.bi_agent.agent import BIAgent as DirectBIAgent
    from app.bi.skill import DatasetQuerySkill

    agent = BIAgent(db=db_session)
    manifest = agent.capability_manifest()

    assert BIAgent is DirectBIAgent
    assert DirectBIAgent.__module__ == "app.agents.bi_agent.agent"
    assert manifest["agent_name"] == "bi_agent"
    assert manifest["skill_names"] == [DatasetQuerySkill.skill_name]
    assert manifest["default_skill"] == DatasetQuerySkill.skill_name
    manifest_text = str(manifest).lower()
    for forbidden in ("select ", " from ", "schema_context", "raw_rows", "query_plan"):
        assert forbidden not in manifest_text


def test_p2_task_runner_defaults_use_agentscope_service_runner():
    from app.agentscope_service.runner import AgentScopeServiceTaskRunner
    from app.api.agentic_shell import build_agentic_shell_task_runner
    from app.runtime import AgenticShellTaskRuntime
    from app.runtime.task_runtime import AgenticShellTaskRuntime as DirectRuntime

    runner = build_agentic_shell_task_runner(base_url="http://testserver/agentscope")

    assert AgenticShellTaskRuntime is DirectRuntime
    assert isinstance(runner, AgentScopeServiceTaskRunner)
    assert runner.base_url == "http://testserver/agentscope"
