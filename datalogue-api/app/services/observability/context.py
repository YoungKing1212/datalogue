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

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator


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


current_observability_context: ContextVar[ObservabilityRequestContext | None] = ContextVar(
    "current_observability_context",
    default=None,
)


@contextmanager
def set_observability_context(
    context: ObservabilityRequestContext | None,
) -> Iterator[ObservabilityRequestContext | None]:
    """临时设置当前请求观测上下文。"""

    token: Token = current_observability_context.set(context)
    try:
        yield context
    finally:
        current_observability_context.reset(token)
