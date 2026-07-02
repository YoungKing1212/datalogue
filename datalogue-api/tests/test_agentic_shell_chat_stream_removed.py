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
        app_root / "prompts" / "lead_agent.py",
    ]
    forbidden_terms = [
        "LegacyWorkflowTaskRunner",
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
