# ============================================================
# File Name   : otel_setup.py
# Description:
#   AgentScope OpenTelemetry tracing 初始化与状态查询。
#
#   WARNING: AgentScope TracingMiddleware 会将模型请求/响应内容
#   （messages、tools schema、模型输出）写入 span 属性。一旦开启
#   OTLP exporter，这些内容会离开本地进入集中式 collector。
#   默认所有开关关闭，开发/排障按需短时间打开。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)


def setup_agentscope_tracing(settings: Settings) -> None:
    """根据配置初始化 AgentScope OTel TracerProvider。

    仅在 AGENTSCOPE_OTEL_TRACING_ENABLED=true 时生效。
    默认把 span 写入后端日志；若同时配置了
    AGENTSCOPE_OTEL_EXPORTER_ENABLED=true 和 endpoint，则额外创建
    OTLPSpanExporter 外发 span。

    注意：开启 exporter 会将模型请求/响应内容外发到 collector。
    """
    if not settings.AGENTSCOPE_OTEL_TRACING_ENABLED:
        logger.debug("AgentScope OTel tracing is disabled.")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        resource = Resource.create({SERVICE_NAME: settings.AGENTSCOPE_OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)

        if settings.AGENTSCOPE_OTEL_LOGGING_ENABLED:
            _setup_logging_exporter(provider, settings)

        if settings.AGENTSCOPE_OTEL_EXPORTER_ENABLED and settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT:
            _setup_otlp_exporter(provider, settings)

        trace.set_tracer_provider(provider)
        logger.info(
            "AgentScope OTel tracing initialized (logging=%s, exporter=%s).",
            "enabled" if settings.AGENTSCOPE_OTEL_LOGGING_ENABLED else "disabled",
            "enabled" if settings.AGENTSCOPE_OTEL_EXPORTER_ENABLED else "disabled",
        )
    except ImportError:
        logger.warning(
            "opentelemetry packages not installed; AgentScope OTel tracing skipped."
        )
    except Exception:
        logger.exception("Failed to initialize AgentScope OTel tracing.")


def agentscope_otel_enabled() -> bool:
    """返回当前是否有有效的 TracerProvider（非 no-op proxy）。

    可在中间件中用于判断是否设置自定义 span 属性。
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        provider = trace.get_tracer_provider()
        return isinstance(provider, TracerProvider)
    except ImportError:
        return False


def _setup_otlp_exporter(provider: Any, settings: Settings) -> None:
    """配置 OTLP span exporter。"""
    try:
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTLP exporter configured (endpoint=%s).", settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT)
    except ImportError:
        logger.warning("opentelemetry-exporter-otlp not installed; OTLP export skipped.")
    except Exception:
        logger.exception("Failed to configure OTLP exporter.")


def _setup_logging_exporter(provider: Any, settings: Settings) -> None:
    """配置只写后端日志的 span exporter，不外发到 collector。"""

    try:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        provider.add_span_processor(
            SimpleSpanProcessor(_LoggingSpanExporter(service_name=settings.AGENTSCOPE_OTEL_SERVICE_NAME))
        )
        logger.info("AgentScope OTel logging exporter configured.")
    except ImportError:
        logger.warning("opentelemetry-sdk not installed; OTel logging export skipped.")
    except Exception:
        logger.exception("Failed to configure OTel logging exporter.")


class _LoggingSpanExporter:
    """把 OTel span 输出到 Datalogue 后端日志，供本地排障使用。"""

    def __init__(self, *, service_name: str) -> None:
        self.service_name = service_name

    def export(self, spans: Sequence[Any]) -> Any:
        try:
            from opentelemetry.sdk.trace.export import SpanExportResult
        except ImportError:
            return None

        for span in spans:
            logger.info(
                "[agentscope.otel.span] %s",
                json.dumps(
                    _span_log_payload(span, service_name=self.service_name),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        del timeout_millis
        return True


def _span_log_payload(span: Any, *, service_name: str) -> dict[str, Any]:
    """把 ReadableSpan 转成可 grep 的 JSON payload。"""

    context = span.get_span_context()
    parent = getattr(span, "parent", None)
    status = getattr(span, "status", None)
    attributes = dict(getattr(span, "attributes", {}) or {})
    return {
        "service_name": service_name,
        "name": getattr(span, "name", None),
        "trace_id": _hex_id(getattr(context, "trace_id", None), width=32),
        "span_id": _hex_id(getattr(context, "span_id", None), width=16),
        "parent_span_id": _hex_id(getattr(parent, "span_id", None), width=16) if parent else None,
        "status_code": str(getattr(status, "status_code", "")) if status else None,
        "status_description": getattr(status, "description", None) if status else None,
        "start_time": getattr(span, "start_time", None),
        "end_time": getattr(span, "end_time", None),
        # 本地 span 日志只保留可定位字段；模型消息、工具入参和工具原始输出由专门的安全日志处理。
        "attributes": _safe_span_attributes(attributes),
    }


def _safe_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """过滤 OTel span attributes，避免把 messages/tools/output 原文写入普通后端日志。"""

    blocked_fragments = ("message", "messages", "prompt", "input", "output", "tools", "tool_calls")
    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        key_text = str(key)
        lowered = key_text.lower()
        if lowered.startswith("gen_ai.usage."):
            safe[key_text] = value
            continue
        if any(fragment in lowered for fragment in blocked_fragments):
            continue
        safe[key_text] = value
    return safe


def _hex_id(value: Any, *, width: int) -> str | None:
    if not isinstance(value, int) or value == 0:
        return None
    return f"{value:0{width}x}"
