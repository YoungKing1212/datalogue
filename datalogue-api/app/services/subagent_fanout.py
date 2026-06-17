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

DATASET_FANOUT_TOOL_NAMES = {
    "dataset_query",
    "dataset_subagent",
    "subagent_dispatch",
    "subagent_query",
}


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


def _tool_name(tool_call: dict[str, Any]) -> str:
    return str(
        tool_call.get("tool")
        or tool_call.get("name")
        or tool_call.get("type")
        or ""
    ).strip()


def _tool_args(tool_call: dict[str, Any]) -> dict[str, Any]:
    for key in ("arguments", "args", "input", "payload", "parameters"):
        value = tool_call.get(key)
        if isinstance(value, dict):
            return value
    return tool_call


def _coerce_dataset_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_dataset_fanout_invocations(
    planned_tool_calls: list[dict[str, Any]] | None,
    *,
    fallback_question: str,
    resolved_question: str | None = None,
    turn_index: int | None = None,
    prior_capsule_status: dict[str, Any] | None = None,
) -> list[SubAgentFanOutInvocation]:
    """从 LeadAgent tool calls 中解析多数据集 fan-out 调用。

    v1 只接受明确携带 dataset_id 的 dataset 查询调用；有效调用不足两个时返回空，
    由 chat 主链路回退当前单数据集执行，避免根据普通 subagent_dispatch 猜测 fan-out。
    """

    invocations: list[SubAgentFanOutInvocation] = []
    seen_dataset_ids: set[int] = set()
    for item in planned_tool_calls or []:
        if not isinstance(item, dict):
            continue
        name = _tool_name(item)
        if name not in DATASET_FANOUT_TOOL_NAMES:
            continue
        args = _tool_args(item)
        dataset_id = _coerce_dataset_id(args.get("dataset_id"))
        if dataset_id is None or dataset_id in seen_dataset_ids:
            continue
        question = str(
            args.get("question")
            or args.get("query")
            or resolved_question
            or fallback_question
        ).strip()
        invocations.append(
            SubAgentFanOutInvocation(
                dataset_id=dataset_id,
                question=question or fallback_question,
                resolved_question=resolved_question or question or fallback_question,
                turn_index=turn_index,
                prior_capsule_status=prior_capsule_status or {},
            )
        )
        seen_dataset_ids.add(dataset_id)
    return invocations if len(invocations) >= 2 else []


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


class SubAgentFanOutAnswerSynthesizer:
    """把多个 LLMVisible 摘要合成为最终回答，不接触控制面或原始结果。"""

    def synthesize(self, result: SubAgentFanOutResult) -> str:
        lines = ["已完成多数据集查询："]
        for item in result.results:
            visible = item.llm_visible
            status = visible.status.value
            summary = visible.display_summary or visible.error_summary or visible.clarification_question
            lines.append(f"- 数据集 {visible.dataset_id}: {status}")
            if summary:
                lines.append(f"  {summary}")
            refs = [
                ref
                for ref in (visible.result_ref, visible.report_ref)
                if isinstance(ref, str) and ref
            ]
            if refs:
                lines.append(f"  refs: {', '.join(refs)}")
        return "\n".join(lines)
