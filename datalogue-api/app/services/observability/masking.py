# ============================================================
# File Name   : masking.py
# Description:
#   Langfuse 上报前的数据脱敏与截断。
#
# Responsibilities:
#   - 过滤连接串、密钥、手机号、身份证号等敏感内容。
#   - 将 SQL 和结果集压缩成可观测但不泄露明细的数据摘要。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "password_enc",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)
_SQL_STRING_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def sanitize_text(value: Any, *, max_length: int = 4000) -> Any:
    """脱敏并截断普通文本。"""

    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    text = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=<masked>", text)
    text = _EMAIL_RE.sub("<email>", text)
    text = _PHONE_RE.sub("<phone>", text)
    text = _ID_CARD_RE.sub("<id_card>", text)
    if len(text) > max_length:
        return text[:max_length] + "...<truncated>"
    return text


def sanitize_sql(sql: Any, *, max_length: int = 4000) -> Any:
    """保留 SQL 结构，隐藏字符串字面量。"""

    if sql is None:
        return None
    text = sanitize_text(sql, max_length=max_length * 2)

    def repl(match: re.Match[str]) -> str:
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        if literal and len(literal) <= 2:
            return "'?'"
        return "'<value>'"

    text = _SQL_STRING_RE.sub(repl, str(text))
    if len(text) > max_length:
        return text[:max_length] + "...<truncated>"
    return text


def sanitize_payload(value: Any, *, max_depth: int = 5, max_items: int = 30) -> Any:
    """递归脱敏 JSON-like payload。"""

    if max_depth <= 0:
        return "<max_depth>"
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in list(value.items())[:max_items]:
            key_str = str(key)
            if key_str.lower() in SENSITIVE_KEYS:
                sanitized[key_str] = "<masked>"
            elif key_str.lower() in {"sql", "query"}:
                sanitized[key_str] = sanitize_sql(item)
            elif key_str.lower() in {"rows", "data", "records"} and isinstance(item, Sequence):
                sanitized[key_str] = summarize_rows(item)
            else:
                sanitized[key_str] = sanitize_payload(
                    item,
                    max_depth=max_depth - 1,
                    max_items=max_items,
                )
        if len(value) > max_items:
            sanitized["_truncated_keys"] = len(value) - max_items
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        result = [
            sanitize_payload(item, max_depth=max_depth - 1, max_items=max_items)
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            result.append({"_truncated_items": len(items) - max_items})
        return result
    return sanitize_text(value)


def summarize_rows(rows: Any, *, limit: int = 5) -> dict[str, Any]:
    """结果集只上报列名、行数和少量脱敏样例。"""

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return {"row_count": 0, "sample": []}
    sample = []
    columns: list[str] = []
    for row in list(rows)[:limit]:
        if isinstance(row, Mapping):
            if not columns:
                columns = [str(k) for k in row.keys()]
            sample.append({str(k): sanitize_text(v, max_length=200) for k, v in row.items()})
        else:
            sample.append(sanitize_text(row, max_length=200))
    return {
        "row_count": len(rows),
        "columns": columns,
        "sample": sample,
    }
