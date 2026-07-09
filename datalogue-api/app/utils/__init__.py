# ============================================================
# File Name   : __init__.py
# Description:
#   标记工具函数包。
#
# Responsibilities:
#   - 组织提示词、SQL、JSON、Token 和列名映射工具。
#   - 保持工具模块导入结构清晰。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# utils 包 — 跨模块复用的纯函数工具
# 子模块按主题划分：
# - json_utils    : LLM 输出 JSON 解析
# - token         : LLM Token 用量提取与合并
# - prompt        : 语义层 schema 文本构建
# - sql_dialect   : 跨方言 SQL 引号 / null sanitize / 危险关键字扫描
# - sql_guard     : SQL 执行前静态安全校验与方言规范化
# - sql_diagnosis : SQL 执行失败确定性诊断
# - sample_data   : 给 SQL 审计 Agent 提供真实表样例
# - column_labels : 语义层 → 中文列头映射

# Phase B: SQL 工具实体已迁至 app.domains.query_execution
# 本文件保留为兼容 facade

from app.utils.json_utils import safe_json_parse
from app.utils.token import extract_token_usage, merge_token_usage
from app.domains.query_execution.sql_diagnosis import classify_sql_execution_error, merge_llm_sql_diagnosis
from app.domains.query_execution.sample_data import fetch_sample_rows
from app.domains.query_execution.column_labels import build_column_labels

__all__ = [
    "safe_json_parse",
    "extract_token_usage",
    "merge_token_usage",
    "resolve_dialect",
    "quote_ident",
    "sanitize_filter_sql",
    "contains_forbidden_keyword",
    "FORBIDDEN_SQL_KEYWORDS",
    "SQLGuardResult",
    "guard_readonly_sql",
    "classify_sql_execution_error",
    "merge_llm_sql_diagnosis",
    "fetch_sample_rows",
    "build_column_labels",
]


def __getattr__(name: str):
    """按需导出 SQL 迁移相关能力，避免 utils 包初始化阶段触发循环导入。"""
    if name in {
        "FORBIDDEN_SQL_KEYWORDS",
        "contains_forbidden_keyword",
        "quote_ident",
        "resolve_dialect",
        "sanitize_filter_sql",
    }:
        from app.domains.query_execution import sql_dialect

        return getattr(sql_dialect, name)
    if name in {"SQLGuardResult", "guard_readonly_sql"}:
        from app.domains.query_execution import sql_guard

        return getattr(sql_guard, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
