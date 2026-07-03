# ============================================================
# File Name   : tracing.py
# Description:
#   AgentScope OpenTelemetry tracing 启动配置。
#
# Responsibilities:
#   - 在配置 OTLP endpoint 或显式启用时安装全局 TracerProvider。
#   - 为 AgentScope TracingMiddleware 提供可导出的 OpenTelemetry 后端。
#   - 默认保持无外部副作用，避免本地开发无 collector 时产生噪声。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GrpcOTLPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HttpOTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ReadableSpan,
    SimpleSpanProcessor,
    SpanExportResult,
    SpanExporter,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)
span_logger = logging.getLogger(f"{__name__}.spans")

_CONFIGURED = False
_CONFIGURED_PROVIDER: TracerProvider | None = None


def configure_agentscope_otel() -> bool:
    """按环境配置初始化 OTel；返回 True 表示 AgentScope tracing 可导出。"""

    global _CONFIGURED, _CONFIGURED_PROVIDER
    if _CONFIGURED:
        return True

    settings = get_settings()
    endpoint = (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()
    exporter_name = (getattr(settings, "OTEL_TRACES_EXPORTER", "otlp") or "otlp").strip().lower()
    if exporter_name in {"none", "off", "disabled"}:
        return False
    enabled = bool(settings.OTEL_TRACES_ENABLED or endpoint)
    if not enabled:
        return False

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "deployment.environment": settings.APP_ENV,
        }
    )
    provider = TracerProvider(resource=resource)
    _install_span_processor(
        provider=provider,
        exporter_name=exporter_name,
        protocol=settings.OTEL_EXPORTER_OTLP_PROTOCOL,
        endpoint=endpoint or None,
    )

    try:
        trace.set_tracer_provider(provider)
    except Exception as exc:  # pragma: no cover - OTel SDK 对重复设置的行为依赖版本。
        logger.warning("AgentScope OpenTelemetry TracerProvider 初始化失败: %s", exc)
        return False

    _CONFIGURED = True
    _CONFIGURED_PROVIDER = provider
    logger.info(
        "AgentScope OpenTelemetry tracing 已启用: service=%s exporter=%s protocol=%s endpoint=%s",
        settings.OTEL_SERVICE_NAME,
        exporter_name,
        settings.OTEL_EXPORTER_OTLP_PROTOCOL,
        endpoint or "default",
    )
    return True


def shutdown_agentscope_otel() -> None:
    """应用退出时尽量 flush OTel batch processor。"""

    global _CONFIGURED_PROVIDER
    provider = _CONFIGURED_PROVIDER
    if provider is None:
        return
    try:
        provider.shutdown()
    except Exception as exc:  # pragma: no cover - shutdown 失败不能影响应用退出。
        logger.warning("AgentScope OpenTelemetry TracerProvider 关闭失败: %s", exc)
    finally:
        _CONFIGURED_PROVIDER = None


def _build_exporter(*, protocol: str, endpoint: str | None):
    normalized = (protocol or "http/protobuf").strip().lower()
    if normalized in {"grpc", "otlp/grpc"}:
        return GrpcOTLPSpanExporter(endpoint=endpoint, insecure=True)
    return HttpOTLPSpanExporter(endpoint=endpoint)


def _install_span_processor(
    *,
    provider: TracerProvider,
    exporter_name: str,
    protocol: str,
    endpoint: str | None,
) -> None:
    if exporter_name == "logger":
        # 本地开发模式：不连接 collector，span 结束后直接写入应用日志。
        provider.add_span_processor(SimpleSpanProcessor(LoggingSpanExporter()))
        return
    provider.add_span_processor(
        BatchSpanProcessor(_build_exporter(protocol=protocol, endpoint=endpoint))
    )


class LoggingSpanExporter(SpanExporter):
    """把 OTel span 摘要写入 Python logger，不导出到外部服务。"""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            payload = _span_log_payload(span)
            span_logger.info("[agentscope.otel.span] %s", payload)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def _span_log_payload(span: ReadableSpan) -> dict[str, Any]:
    context = span.get_span_context()
    parent = span.parent
    return {
        "name": span.name,
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
        "parent_span_id": format(parent.span_id, "016x") if parent else None,
        "status": getattr(span.status, "status_code", None).name,
        "attributes": _safe_span_attributes(dict(span.attributes or {})),
    }


def _safe_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        text_key = str(key)
        lowered = text_key.lower()
        if any(token in lowered for token in ("sql", "schema", "raw_rows", "compiled_query_ref")):
            safe[text_key] = "<redacted>"
            continue
        safe[text_key] = _compact_attribute_value(value)
    return safe


def _compact_attribute_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 300:
        return f"{value[:300]}..."
    if isinstance(value, (list, tuple)):
        return [_compact_attribute_value(item) for item in value[:20]]
    return value
