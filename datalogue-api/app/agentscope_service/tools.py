# ============================================================
# File Name   : tools.py
# Description:
#   AgentScope Service 侧 Datalogue Dataset Tool 注册入口。
#
# Responsibilities:
#   - 暴露 create_app extra_agent_tools 可消费的异步工具 factory。
#   - 用 AgentScope FunctionTool 注册 Agent Team worker 可调用的 datalogue_query_dataset。
#   - 将工具返回值收口为安全 JSON 文本块，避免泄露查询语句、表结构或明细行。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import FunctionTool, ToolBase, ToolChunk

from app.agentscope_service.dataset_query_executor import execute_dataset_query_for_agent_team


AgentToolFactory = Callable[[str | None, str | None, str | None], Awaitable[list[ToolBase]]]


def build_datalogue_extra_agent_tools() -> AgentToolFactory:
    """构建 AgentScope create_app(extra_agent_tools=...) 可直接使用的工具工厂。"""

    async def _extra_agent_tools(
        user_id: str | None,
        agent_id: str | None,
        session_id: str | None,
    ) -> list[ToolBase]:
        del user_id, agent_id, session_id
        # AgentScope 的 AgentCreate 会为 worker 生成真实 agent_id，extra_agent_tools 当前拿不到
        # subagent_type；因此不能再用旧固定 "bi_agent" id 过滤。工具本身只接受必要的
        # dataset_id/confirmed_question，并通过 Datalogue 业务执行器 fail-closed。
        return [build_datalogue_query_dataset_tool()]

    return _extra_agent_tools


def build_datalogue_query_dataset_tool() -> FunctionTool:
    """创建 Agent Team worker 可见的 Dataset 查询工具。"""

    async def datalogue_query_dataset(
        dataset_id: int,
        confirmed_question: str,
        task_goal: str | None = None,
        user_confirmation_id: str | None = None,
        routing_rationale: str | None = None,
        trace_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> ToolChunk:
        """Run the confirmed Datalogue Dataset query and return safe result refs."""

        result = await execute_dataset_query_for_agent_team(
            dataset_id=dataset_id,
            confirmed_question=confirmed_question,
            task_goal=task_goal,
            user_confirmation_id=user_confirmation_id,
            routing_rationale=routing_rationale,
            trace_id=trace_id,
            parent_run_id=parent_run_id,
        )
        payload = result.to_tool_payload()
        return ToolChunk(
            content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))],
            state=ToolResultState.SUCCESS,
        )

    return FunctionTool(
        datalogue_query_dataset,
        description=(
            "Agent Team BI Worker 的 Datalogue Dataset 查询工具；只返回 answer_summary、"
            "artifact_ref、checkpoint_ref、row_count、column_count。"
        ),
        is_concurrency_safe=False,
        is_read_only=False,
    )
