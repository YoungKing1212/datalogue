# ============================================================
# File Name   : safe_log_summary.py
# Description:
#   AgentScope 日志安全摘要工具。
#
# Responsibilities:
#   - 为 ToolMiddleware 日志提供安全字段计数与标志位。
#   - 避免日志输出 SQL、schema、raw rows、query_plan 或物理字段明细。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
from typing import Any

from agentscope.message import TextBlock


_FORBIDDEN_KEY_FRAGMENTS = (
    "sql",
    "schema",
    "raw",
    "row",
    "record",
    "query_plan",
    "repair_patch",
    "blueprint",
    "field",
    "column",
    "table",
)


def summarize_mapping(
    payload: dict[str, Any],
    *,
    prefix: str,
    **extra: Any,
) -> dict[str, Any]:
    """把工具入参/出参压缩成安全计数，不输出原始字段或数据。"""

    safe_keys = [key for key in payload if _is_safe_key(key)]
    blocked_keys = [key for key in payload if not _is_safe_key(key)]
    return {
        **extra,
        f"safe_{prefix}_key_count": len(safe_keys),
        f"blocked_{prefix}_key_count": len(blocked_keys),
        "has_compiled_query_ref": bool(payload.get("compiled_query_ref")),
        "has_artifact_ref": bool(payload.get("artifact_ref")),
        "has_error_summary": bool(payload.get("error_summary")),
    }


def parse_json_object(text: str) -> dict[str, Any] | None:
    """只接受 JSON object；其他输出视为 opaque，避免误解析非结构化正文。"""

    try:
        payload = json.loads(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def extract_text_outputs(output: str | list[Any]) -> list[str]:
    """从 AgentScope 文本块中提取字符串，供安全摘要解析。"""

    if isinstance(output, str):
        return [output]
    texts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if isinstance(item, TextBlock):
                texts.append(item.text)
            elif isinstance(item, str):
                texts.append(item)
    return texts


def _is_safe_key(key: Any) -> bool:
    key_text = str(key).lower()
    return not any(fragment in key_text for fragment in _FORBIDDEN_KEY_FRAGMENTS)
