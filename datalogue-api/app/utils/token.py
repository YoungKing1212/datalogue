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

from typing import Optional


def extract_token_usage(response) -> dict:
    """从 LangChain AIMessage 中提取 Token 用量。
    兼容 usage_metadata 的 input_tokens / output_tokens / total_tokens 字段。"""
    usage = response.usage_metadata or {}
    prompt = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
    completion = usage.get("output_tokens") or usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
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
