# ============================================================
# File Name   : test_agentic_shell_chat_stream_removed.py
# Description:
#   /api/chat/stream 硬切删除测试。
#
# Responsibilities:
#   - 确认旧 chat stream 不再是执行入口。
#   - 防止后续改动重新把 /api/chat/stream 接回 runtime。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================


def test_chat_stream_route_is_removed(client):
    response = client.post("/api/chat/stream", json={"question": "统计合同总金额"})

    assert response.status_code in {404, 405}


def test_legacy_chat_stream_and_old_lead_agent_sources_are_removed():
    project_root = __import__("pathlib").Path(__file__).resolve().parents[1]
    app_root = project_root / "app"
    forbidden_paths = [
        app_root / "services" / "agentscope_shell_adapter.py",
        app_root / "services" / "agentic_chat_runtime.py",
        app_root / "services" / "bi_workbench_tool.py",
        app_root / "services" / "lead_agent.py",
        app_root / "services" / "lead_agent_routing.py",
        app_root / "services" / "lead_agent_planner_projection.py",
        app_root / "services" / "lead_agent_planning",
        app_root / "services" / "answer_explanation.py",
        app_root / "services" / "message_gateway.py",
        app_root / "services" / "observability" / "__init__.py",
        app_root / "services" / "observability" / "context.py",
        app_root / "services" / "observability" / "fallback.py",
        app_root / "services" / "observability" / "feedback.py",
        app_root / "services" / "observability" / "masking.py",
        app_root / "services" / "observability" / "prompt_registry.py",
        app_root / "services" / "observability" / "prompts.py",
        app_root / "services" / "observability" / "tracer.py",
        app_root / "services" / "agentscope_event_adapter.py",
        app_root / "services" / "artifact_actions.py",
        app_root / "services" / "conversation_store.py",
        app_root / "services" / "dataset_context.py",
        app_root / "services" / "dataset_subagent.py",
        app_root / "services" / "multiturn" / "__init__.py",
        app_root / "services" / "multiturn" / "last_success_task.py",
        app_root / "services" / "multiturn" / "query_artifacts.py",
        app_root / "services" / "multiturn" / "refinement_fast_path.py",
        app_root / "services" / "multiturn_context.py",
        app_root / "services" / "repair_patch.py",
        app_root / "services" / "report_generation.py",
        app_root / "services" / "runner.py",
        app_root / "services" / "soul_contract_sync.py",
        app_root / "services" / "subagent_fanout.py",
        app_root / "services" / "subagent_tool_adapter.py",
        app_root / "services" / "task_capsule.py",
        app_root / "services" / "subagent_planning" / "asset_catalog.py",
        app_root / "services" / "subagent_planning" / "asset_recall.py",
        app_root / "services" / "subagent_planning" / "detail_loop.py",
        app_root / "services" / "subagent_planning" / "execution.py",
        app_root / "services" / "subagent_planning" / "sql_context.py",
        app_root / "api" / "chat.py",
        app_root / "api" / "internal_subagent.py",
        app_root / "agents" / "bi_agent" / "agent.py",
        app_root / "agents" / "bi_agent" / "handoff_adapter.py",
        app_root / "agents" / "bi_agent" / "services.py",
        app_root / "graph" / "nodes.py",
        app_root / "graph" / "state.py",
        app_root / "graph" / "workflow.py",
        app_root / "middlewares" / "tracing.py",
        app_root / "prompts" / "dsl_generate.py",
        app_root / "prompts" / "intent_router.py",
        app_root / "prompts" / "lead_agent.py",
        app_root / "prompts" / "repair_patch.py",
        app_root / "prompts" / "report_generate.py",
        app_root / "prompts" / "sql_audit.py",
        app_root / "schemas" / "capsule.py",
        app_root / "schemas" / "dsl.py",
        project_root / "scripts" / "smoke_remote_subagent.py",
    ]
    forbidden_terms = [
        "LegacyWorkflowTaskRunner",
        "RemoteDatasetSubAgentRunner",
        "StateGraph",
        "build_workflow",
        "class DatasetSubAgent:",
        "InProcessDatasetSubAgentRunner",
        "DatalogueChatStreamRuntime",
        "BIWorkbenchTool",
        "AgentScopeShellAdapter",
        "AskBIRequest",
        "AskBIResponse",
        "chat_stream_runtime_hooks",
        "_stream_chat",
        "lead_agent_skill_selector",
        "lead_agent_tool_planner",
        "tool_planner",
        "skill_selector",
        "configure_agentscope_otel",
        "OTEL_TRACES_ENABLED",
    ]

    for path in forbidden_paths:
        assert not path.exists(), f"legacy source still exists: {path}"

    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in app_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    for term in forbidden_terms:
        assert term not in source_text
