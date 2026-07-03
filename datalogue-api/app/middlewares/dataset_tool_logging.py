# ============================================================
# File Name   : dataset_tool_logging.py
# Description:
#   DatasetAgent ToolBase 调用链的 AgentScope 2.0 ToolMiddleware 日志。
#
# Responsibilities:
#   - 通过 ToolMiddlewareBase.on_tool_call 拦截 DatasetAgent 原子工具调用。
#   - 只记录工具调用和工具结果的安全摘要，不记录 SQL、schema、raw rows 或物理字段明细。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from agentscope.tool import ToolBase, ToolChunk, ToolMiddlewareBase

from app.middlewares.safe_log_summary import (
    extract_text_outputs,
    parse_json_object,
    summarize_mapping,
)


logger = logging.getLogger(__name__)


class DatasetRuntimeToolLoggingMiddleware(ToolMiddlewareBase):
    """AgentScope 2.0 ToolMiddleware：记录 DatasetAgent ToolBase 调用安全摘要。"""

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
        """拦截 ToolBase 调用；只记录安全摘要，不记录真实入参或输出正文。"""

        self._log(
            "call",
            tool=tool.name,
            dataset_id=self.dataset_id,
            conversation_id=self.conversation_id,
            trace_id=self.trace_id,
            **summarize_mapping(input_kwargs, prefix="input"),
        )
        async for chunk in next_handler(**input_kwargs):
            self._log(
                "result",
                tool=tool.name,
                dataset_id=self.dataset_id,
                conversation_id=self.conversation_id,
                trace_id=self.trace_id,
                state=str(chunk.state),
                **self._summarize_tool_chunk(chunk),
            )
            yield chunk

    @classmethod
    def _summarize_tool_chunk(cls, chunk: ToolChunk) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for payload in extract_text_outputs(chunk.content):
            parsed = parse_json_object(payload)
            if parsed:
                merged.update(parsed)
        if not merged:
            return {"output_format": "opaque"}
        return summarize_mapping(
            merged,
            prefix="output",
            output_format="json",
        )

    @staticmethod
    def _log(checkpoint: str, **fields: Any) -> None:
        safe_fields = {key: value for key, value in fields.items() if value is not None}
        logger.info(
            "[agentscope.dataset_tool.%s] %s",
            checkpoint,
            json.dumps(safe_fields, ensure_ascii=False, default=str),
        )
