# ============================================================
# File Name   : subagent_fanout.py
# Description:
#   多数据集 SubAgent fan-out 编排层。
#
# Responsibilities:
#   - 并发执行多个数据集 SubAgent 调用并保持结果顺序稳定。
#   - 复用 SubAgentToolAdapter 拆分 LLM 可见层和控制面。
#   - 让单数据集失败降级为安全错误结果，不污染其它数据集的 capsule。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.services.subagent_tool_adapter import (
    SubAgentInvocation,
    SubAgentToolAdapter,
    SubAgentToolResult,
)


class SubAgentFanOutInvocation(SubAgentInvocation):
    """fan-out 单个数据集调用上下文。"""

    model_config = ConfigDict(extra="forbid")


class SubAgentFanOutResult(BaseModel):
    """fan-out 聚合结果，保留每个数据集的双层出参。"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    results: list[SubAgentToolResult] = Field(default_factory=list)
    control_planes: list[dict[str, Any]] = Field(default_factory=list)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


InvokeFinalState = Callable[[SubAgentFanOutInvocation], Awaitable[dict[str, Any]]]


class SubAgentFanOutOrchestrator:
    """控制 fan-out 并发和局部失败隔离，不承担 LeadAgent 规划职责。"""

    def __init__(
        self,
        *,
        invoke_final_state: InvokeFinalState,
        adapter: SubAgentToolAdapter | None = None,
        max_parallel: int | None = None,
    ) -> None:
        self.invoke_final_state = invoke_final_state
        self.adapter = adapter or SubAgentToolAdapter()
        self.max_parallel = int(
            max_parallel
            if max_parallel is not None
            else getattr(get_settings(), "SUBAGENT_FANOUT_MAX_PARALLEL", 3)
        )

    async def run(
        self,
        invocations: list[SubAgentFanOutInvocation],
    ) -> SubAgentFanOutResult:
        semaphore = asyncio.Semaphore(max(1, self.max_parallel))

        async def _run_one(invocation: SubAgentFanOutInvocation) -> SubAgentToolResult:
            async with semaphore:
                try:
                    final_state = await self.invoke_final_state(invocation)
                except TimeoutError as exc:
                    final_state = {"error": f"timeout: {exc}"}
                except Exception as exc:
                    final_state = {"error": str(exc)}
                return self.adapter.assemble_from_final_state(invocation, final_state)

        results = await asyncio.gather(*[_run_one(invocation) for invocation in invocations])
        control_planes = [
            result.control_plane.model_dump(exclude={"raw_error"})
            for result in results
        ]
        return SubAgentFanOutResult(
            results=list(results),
            control_planes=control_planes,
            trace_metadata={
                "dataset_count": len(results),
                "statuses": [result.llm_visible.status.value for result in results],
            },
        )

    def render_for_llm(self, result: SubAgentFanOutResult) -> str:
        return "\n".join(
            self.adapter.render_for_llm(item)
            for item in result.results
        )
