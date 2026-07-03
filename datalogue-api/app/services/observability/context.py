# ============================================================
# File Name   : context.py
# Description:
#   可观测上下文传递工具。
#
# Responsibilities:
#   - 通过 contextvars 在 Chat 流程和节点之间传递 trace 上下文。
#   - 避免业务函数层层增加 Langfuse 参数。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class ObservabilityRequestContext:
    """一次问数请求的观测上下文。"""

    trace_id: str | None
    session_id: str
    conversation_id: int | None
    dataset_id: int | None
    user_id: str | None
    tenant_id: str
    execution_path: str = "unknown"
    release: str = "local"
    prompt_label: str = "production"
    base_url: str | None = None
    project_id: str | None = None
    trace_url: str | None = None
    enabled: bool = False
    active: bool = False
    prompt_versions: dict[str, Any] = field(default_factory=dict)
    parent_observation_id: str | None = None


current_observability_context: ContextVar[ObservabilityRequestContext | None] = ContextVar(
    "current_observability_context",
    default=None,
)


@contextmanager
def set_observability_context(
    context: ObservabilityRequestContext | None,
) -> Iterator[ObservabilityRequestContext | None]:
    """临时设置当前请求观测上下文。

    备注：流式任务入口里通常会通过 async generator 持续产出事件，
    当客户端断开连接时 FastAPI 会调用 `aclose()` 强制关闭它。`aclose` 触发
    的 `GeneratorExit` 清理路径可能落在与 `__enter__` 不同的 asyncio
    task / Context 副本中，此时 `ContextVar.reset(token)` 会抛出
    `ValueError: Token was created in a different Context`。这里捕获该异常
    并降级——清理 task 结束时其 Context 副本会被自然回收，无须显式回退。
    """

    token: Token = current_observability_context.set(context)
    try:
        yield context
    finally:
        try:
            current_observability_context.reset(token)
        except ValueError:
            # 跨 Context 释放，contextvar 由原 task 的生命周期托管
            logger.debug(
                "observability context token 跨 asyncio Context 释放，已忽略 reset 异常",
            )
