# ============================================================
# File Name   : text_patterns.py
# Description:
#   用户可见文本边界共用的 SQL 与内部异常识别模式。
#
# Responsibilities:
#   - 区分查询语句模式与包含 DDL 的完整 SQL 语句模式。
#   - 统一识别驱动异常和内部数据库对象不存在等错误文本。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations

import re


# 自由问句可能包含 “create ... from ...”，仅在已知执行摘要面使用较窄的查询语句模式。
SQL_QUERY_TEXT_RE = re.compile(
    r"\b(select|insert|update|delete|with)\b[\s\S]{0,120}\b(from|into|set)\b",
    re.IGNORECASE,
)

# 已知内部载荷面需要同时拦截 DDL，避免 schema/repair payload 通过摘要字段外泄。
SQL_STATEMENT_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)

INTERNAL_ERROR_TEXT_RE = re.compile(
    r"(\b(psycopg2|sqlalchemy|traceback|undefinedcolumn|undefinedtable|programmingerror|operationalerror)\b)"
    r"|(\b(column|table|relation)\s+['\"]?[\w.]+['\"]?\s+(does not exist|not found))",
    re.IGNORECASE,
)


__all__ = ["INTERNAL_ERROR_TEXT_RE", "SQL_QUERY_TEXT_RE", "SQL_STATEMENT_TEXT_RE"]
