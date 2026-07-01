# ============================================================
# File Name   : tracer.py
# Description:
#   本地可观测兼容入口。
#
# Responsibilities:
#   - 保留主链对 tracer/span/generation/feedback 的调用签名。
#   - 在暂不建设 Trace 的阶段避免任何外部 SDK、网络写入或后台 flush。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings
from app.services.observability.context import ObservabilityRequestContext
from app.services.observability.masking import sanitize_sql, sanitize_text
from app.utils.token import estimate_messages_tokens, estimate_text_tokens


def build_observability_trace_url(
    *,
    base_url: str | None,
    project_id: str | None,
    trace_id: str | None,
) -> str | None:
    """当前不建设 Trace 详情页，始终不返回外部跳转地址。"""

    return None


@dataclass
class ObservabilityTraceContext:
    """问数请求的本地兼容上下文。"""

    trace_id: str | None
    session_id: str
    conversation_id: int | None
    dataset_id: int | None
    user_id: str | None
    tenant_id: str
    question: str
    execution_path: str = "unknown"
    enabled: bool = False
    active: bool = False
    environment: str = "local"
    release: str = "local"
    prompt_label: str = "local"
    base_url: str | None = None
    project_id: str | None = None
    prompt_versions: dict[str, Any] = field(default_factory=dict)
    root_handle: Any = None
    root_manager: Any = None
    span_handles: dict[str, Any] = field(default_factory=dict)
    span_managers: dict[str, Any] = field(default_factory=dict)

    def request_context(self) -> ObservabilityRequestContext:
        """转换为 contextvars 使用的轻量上下文。"""

        return ObservabilityRequestContext(
            trace_id=self.trace_id,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            dataset_id=self.dataset_id,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            execution_path=self.execution_path,
            release=self.release,
            prompt_label=self.prompt_label,
            base_url=None,
            project_id=None,
            trace_url=None,
            enabled=False,
            active=False,
            prompt_versions=self.prompt_versions,
            parent_observation_id=None,
        )

    def observability_payload(self) -> dict[str, Any]:
        """返回禁用状态，避免前端误以为存在 Trace 后端。"""

        return {
            "enabled": False,
            "active": False,
            "environment": self.environment,
            "release": self.release,
            "prompt_label": self.prompt_label,
            "base_url": None,
            "project_id": None,
            "trace_url": None,
        }

    @property
    def trace_url(self) -> str | None:
        return None


@dataclass
class GenerationObservationHandle:
    """兼容旧调用签名的 generation 句柄。"""

    manager: Any = None
    generation: Any = None
    usage_source: str = "disabled"
    technical_name: str = ""


class DatalogueTracer:
    """无外部副作用的 tracer 兼容层。"""

    def __init__(self, settings: Settings, client: Any | None = None):
        self.settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return False

    def create_trace_context(
        self,
        *,
        conversation_id: int | None,
        dataset_id: int | None,
        user_id: str | None,
        tenant_id: str,
        question: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ObservabilityTraceContext:
        """创建本地上下文；不分配 trace id，不触发外部写入。"""

        return ObservabilityTraceContext(
            trace_id=None,
            session_id=session_id or f"datalogue-conv-{conversation_id or 'anonymous'}",
            conversation_id=conversation_id,
            dataset_id=dataset_id,
            user_id=user_id,
            tenant_id=tenant_id,
            question=question,
        )

    def start_span(
        self,
        context: ObservabilityTraceContext | None,
        *,
        node: str,
        display_name: str,
        input_payload: dict[str, Any] | None = None,
        trace_tags: list[str] | None = None,
    ) -> None:
        return None

    def end_span(
        self,
        context: ObservabilityTraceContext | None,
        *,
        node: str,
        output_payload: dict[str, Any] | None = None,
        elapsed_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        return None

    def record_generation(
        self,
        *,
        name: str,
        model: str | None,
        messages: list[Any],
        output: Any,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None

    def start_generation(
        self,
        *,
        name: str,
        model: str | None,
        messages: list[Any],
        output: Any = None,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationObservationHandle | None:
        return None

    def end_generation(
        self,
        handle: GenerationObservationHandle | None,
        *,
        output: Any,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        completion_start_time: datetime | None = None,
    ) -> None:
        return None

    def update_trace_output(
        self,
        context: ObservabilityTraceContext | None,
        *,
        output: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if context and metadata:
            context.prompt_versions.update(metadata.get("prompt_versions") or {})

    def score_trace(
        self,
        *,
        trace_id: str | None,
        name: str,
        value: Any,
        data_type: str = "NUMERIC",
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        return False

    def flush(self) -> None:
        return None

    def close_trace(self, context: ObservabilityTraceContext | None) -> None:
        if not context:
            return
        context.span_managers.clear()
        context.span_handles.clear()


def _message_to_dict(message: Any) -> dict[str, Any]:
    role = getattr(message, "type", None) or getattr(message, "role", None) or "message"
    content = getattr(message, "content", message)
    return {"role": role, "content": sanitize_text(content, max_length=4000)}


def _observability_usage_details(
    usage: dict[str, Any] | None,
    *,
    messages: list[Any] | None = None,
    output: Any = None,
) -> tuple[dict[str, int], str]:
    """保留 token 估算工具，供旧单测和本地统计复用。"""

    usage = usage or {}
    input_tokens = (
        usage.get("input") or usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    )
    output_tokens = (
        usage.get("output") or usage.get("output_tokens") or usage.get("completion_tokens") or 0
    )
    total_tokens = usage.get("total") or usage.get("total_tokens") or 0
    source = str(usage.get("usage_source") or "")
    if source not in {"provider", "estimated"}:
        source = "provider" if input_tokens or output_tokens or total_tokens else "estimated"
    if not input_tokens and messages is not None:
        input_tokens = estimate_messages_tokens(messages)
    if not output_tokens and output is not None:
        output_tokens = estimate_text_tokens(output)
    if not total_tokens:
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    return (
        {
            "input": int(input_tokens or 0),
            "output": int(output_tokens or 0),
            "total": int(total_tokens or 0),
        },
        source,
    )


def sanitize_trace_sql(sql: Any) -> Any:
    """供外部模块复用的 SQL 脱敏入口。"""

    return sanitize_sql(sql)


@lru_cache
def get_observability_tracer() -> DatalogueTracer:
    """返回进程级 tracer 兼容单例。"""

    return DatalogueTracer(get_settings())
