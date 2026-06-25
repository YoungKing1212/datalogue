# ============================================================
# File Name   : test_live_react_agent.py
# Description:
#   用真实 Datalogue 服务验证 AgentScope 2.0 Agent 能自主调用平台能力。
#
# Responsibilities:
#   - 启动 AgentScope Agent，而不是手动顺序调用工具。
#   - 使用真实 HTTP 请求访问当前部署的 Datalogue API。
#   - 断言 Agent 自主完成 plan-query 与 readonly SQL preview 两类能力调用。
#
# Author      : yangkai
# Created On  : 2026-06-25
# ============================================================

from __future__ import annotations

import os
from typing import Any

import pytest


pytestmark = pytest.mark.asyncio


def _first_positive_number(rows: list[dict[str, Any]]) -> int | float | None:
    """从 SQL preview 的首行结果中提取正数，避免把测试绑定到模型生成的列别名。"""

    if not rows:
        return None
    for value in rows[0].values():
        if isinstance(value, (int, float)) and value > 0:
            return value
    return None


@pytest.mark.integration
async def test_agentscope_agent_autonomously_calls_live_datalogue_tools() -> None:
    if os.getenv("RUN_AGENTSCOPE_REACT_MVP") != "1":
        pytest.skip("设置 RUN_AGENTSCOPE_REACT_MVP=1 后才请求真实服务和真实 LLM")

    try:
        from agentscope_react_mvp.mvp import run_datalogue_react_mvp
    except ImportError as exc:
        pytest.fail(f"运行真实 AgentScope MVP 前需要安装 agentscope 2.0：{exc}", pytrace=False)

    result = await run_datalogue_react_mvp(
        question="请使用数语工具统计 dataset 11 的项目合同数量，并给出最终数字。",
        dataset_id=11,
        base_url=os.getenv("DATALOGUE_BASE_URL", "http://127.0.0.1:8000"),
    )

    assert "DataloguePlanQueryTool" in result.tool_names
    assert "DatalogueExecuteSqlTool" in result.tool_names
    assert "/api/dataset" in result.called_paths
    assert "/api/dataset/11/selected-tables" in result.called_paths
    assert "/api/dataset/11/selected-columns" in result.called_paths
    assert "/api/dataset/11/sql/preview" in result.called_paths
    assert "/api/chat/stream" not in result.called_paths
    assert "/api/conversation" not in result.called_paths
    assert result.preview_result is not None
    assert result.preview_result["sql_guard"]["ok"] is True
    assert _first_positive_number(result.preview_result["rows"]) is not None
    assert result.final_text.strip()
