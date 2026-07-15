# ============================================================
# File Name   : observability.py
# Description:
#   数语业务执行面 OpenTelemetry span 的轻量公共工具。
#
# Responsibilities:
#   - 以统一 tracer 创建问数任务、SQL 执行和产物写入等业务 span。
#   - 归一化 span 属性，避免把 None 或复杂对象直接交给 OTel SDK。
#
# Author      : yangkai
# Created On  : 2026-07-14
# ============================================================

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any

from opentelemetry import trace

_TRACER_NAME = "datalogue.observability"


def observation_span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
) -> AbstractContextManager[Any]:
    """创建业务 span；SDK 未配置时仍返回 no-op span，不能影响问数主链。"""

    return trace.get_tracer(_TRACER_NAME).start_as_current_span(
        name,
        attributes=_normalize_attributes(attributes or {}),
    )


def set_span_attributes(span: Any, attributes: Mapping[str, Any]) -> None:
    """只写 OTel 支持的属性类型，供执行结束后补充行列数、产物引用等结果。"""

    for key, value in _normalize_attributes(attributes).items():
        span.set_attribute(key, value)


def _normalize_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """过滤空值并把复杂业务对象转成字符串，避免观测失败反向影响业务。"""

    normalized: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            normalized[str(key)] = value
            continue
        if isinstance(value, (list, tuple)) and all(
            isinstance(item, (str, bool, int, float)) for item in value
        ):
            normalized[str(key)] = list(value)
            continue
        normalized[str(key)] = str(value)
    return normalized
