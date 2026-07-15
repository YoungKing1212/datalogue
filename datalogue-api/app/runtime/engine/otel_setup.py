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


def setup_runtime_tracing(settings: Settings, *, app: Any | None = None) -> None:
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

        resource_attributes: dict[str, Any] = {
            SERVICE_NAME: settings.AGENTSCOPE_OTEL_SERVICE_NAME,
            "deployment.environment.name": settings.APP_ENV,
        }
        if settings.AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME:
            # Phoenix 按 OpenInference 项目属性归档 trace；不依赖 Phoenix SDK 注册新的 Provider。
            resource_attributes["openinference.project.name"] = (
                settings.AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME
            )
        resource = Resource.create(resource_attributes)
        provider = TracerProvider(resource=resource)

        if settings.AGENTSCOPE_OTEL_LOGGING_ENABLED:
            _setup_logging_exporter(provider, settings)

        if settings.AGENTSCOPE_OTEL_EXPORTER_ENABLED and settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT:
            _setup_otlp_exporter(provider, settings)

        trace.set_tracer_provider(provider)
        if app is not None:
            _instrument_http_boundaries(app)
        logger.info(
            "AgentScope OTel tracing initialized (logging=%s, exporter=%s).",
            "enabled" if settings.AGENTSCOPE_OTEL_LOGGING_ENABLED else "disabled",
            "enabled" if settings.AGENTSCOPE_OTEL_EXPORTER_ENABLED else "disabled",
        )
    except ImportError:
        logger.warning("opentelemetry packages not installed; AgentScope OTel tracing skipped.")
    except Exception:
        logger.exception("Failed to initialize AgentScope OTel tracing.")


def runtime_otel_enabled() -> bool:
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

        headers = _otlp_exporter_headers(settings)
        if not settings.AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN:
            # 不打印 token 或配置对象，避免意外把部署机密写入日志。
            logger.warning("OTLP exporter configured without an authorization token.")
        exporter = OTLPSpanExporter(
            endpoint=settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT,
            headers=headers or None,
            # Phoenix 自建 gRPC collector 走 Docker 内网/宿主机回环时没有 TLS；显式关闭 TLS
            # 才不会把明文 gRPC 响应误当作错误证书。公网 collector 必须保留默认安全连接。
            insecure=settings.AGENTSCOPE_OTEL_EXPORTER_INSECURE,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(
            "OTLP exporter configured (endpoint=%s).", settings.AGENTSCOPE_OTEL_EXPORTER_ENDPOINT
        )
    except ImportError:
        logger.warning("opentelemetry-exporter-otlp not installed; OTLP export skipped.")
    except Exception:
        logger.exception("Failed to configure OTLP exporter.")


def _otlp_exporter_headers(settings: Settings) -> list[tuple[str, str]]:
    """构造 Phoenix gRPC 认证 metadata；该函数不记录任何部署机密。"""

    headers: list[tuple[str, str]] = []
    if settings.AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN:
        # Phoenix gRPC collector 要求小写 authorization metadata；值不参与日志输出。
        headers.append(("authorization", f"Bearer {settings.AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN}"))
    # x-project-name 仅适用于 Phoenix 的 OTLP HTTP collector；当前 gRPC 方案通过
    # setup_runtime_tracing 中的 openinference.project.name Resource 属性完成项目路由。
    return headers


def _instrument_http_boundaries(app: Any) -> None:
    """为主 FastAPI 与内部 HTTPX 调用自动传递 W3C traceparent。"""

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        logger.warning(
            "OTel FastAPI/HTTPX instrumentation not installed; HTTP trace propagation skipped."
        )
    except Exception:
        # 观测初始化不允许阻断 API 启动；重复初始化等问题留给日志排查。
        logger.exception("Failed to instrument FastAPI/HTTPX tracing boundaries.")


def _setup_logging_exporter(provider: Any, settings: Settings) -> None:
    """配置只写后端日志的 span exporter，不外发到 collector。"""

    try:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        provider.add_span_processor(
            SimpleSpanProcessor(
                _LoggingSpanExporter(service_name=settings.AGENTSCOPE_OTEL_SERVICE_NAME)
            )
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
            if not logger.isEnabledFor(logging.DEBUG):
                continue
            logger.debug(
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
    """把 ReadableSpan 转成精简的可 grep JSON payload。

    只保留排障定位必需字段：span 名称、耗时、状态码、token 用量。
    模型消息、工具入参和工具原始输出不进入 span 日志。
    """

    context = span.get_span_context()
    status = getattr(span, "status", None)
    attributes: dict[str, Any] = dict(getattr(span, "attributes", {}) or {})
    start_time = getattr(span, "start_time", None)
    end_time = getattr(span, "end_time", None)
    duration_ms: int | None = None
    if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
        duration_ms = (end_time - start_time) // 1_000_000  # ns → ms（截断）

    payload: dict[str, Any] = {
        "service": service_name,
        "name": getattr(span, "name", None),
        "trace_id": _hex_id(getattr(context, "trace_id", None), width=32),
        "span_id": _hex_id(getattr(context, "span_id", None), width=16),
        "duration_ms": duration_ms,
        "status": str(getattr(status, "status_code", "")) if status else None,
    }
    # 只保留 token 用量，其余 attributes 丢弃
    usage: dict[str, int] = {}
    for key, value in attributes.items():
        key_text = str(key)
        if key_text.startswith("gen_ai.usage.") and isinstance(value, (int, float)):
            usage[key_text.replace("gen_ai.usage.", "")] = int(value)
    if usage:
        payload["usage"] = usage
    return {k: v for k, v in payload.items() if v is not None}


def _hex_id(value: Any, *, width: int) -> str | None:
    if not isinstance(value, int) or value == 0:
        return None
    return f"{value:0{width}x}"
