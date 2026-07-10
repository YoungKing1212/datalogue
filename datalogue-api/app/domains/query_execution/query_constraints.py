# ============================================================
# File Name   : query_constraints.py
# Description:
#   数据集查询约束配置工具。
#
# Responsibilities:
#   - 归一化数据集级默认时间范围与默认行数限制。
#   - 渲染 SQL/DSL 生成节点可复用的提示词约束。
#
# Author      : yangkai
# Created On  : 2026-06-08
# ============================================================

from typing import Any


DEFAULT_QUERY_CONSTRAINTS: dict[str, Any] = {
    "enabled": True,
    "default_time_range_days": 30,
    "default_limit": 10000,
    "max_limit": 10000,
}


def normalize_query_constraints(value: dict[str, Any] | None) -> dict[str, Any]:
    """合并用户配置和系统默认值，并限制数值范围。"""
    raw = value or {}
    enabled = bool(raw.get("enabled", DEFAULT_QUERY_CONSTRAINTS["enabled"]))

    def _int_value(key: str, minimum: int, maximum: int) -> int:
        try:
            parsed = int(raw.get(key, DEFAULT_QUERY_CONSTRAINTS[key]))
        except (TypeError, ValueError):
            parsed = DEFAULT_QUERY_CONSTRAINTS[key]
        return max(minimum, min(maximum, parsed))

    max_limit = _int_value("max_limit", 1, 1000000000)
    default_limit = min(_int_value("default_limit", 1, max_limit), max_limit)
    default_time_range_days = _int_value("default_time_range_days", 1, 3650)
    return {
        "enabled": enabled,
        "default_time_range_days": default_time_range_days,
        "default_limit": default_limit,
        "max_limit": max_limit,
    }


def render_query_constraints_instruction(value: dict[str, Any] | None) -> str:
    """生成供 LLM 使用的查询约束说明。"""
    constraints = normalize_query_constraints(value)
    if not constraints["enabled"]:
        return ""
    return (
        "【SQL 生成查询约束（硬性要求）】\n"
        f"- 用户没有明确时间范围时，默认查询最近 {constraints['default_time_range_days']} 天。\n"
        f"- 用户没有明确返回条数时，默认 LIMIT {constraints['default_limit']}。\n"
        f"- LIMIT 最大不能超过 {constraints['max_limit']}，用户要求更多也要截断到该上限。"
    )


__all__ = [
    "DEFAULT_QUERY_CONSTRAINTS",
    "normalize_query_constraints",
    "render_query_constraints_instruction",
]
