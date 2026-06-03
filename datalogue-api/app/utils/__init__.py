# utils 包 — 跨模块复用的纯函数工具
# 子模块按主题划分：
# - json_utils    : LLM 输出 JSON 解析
# - token         : LLM Token 用量提取与合并
# - prompt        : 语义层 schema 文本构建
# - sql_dialect   : 跨方言 SQL 引号 / null sanitize / 危险关键字扫描
# - sample_data   : 给 SQL 审计 Agent 提供真实表样例
# - column_labels : 语义层 → 中文列头映射

from app.utils.json_utils import safe_json_parse
from app.utils.token import extract_token_usage, merge_token_usage
from app.utils.prompt import build_schema_prompt
from app.utils.sql_dialect import (
    resolve_dialect,
    quote_ident,
    sanitize_filter_sql,
    contains_forbidden_keyword,
    FORBIDDEN_SQL_KEYWORDS,
)
from app.utils.sample_data import fetch_sample_rows
from app.utils.column_labels import build_column_labels

__all__ = [
    "safe_json_parse",
    "extract_token_usage",
    "merge_token_usage",
    "build_schema_prompt",
    "resolve_dialect",
    "quote_ident",
    "sanitize_filter_sql",
    "contains_forbidden_keyword",
    "FORBIDDEN_SQL_KEYWORDS",
    "fetch_sample_rows",
    "build_column_labels",
]
