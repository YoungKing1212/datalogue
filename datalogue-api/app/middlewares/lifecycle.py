# ============================================================
# File Name   : lifecycle.py
# Description:
#   Datalogue Agent 与 Dataset Query Skill 执行链路的安全生命周期日志。
#
# Responsibilities:
#   - 统一输出可 grep 的结构化生命周期日志。
#   - 只记录 ID、状态、阶段、工具名和错误码等安全字段。
#   - 对 SQL、schema、raw rows、compiled refs 等敏感执行态做脱敏。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_RAW_LOG_TRUE_VALUES = {"1", "true", "yes", "on", "debug"}

_FORBIDDEN_KEY_TOKENS = (
    "sql",
    "schema",
    "raw_rows",
    "rawrows",
    "compiled_query_ref",
    "query_plan",
    "repair_patch",
    "blueprint_body",
    "candidate_assets",
)
_FORBIDDEN_VALUE_TOKENS = (
    "select ",
    " from ",
    "schema_context",
    "raw_rows",
    "compiled_query:",
    "query_plan",
    "repair_patch",
)


def log_lifecycle(stage: str, **fields: Any) -> None:
    """生命周期日志已在调试期下线；保留函数签名避免迁移期调用方大面积改动。"""

    return None


def raw_agent_logs_enabled() -> bool:
    """调试阶段开关：显式开启后才允许打印原始 request/context/result。"""

    raw_env = os.getenv("AGENT_DEBUG_RAW_LOGS")
    if raw_env is not None:
        return raw_env.strip().lower() in _RAW_LOG_TRUE_VALUES
    try:
        from app.core.config import get_settings

        return bool(get_settings().AGENT_DEBUG_RAW_LOGS)
    except Exception:
        return False


def log_raw(stage: str, **fields: Any) -> None:
    """输出原始调试 payload；只用于本地排障，调用方需通过环境变量显式开启。"""

    if not raw_agent_logs_enabled():
        return
    payload = {"stage": stage, **fields}
    logger.info("[datalogue.raw] %s", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def log_agent_io(agent: str, stage: str, **fields: Any) -> None:
    """输出 Agent 原始 prompt 和返回值；仅在本地调试开关开启时打印。"""

    if not raw_agent_logs_enabled():
        return
    payload = {"agent": agent, "stage": stage, **fields}
    logger.info("[datalogue.agent] %s", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def log_output(**fields: Any) -> None:
    """输出 Datalogue 用户可见结果摘要，仍复用同一套敏感执行态脱敏规则。"""

    logger.info("[datalogue.output] %s", json.dumps(_sanitize(fields), ensure_ascii=False, sort_keys=True))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            text_key = str(key)
            lowered = text_key.lower()
            if any(token in lowered for token in _FORBIDDEN_KEY_TOKENS):
                safe[text_key] = "<redacted>"
                continue
            safe[text_key] = _sanitize(nested)
        return safe
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:20]]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value[:20]]
    if isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in _FORBIDDEN_VALUE_TOKENS):
            return "<redacted>"
        return value if len(value) <= 300 else f"{value[:300]}..."
    return value
