# ============================================================
# File Name   : test_agentscope_otel.py
# Description:
#   AgentScope OpenTelemetry 启动配置测试。
#
# Responsibilities:
#   - 验证未显式配置 OTLP 时不会初始化外部 tracing。
#   - 验证配置 OTLP endpoint 后会为 AgentScope TracingMiddleware 安装全局 TracerProvider。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from types import SimpleNamespace
import logging


def test_agentscope_otel_bootstrap_stays_disabled_without_endpoint(monkeypatch):
    from app.middlewares import tracing as agentscope_otel

    agentscope_otel._CONFIGURED = False
    agentscope_otel._CONFIGURED_PROVIDER = None
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(
        agentscope_otel,
        "get_settings",
        lambda: SimpleNamespace(
            APP_ENV="test",
            OTEL_TRACES_ENABLED=False,
            OTEL_SERVICE_NAME="datalogue-api-test",
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
        ),
    )

    assert agentscope_otel.configure_agentscope_otel() is False


def test_agentscope_otel_bootstrap_installs_http_tracer_provider(monkeypatch):
    from app.middlewares import tracing as agentscope_otel

    installed: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, *, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeExporter:
        def __init__(self, *, endpoint):
            self.endpoint = endpoint

    class FakeResource:
        @staticmethod
        def create(payload):
            return payload

    agentscope_otel._CONFIGURED = False
    agentscope_otel._CONFIGURED_PROVIDER = None
    monkeypatch.setattr(agentscope_otel.trace, "set_tracer_provider", lambda provider: installed.setdefault("provider", provider))
    monkeypatch.setattr(agentscope_otel, "TracerProvider", FakeProvider)
    monkeypatch.setattr(agentscope_otel, "BatchSpanProcessor", FakeProcessor)
    monkeypatch.setattr(agentscope_otel, "HttpOTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(agentscope_otel, "Resource", FakeResource)
    monkeypatch.setattr(
        agentscope_otel,
        "get_settings",
        lambda: SimpleNamespace(
            APP_ENV="test",
            OTEL_TRACES_ENABLED=False,
            OTEL_SERVICE_NAME="datalogue-api-test",
            OTEL_TRACES_EXPORTER="otlp",
            OTEL_EXPORTER_OTLP_ENDPOINT="http://collector.test/v1/traces",
            OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
        ),
    )

    assert agentscope_otel.configure_agentscope_otel() is True

    provider = installed["provider"]
    assert provider.resource["service.name"] == "datalogue-api-test"
    assert provider.resource["deployment.environment"] == "test"
    assert provider.processors[0].exporter.endpoint == "http://collector.test/v1/traces"


def test_agentscope_otel_bootstrap_keeps_logger_exporter_disabled_until_explicitly_enabled(monkeypatch):
    from app.middlewares import tracing as agentscope_otel

    installed: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, *, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeResource:
        @staticmethod
        def create(payload):
            return payload

    agentscope_otel._CONFIGURED = False
    agentscope_otel._CONFIGURED_PROVIDER = None
    monkeypatch.setattr(agentscope_otel.trace, "set_tracer_provider", lambda provider: installed.setdefault("provider", provider))
    monkeypatch.setattr(agentscope_otel, "TracerProvider", FakeProvider)
    monkeypatch.setattr(agentscope_otel, "SimpleSpanProcessor", FakeProcessor)
    monkeypatch.setattr(agentscope_otel, "Resource", FakeResource)
    monkeypatch.setattr(
        agentscope_otel,
        "get_settings",
        lambda: SimpleNamespace(
            APP_ENV="test",
            OTEL_TRACES_ENABLED=False,
            OTEL_SERVICE_NAME="datalogue-api-test",
            OTEL_TRACES_EXPORTER="logger",
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
        ),
    )

    assert agentscope_otel.configure_agentscope_otel() is False
    assert installed == {}


def test_agentscope_otel_bootstrap_installs_logger_exporter_when_explicitly_enabled(monkeypatch):
    from app.middlewares import tracing as agentscope_otel

    installed: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, *, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeResource:
        @staticmethod
        def create(payload):
            return payload

    agentscope_otel._CONFIGURED = False
    agentscope_otel._CONFIGURED_PROVIDER = None
    monkeypatch.setattr(agentscope_otel.trace, "set_tracer_provider", lambda provider: installed.setdefault("provider", provider))
    monkeypatch.setattr(agentscope_otel, "TracerProvider", FakeProvider)
    monkeypatch.setattr(agentscope_otel, "SimpleSpanProcessor", FakeProcessor)
    monkeypatch.setattr(agentscope_otel, "Resource", FakeResource)
    monkeypatch.setattr(
        agentscope_otel,
        "get_settings",
        lambda: SimpleNamespace(
            APP_ENV="test",
            OTEL_TRACES_ENABLED=True,
            OTEL_SERVICE_NAME="datalogue-api-test",
            OTEL_TRACES_EXPORTER="logger",
            OTEL_EXPORTER_OTLP_ENDPOINT=None,
            OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
        ),
    )

    assert agentscope_otel.configure_agentscope_otel() is True

    provider = installed["provider"]
    assert provider.processors
    assert isinstance(provider.processors[0].exporter, agentscope_otel.LoggingSpanExporter)


def test_logging_span_exporter_writes_safe_span_summary(caplog):
    from app.middlewares import tracing as agentscope_otel

    class FakeStatusCode:
        name = "OK"

    class FakeStatus:
        status_code = FakeStatusCode()

    class FakeContext:
        trace_id = 1
        span_id = 2

    class FakeParent:
        span_id = 3

    class FakeSpan:
        name = "agent.reply"
        parent = FakeParent()
        status = FakeStatus()
        attributes = {
            "agent.name": "dataset_agent",
            "db.sql": "SELECT * FROM user_logs",
            "schema_context": "secret schema",
            "prompt": "x" * 400,
        }

        @staticmethod
        def get_span_context():
            return FakeContext()

    exporter = agentscope_otel.LoggingSpanExporter()
    with caplog.at_level(logging.INFO, logger="app.middlewares.tracing.spans"):
        result = exporter.export([FakeSpan()])

    assert result is agentscope_otel.SpanExportResult.SUCCESS
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.otel.span]" in logs
    assert "agent.reply" in logs
    assert "dataset_agent" in logs
    assert "<redacted>" in logs
    assert "SELECT" not in logs
    assert "secret schema" not in logs
    assert "x" * 350 not in logs
