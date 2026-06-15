# ============================================================
# File Name   : think.py
# Description:
#   LLM Think 标签清理工具。
#
# Responsibilities:
#   - 清理模型泄露到用户可见内容中的 <think> 块。
#   - 支持流式 token 场景下跨 chunk 的 Think 标签过滤。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import re
from typing import Any

THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
THINK_CLOSE_RE = re.compile(r"</think\s*>", re.IGNORECASE)
THINK_PREFIXES = ("<think", "</think")


def strip_think_blocks(text: Any) -> str:
    """移除完整 Think 块，兼容大小写和带属性的开标签。"""

    value = "" if text is None else str(text)
    return re.sub(
        r"<think\b[^>]*>[\s\S]*?</think\s*>",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()


def new_think_stream_state() -> dict[str, Any]:
    """创建流式 Think 过滤状态。"""

    return {"pending": "", "in_think": False}


def _prefix_suffix(text: str, prefixes: tuple[str, ...]) -> str:
    lowered = text.lower()
    max_len = min(len(lowered), max(len(prefix) for prefix in prefixes))
    for size in range(max_len, 0, -1):
        suffix = lowered[-size:]
        if any(prefix.startswith(suffix) for prefix in prefixes):
            return text[-size:]
    return ""


def filter_think_stream_chunk(chunk: Any, state: dict[str, Any]) -> str:
    """过滤单个流式 chunk，Think 块内内容不会被返回。

    state 必须来自 new_think_stream_state()，调用方应在同一次 LLM 流中复用。
    """

    if chunk in (None, ""):
        return ""

    state["pending"] = str(state.get("pending") or "") + str(chunk)
    output: list[str] = []

    while state["pending"]:
        pending = state["pending"]
        if bool(state.get("in_think")):
            close = THINK_CLOSE_RE.search(pending)
            if close is None:
                state["pending"] = _prefix_suffix(pending, ("</think",))
                return "".join(output)
            state["pending"] = pending[close.end():]
            state["in_think"] = False
            continue

        open_tag = THINK_OPEN_RE.search(pending)
        if open_tag is None:
            suffix = _prefix_suffix(pending, THINK_PREFIXES)
            if suffix:
                output.append(pending[: -len(suffix)])
                state["pending"] = suffix
            else:
                output.append(pending)
                state["pending"] = ""
            return "".join(output)

        output.append(pending[: open_tag.start()])
        state["pending"] = pending[open_tag.end():]
        state["in_think"] = True

    return "".join(output)


def flush_think_stream_state(state: dict[str, Any]) -> str:
    """流结束时返回未处于 Think 块内的普通文本尾巴。"""

    if bool(state.get("in_think")):
        state["pending"] = ""
        return ""
    pending = str(state.get("pending") or "")
    state["pending"] = ""
    return pending
