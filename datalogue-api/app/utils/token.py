# ============================================================
# File Name   : token.py
# Description:
#   Token 估算和上下文裁剪工具。
#
# Responsibilities:
#   - 估算提示词 Token 使用量。
#   - 在调用 LLM 前裁剪过大的上下文。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# LLM Token 用量提取与合并工具

from typing import Any, Optional


def estimate_text_tokens(text: Any) -> int:
    """粗粒度估算 token 数，用于模型未返回 usage 时兜底。"""

    raw = str(text or "")
    if not raw:
        return 0
    chinese_chars = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
    other_chars = max(0, len(raw) - chinese_chars)
    return max(1, chinese_chars + other_chars // 4)


def estimate_messages_tokens(messages: list[Any] | None) -> int:
    """估算一组 LangChain message 的输入 token。"""

    total = 0
    for message in messages or []:
        content = getattr(message, "content", message)
        role = getattr(message, "type", None) or getattr(message, "role", "")
        total += estimate_text_tokens(f"{role}\n{content}")
    return total


def extract_token_usage(response, messages: list[Any] | None = None) -> dict:
    """从 LangChain AIMessage 中提取 Token 用量。
    兼容 usage_metadata 的 input_tokens / output_tokens / total_tokens 字段。

    部分 OpenAI-compatible 服务商不会返回 usage；此时按输入/输出文本做本地估算，
    保证可观测链路不再出现 0 token，但调用方应把来源标记为 estimated。
    """
    usage = getattr(response, "usage_metadata", None) or {}
    prompt = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
    completion = usage.get("output_tokens") or usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt + completion)
    source = "provider" if prompt or completion or total else "estimated"
    if not (prompt or completion or total):
        prompt = estimate_messages_tokens(messages)
        completion = estimate_text_tokens(getattr(response, "content", response))
        total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "usage_source": source,
    }


def merge_token_usage(current: Optional[dict], new_usage: Optional[dict]) -> dict:
    """把两轮 Token 用量累加；首次累计时 current 为空 dict。"""
    if not current:
        current = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if not new_usage:
        return dict(current)
    return {
        "prompt_tokens": current.get("prompt_tokens", 0) + new_usage.get("prompt_tokens", 0),
        "completion_tokens": current.get("completion_tokens", 0)
        + new_usage.get("completion_tokens", 0),
        "total_tokens": current.get("total_tokens", 0) + new_usage.get("total_tokens", 0),
    }
