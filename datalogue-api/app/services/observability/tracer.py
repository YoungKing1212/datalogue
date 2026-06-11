# ============================================================
# File Name   : tracer.py
# Description:
#   Datalogue 对 Langfuse Python SDK v4 的统一封装。
#
# Responsibilities:
#   - 统一创建 trace、span、generation 和 score。
#   - 在 Langfuse 缺失或异常时降级为 no-op，不影响问数主流程。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

import logging
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from app.core.config import Settings, get_settings
from app.services.observability.context import ObservabilityRequestContext
from app.services.observability.fallback import LangfuseHealthCheck
from app.services.observability.masking import sanitize_payload, sanitize_sql, sanitize_text

logger = logging.getLogger(__name__)


def build_langfuse_trace_url(
    *,
    base_url: str | None,
    project_id: str | None,
    trace_id: str | None,
) -> str | None:
    """按 Langfuse Web 路由生成 trace 详情页地址。"""

    if not base_url or not project_id or not trace_id:
        return None
    clean_base = base_url.rstrip("/")
    return (
        f"{clean_base}/project/{quote(str(project_id), safe='')}"
        f"/traces/{quote(str(trace_id), safe='')}"
    )


@dataclass
class ObservabilityTraceContext:
    """Datalogue 内部 trace 上下文。"""

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
    environment: str = "dev"
    release: str = "local"
    prompt_label: str = "production"
    base_url: str | None = None
    project_id: str | None = None
    prompt_versions: dict[str, Any] = field(default_factory=dict)
    root_handle: Any = None
    root_manager: AbstractContextManager | None = None
    span_handles: dict[str, Any] = field(default_factory=dict)
    span_managers: dict[str, AbstractContextManager] = field(default_factory=dict)

    def request_context(self) -> ObservabilityRequestContext:
        """转换为可放入 contextvars 的轻量上下文。"""

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
            base_url=self.base_url,
            project_id=self.project_id,
            trace_url=self.trace_url,
            enabled=self.enabled,
            active=self.active,
            prompt_versions=self.prompt_versions,
        )

    def observability_payload(self) -> dict[str, Any]:
        """返回 API final payload 中的观测状态。"""

        return {
            "enabled": self.enabled,
            "active": self.active,
            "environment": self.environment,
            "release": self.release,
            "prompt_label": self.prompt_label,
            "base_url": self.base_url,
            "project_id": self.project_id,
            "trace_url": self.trace_url,
        }

    @property
    def trace_url(self) -> str | None:
        """返回 Langfuse Web trace 详情页地址。"""

        return build_langfuse_trace_url(
            base_url=self.base_url,
            project_id=self.project_id,
            trace_id=self.trace_id,
        )


class DatalogueTracer:
    """统一可观测入口，屏蔽 Langfuse SDK v4 的直接依赖。"""

    def __init__(self, settings: Settings, client: Any | None = None):
        self.settings = settings
        self._client = client
        self._health = LangfuseHealthCheck()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.LANGFUSE_ENABLED)

    def create_trace_context(
        self,
        *,
        conversation_id: int | None,
        dataset_id: int | None,
        user_id: str | None,
        tenant_id: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> ObservabilityTraceContext:
        """创建一次用户问数根 trace。"""

        session_id = f"datalogue-conv-{conversation_id or 'anonymous'}"
        fallback_trace_id = f"dlg-{uuid.uuid4().hex}"
        context = ObservabilityTraceContext(
            trace_id=fallback_trace_id,
            session_id=session_id,
            conversation_id=conversation_id,
            dataset_id=dataset_id,
            user_id=user_id,
            tenant_id=tenant_id,
            question=question,
            enabled=self.enabled,
            environment=self.settings.LANGFUSE_ENVIRONMENT,
            release=self.settings.LANGFUSE_RELEASE,
            prompt_label=self.settings.LANGFUSE_PROMPT_LABEL,
            base_url=self.settings.LANGFUSE_BASE_URL or self.settings.LANGFUSE_HOST,
            project_id=self.settings.LANGFUSE_PROJECT_ID,
        )
        if not self.enabled or not self._health.allow_request():
            return context

        client = self._get_client()
        if client is None:
            return context

        trace_metadata = sanitize_payload(
            {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "dataset_id": dataset_id,
                "environment": self.settings.LANGFUSE_ENVIRONMENT,
                "release": self.settings.LANGFUSE_RELEASE,
                **(metadata or {}),
            }
        )
        try:
            manager = client.start_as_current_observation(
                name="user_query",
                input=sanitize_text(question, max_length=self.settings.LANGFUSE_MAX_TEXT_LENGTH),
                metadata=trace_metadata,
            )
            root = manager.__enter__()
            self._safe_call(
                root,
                "update_trace",
                user_id=f"{tenant_id}:{user_id or 'anonymous'}",
                session_id=session_id,
                tags=[
                    f"tenant:{tenant_id}",
                    f"env:{self.settings.LANGFUSE_ENVIRONMENT}",
                    f"release:{self.settings.LANGFUSE_RELEASE}",
                ],
                metadata=trace_metadata,
            )
            context.root_handle = root
            context.root_manager = manager
            context.trace_id = (
                getattr(root, "trace_id", None)
                or getattr(root, "id", None)
                or getattr(root, "traceId", None)
                or fallback_trace_id
            )
            context.active = True
            self._health.record_success()
        except Exception as exc:
            logger.warning("Langfuse trace 创建失败，已降级: %s", exc)
            self._health.record_failure()
        return context

    def start_span(
        self,
        context: ObservabilityTraceContext | None,
        *,
        node: str,
        display_name: str,
        input_payload: dict[str, Any] | None = None,
    ) -> None:
        """开始记录一个 LangGraph 节点 span。"""

        if not context or not context.active:
            return
        client = self._get_client()
        if client is None:
            return
        try:
            manager = client.start_as_current_observation(
                name=f"node.{node}",
                input=sanitize_payload(input_payload or {}),
                metadata={"node": node, "display_name": display_name},
            )
            handle = manager.__enter__()
            context.span_managers[node] = manager
            context.span_handles[node] = handle
        except Exception as exc:
            logger.warning("Langfuse span 开始失败 node=%s: %s", node, exc)
            self._health.record_failure()

    def end_span(
        self,
        context: ObservabilityTraceContext | None,
        *,
        node: str,
        output_payload: dict[str, Any] | None = None,
        elapsed_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """结束节点 span。"""

        if not context or not context.active:
            return
        handle = context.span_handles.pop(node, None)
        manager = context.span_managers.pop(node, None)
        metadata = {"elapsed_ms": elapsed_ms, "status": "error" if error else "success"}
        if error:
            metadata["error"] = sanitize_text(error, max_length=1000)
        try:
            self._safe_call(
                handle,
                "update",
                output=sanitize_payload(output_payload or {}),
                metadata=metadata,
            )
        finally:
            if manager:
                self._exit_manager(manager)

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
        """记录一次 LLM generation。依赖当前 Langfuse active observation。"""

        if not self.enabled:
            return
        client = self._get_client()
        if client is None:
            return
        try:
            manager = client.start_as_current_observation(
                name=name,
                as_type="generation",
                model=model,
                input=sanitize_payload([_message_to_dict(m) for m in messages]),
                metadata=sanitize_payload(metadata or {}),
            )
            generation = manager.__enter__()
            self._safe_call(
                generation,
                "update",
                output=sanitize_text(output, max_length=self.settings.LANGFUSE_MAX_TEXT_LENGTH),
                usage_details=usage or {},
            )
            manager.__exit__(None, None, None)
        except Exception as exc:
            logger.warning("Langfuse generation 记录失败 name=%s: %s", name, exc)
            self._health.record_failure()

    def update_trace_output(
        self,
        context: ObservabilityTraceContext | None,
        *,
        output: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """更新根 trace 输出。"""

        if not context:
            return
        if metadata:
            context.prompt_versions.update(metadata.get("prompt_versions") or {})
        if not context.active:
            return
        self._safe_call(
            context.root_handle,
            "update",
            output=sanitize_text(output, max_length=self.settings.LANGFUSE_MAX_TEXT_LENGTH),
            metadata=sanitize_payload(metadata or {}),
        )

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
        """给 trace 写 score。失败返回 False，由调用方决定 partial success。"""

        if not self.enabled or not trace_id:
            return False
        client = self._get_client()
        if client is None:
            return False
        try:
            # v4 active observation 支持 score；离线 feedback 场景优先走 client.create_score。
            if hasattr(client, "create_score"):
                client.create_score(
                    trace_id=trace_id,
                    name=name,
                    value=value,
                    data_type=data_type,
                    comment=sanitize_text(comment, max_length=1000) if comment else None,
                    metadata=sanitize_payload(metadata or {}),
                )
            elif hasattr(client, "score"):
                client.score(
                    trace_id=trace_id,
                    name=name,
                    value=value,
                    data_type=data_type,
                    comment=sanitize_text(comment, max_length=1000) if comment else None,
                    metadata=sanitize_payload(metadata or {}),
                )
            else:
                return False
            return True
        except Exception as exc:
            logger.warning("Langfuse score 写入失败 trace_id=%s name=%s: %s", trace_id, name, exc)
            self._health.record_failure()
            return False

    def flush(self) -> None:
        """短生命周期请求结束时按配置 flush。"""

        if not self.enabled or not self.settings.LANGFUSE_FLUSH_AT_END:
            return
        client = self._get_client()
        if client is None:
            return
        self._safe_call(client, "flush")

    def close_trace(self, context: ObservabilityTraceContext | None) -> None:
        """关闭未结束的 span 和根 trace。"""

        if not context or not context.active:
            return
        for node, manager in list(context.span_managers.items()):
            logger.debug("关闭未结束 Langfuse span: %s", node)
            self._exit_manager(manager)
        context.span_managers.clear()
        context.span_handles.clear()
        if context.root_manager:
            self._exit_manager(context.root_manager)
        self.flush()

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.enabled:
            return None
        try:
            from langfuse import Langfuse  # noqa: PLC0415

            base_url = self.settings.LANGFUSE_BASE_URL or self.settings.LANGFUSE_HOST
            self._client = Langfuse(
                public_key=self.settings.LANGFUSE_PUBLIC_KEY,
                secret_key=self.settings.LANGFUSE_SECRET_KEY,
                base_url=base_url,
            )
            return self._client
        except Exception as exc:
            logger.warning("Langfuse SDK v4 初始化失败，已降级: %s", exc)
            self._health.record_failure()
            return None

    @staticmethod
    def _safe_call(target: Any, method: str, *args, **kwargs):
        if target is None:
            return None
        fn = getattr(target, method, None)
        if not fn:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.debug("Langfuse 方法调用失败 method=%s: %s", method, exc)
            return None

    @staticmethod
    def _exit_manager(manager: AbstractContextManager) -> None:
        try:
            manager.__exit__(None, None, None)
        except Exception as exc:
            logger.debug("Langfuse context manager 关闭失败: %s", exc)


def _message_to_dict(message: Any) -> dict[str, Any]:
    role = getattr(message, "type", None) or getattr(message, "role", None) or "message"
    content = getattr(message, "content", message)
    return {"role": role, "content": sanitize_text(content, max_length=4000)}


def sanitize_trace_sql(sql: Any) -> Any:
    """供外部模块复用的 SQL 脱敏入口。"""

    return sanitize_sql(sql)


@lru_cache
def get_observability_tracer() -> DatalogueTracer:
    """返回进程级 tracer 单例。"""

    return DatalogueTracer(get_settings())
