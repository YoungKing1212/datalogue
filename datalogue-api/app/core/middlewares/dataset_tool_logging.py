# ============================================================
# File Name   : dataset_tool_logging.py
# Description:
#   DatasetAgent ToolBase 调用链的 AgentScope 2.0 ToolMiddleware 兼容壳。
#
# Responsibilities:
#   - 保留旧 runtime 的 ToolMiddleware 挂载边界，避免调用方大面积改动。
#   - 自定义执行日志已切到 OpenTelemetry，由该中间件透传工具调用。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any

from agentscope.tool import ToolBase, ToolChunk, ToolMiddlewareBase


class DatasetRuntimeToolLoggingMiddleware(ToolMiddlewareBase):
    """AgentScope 2.0 ToolMiddleware 兼容壳：执行观测交给 OTel。"""

    def __init__(
        self,
        *,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.dataset_id = dataset_id
        self.conversation_id = conversation_id
        self.trace_id = trace_id

    async def on_tool_call(
        self,
        tool: ToolBase,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator[ToolChunk, None]],
    ) -> AsyncGenerator[ToolChunk, None]:
        """透传 ToolBase 调用；不再输出 Datalogue 自定义执行日志。"""

        del tool
        async for chunk in next_handler(**input_kwargs):
            yield chunk
