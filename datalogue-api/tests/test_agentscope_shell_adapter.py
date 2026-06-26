# ============================================================
# File Name   : test_agentscope_shell_adapter.py
# Description:
#   AgentScopeShellAdapter 最小验证线测试。
#
# Responsibilities:
#   - 验证 Shell Adapter 第一阶段只调用 ask_bi。
#   - 验证响应只包含 answer、ArtifactCard、refs 和安全事件。
#   - 验证工具白名单不允许 schema、SQL、database 或 control_plane 能力。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import pytest

from app.schemas.bi_workbench import AskBIRequest
from app.services.agentscope_shell_adapter import AgentScopeShellAdapter
from app.services.bi_workbench_tool import BIWorkbenchTool


@pytest.mark.asyncio
async def test_agentscope_shell_adapter_only_calls_ask_bi():
    calls: list[AskBIRequest] = []

    async def handler(request: AskBIRequest):
        calls.append(request)
        return await BIWorkbenchTool(handler=_safe_response).ask_bi(request)

    def _safe_response(request: AskBIRequest):
        primary_ref = {"ref": "artifact:bi_answer:1", "kind": "answer", "title": "BI 查询结果摘要"}
        return {
            "task_id": "task-1",
            "event_envelope": {
                "event_type": "answer.completed",
                "task_id": "task-1",
                "payload": {"answer": f"已受理问数请求：{request.question}"},
            },
            "answer": f"已受理问数请求：{request.question}",
            "artifact_card": {
                "title": "BI 查询结果",
                "summary_for_chat": f"已受理问数请求：{request.question}",
                "primary_ref": primary_ref,
            },
            "primary_ref": primary_ref,
            "status": "completed",
        }

    adapter = AgentScopeShellAdapter(allowed_tools=["ask_bi"], ask_bi_func=handler)

    response = await adapter.run("查询杨凯 2024 年工作日志", confirmed_dataset_id=12)

    dumped = response.model_dump_json()
    assert [call.question for call in calls] == ["查询杨凯 2024 年工作日志"]
    assert response.used_tools == ["ask_bi"]
    assert response.artifact_card.primary_ref
    assert response.primary_ref == response.artifact_card.primary_ref.ref
    assert response.visible_events[0].channel == "shell_visible"
    assert "raw_sql" not in dumped
    assert "raw_result" not in dumped
    assert "control_plane" not in dumped
    assert "capsule" not in dumped
    assert "schema" not in dumped


def test_agentscope_shell_adapter_rejects_extra_tools():
    with pytest.raises(ValueError):
        AgentScopeShellAdapter(allowed_tools=["ask_bi", "schema"])


def test_agentscope_shell_adapter_requires_exact_first_phase_whitelist():
    with pytest.raises(ValueError):
        AgentScopeShellAdapter(allowed_tools=[])
