# ============================================================
# File Name   : test_bi_worker_agent.py
# Description:
#   验证 BI Worker 不会继承 AgentScope Service 的通用工具 Schema。
#
# Responsibilities:
#   - 校验最小工具集仅包含查询链路与 TeamSay。
#   - 校验非 basic ToolGroup 被移除，避免 reset_tools 回到模型上下文。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

from __future__ import annotations

import pytest

from agentscope.tool import FunctionTool, ToolGroup, Toolkit

from app.runtime.engine.bi_worker_agent import (
    BI_WORKER_ALLOWED_TOOL_NAMES,
    build_bi_worker_toolkit,
)


def _tool(name: str) -> FunctionTool:
    """构造仅用于 Toolkit 装配测试的无副作用工具。"""

    def handler() -> None:
        return None

    handler.__name__ = name
    return FunctionTool(handler)


@pytest.mark.asyncio
async def test_bi_worker_toolkit_keeps_only_allowlisted_tools():
    """BI Worker 必须丢弃工作区、任务、后台控制与未使用业务工具。"""

    source = Toolkit(
        tools=[
            _tool("Bash"),
            _tool("TaskCreate"),
            _tool("ToolStop"),
            _tool("TeamSay"),
            _tool("datalogue_search_assets"),
            *[_tool(name) for name in BI_WORKER_ALLOWED_TOOL_NAMES if name != "TeamSay"],
        ],
        tool_groups=[
            ToolGroup(
                name="schedule_tools",
                description="测试用的非默认工具组。",
                tools=[_tool("ScheduleCreate")],
            )
        ],
    )

    filtered = build_bi_worker_toolkit(source)
    schemas = await filtered.get_tool_schemas()
    tool_names = {schema["function"]["name"] for schema in schemas}

    assert tool_names == BI_WORKER_ALLOWED_TOOL_NAMES
    assert [group.name for group in filtered.tool_groups] == ["basic"]
    assert "reset_tools" not in tool_names
