# ============================================================
# File Name   : otel_setup.py
# Description:
#   AgentScope runtime OpenTelemetry 初始化 facade。
#
# Responsibilities:
#   - 暴露 setup_runtime_tracing 作为新目录的稳定入口。
#   - 保持 tracing 初始化逻辑单一来源，避免重复挂载 span/exporter。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.otel_setup import setup_runtime_tracing

__all__ = ["setup_runtime_tracing"]
