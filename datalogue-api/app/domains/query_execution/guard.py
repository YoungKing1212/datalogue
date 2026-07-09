# ============================================================
# File Name   : guard.py
# Description:
#   查询执行领域的 SQL 执行前静态安全校验与方言规范化工具。
#
# Responsibilities:
#   - 在执行前拦截非只读、多语句和危险 SQL。
#   - 按目标数据源方言补齐或裁剪结果行数限制。
#   - 返回结构化错误，便于 API 和蓝图执行器透出明确原因。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

from app.utils.query_constraints import normalize_query_constraints
from app.domains.query_execution.dialect.names import sanitize_filter_sql


@dataclass
class SQLGuardResult:
    """SQL Guard 的结构化执行结果。"""

    ok: bool
    normalized_sql: str | None = None
    code: str | None = None
    error: str | None = None
    keyword: str | None = None
    warnings: list[str] = field(default_factory=list)


DIALECT_ALIASES = {
    "postgresql": "postgres",
    "pgsql": "postgres",
    "mariadb": "mysql",
    "sqlserver": "tsql",
    "mssql": "tsql",
    "presto": "trino",
}

FORBIDDEN_STATEMENT_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "grant",
    "revoke",
    "truncate",
    "merge",
    "replace",
    "call",
    "execute",
    "exec",
    "vacuum",
    "attach",
    "detach",
)

DANGEROUS_FUNCTIONS = (
    "sleep",
    "pg_sleep",
    "benchmark",
    "load_file",
    "xp_cmdshell",
)

DANGEROUS_PATTERNS = (
    ("INTO_OUTFILE", re.compile(r"\binto\s+(?:out|dump)file\b", re.IGNORECASE), "INTO OUTFILE"),
    ("COPY_PROGRAM", re.compile(r"\bcopy\b[\s\S]*\bprogram\b", re.IGNORECASE), "COPY PROGRAM"),
)

FORBIDDEN_EXPRESSION_CLASSES: tuple[type[exp.Expression], ...] = tuple(
    cls
    for cls in (
        getattr(exp, "Insert", None),
        getattr(exp, "Update", None),
        getattr(exp, "Delete", None),
        getattr(exp, "Drop", None),
        getattr(exp, "Create", None),
        getattr(exp, "Alter", None),
        getattr(exp, "Merge", None),
        getattr(exp, "Command", None),
    )
    if cls is not None
)

FORBIDDEN_EXPRESSION_NAMES = {
    "Insert": "insert",
    "Update": "update",
    "Delete": "delete",
    "Drop": "drop",
    "Create": "create",
    "Alter": "alter",
    "Merge": "merge",
    "Command": "command",
}


def _normalize_dialect(dialect: str | None) -> str:
    """归一化内部使用的方言名称。"""
    normalized = str(dialect or "postgres").strip().lower()
    return DIALECT_ALIASES.get(normalized, normalized or "postgres")


def _fail(code: str, message: str, keyword: str | None = None) -> SQLGuardResult:
    """生成失败结果，保持错误结构一致。"""
    return SQLGuardResult(ok=False, code=code, error=message, keyword=keyword)


def _strip_comments(sql: str) -> str:
    """删除 SQL 注释，保留字符串和引用标识符内容。"""
    out: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if quote:
            out.append(ch)
            if ch == quote:
                if quote == "'" and nxt == "'":
                    out.append(nxt)
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and quote == "'" and nxt:
                out.append(nxt)
                i += 2
                continue
            i += 1
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "-" and nxt == "-":
            i += 2
            while i < len(sql) and sql[i] not in "\r\n":
                i += 1
            out.append(" ")
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(sql) and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i = min(i + 2, len(sql))
            out.append(" ")
            continue

        out.append(ch)
        i += 1
    return "".join(out)


def _mask_quoted_content(sql: str) -> str:
    """把字符串和引用标识符替换为空白，便于只扫描可执行 token。"""
    out: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if quote:
            out.append(" ")
            if ch == quote:
                if quote == "'" and nxt == "'":
                    out.append(" ")
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and quote == "'" and nxt:
                out.append(" ")
                i += 2
                continue
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _statement_parts(masked_sql: str) -> list[str]:
    """按分号拆分语句，调用前已屏蔽字符串和注释。"""
    return [part.strip() for part in masked_sql.split(";")]


def _first_token(masked_sql: str) -> str:
    """提取 SQL 的第一个可执行 token。"""
    match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", masked_sql)
    return match.group(0).lower() if match else ""


def _contains_forbidden_keyword(masked_sql: str) -> str | None:
    """扫描注释和字符串外的危险语句关键字。"""
    for keyword in FORBIDDEN_STATEMENT_KEYWORDS:
        if re.search(rf"\b{keyword}\b", masked_sql, re.IGNORECASE):
            return keyword
    return None


def _contains_dangerous_function(masked_sql: str) -> str | None:
    """扫描注释和字符串外的危险函数调用。"""
    for function_name in DANGEROUS_FUNCTIONS:
        if re.search(rf"\b{re.escape(function_name)}\s*\(", masked_sql, re.IGNORECASE):
            return function_name
    return None


def _parse_with_sqlglot(sql: str, dialect: str) -> list[exp.Expression] | SQLGuardResult:
    """使用 SQLGlot 按目标方言解析 SQL。"""
    try:
        return sqlglot.parse(sql, read=dialect)
    except (ParseError, SqlglotError) as exc:
        return _fail("PARSE_ERROR", f"SQL 解析失败，无法确认安全性：{exc}")
    except ValueError as exc:
        return _fail("DIALECT_UNSUPPORTED", f"当前 SQL 方言暂不支持：{exc}")


def _forbidden_expression(expression: exp.Expression) -> str | None:
    """从 AST 中识别 DML/DDL/命令类节点。"""
    for node in expression.walk():
        if isinstance(node, FORBIDDEN_EXPRESSION_CLASSES):
            return FORBIDDEN_EXPRESSION_NAMES.get(type(node).__name__, type(node).__name__.lower())
    return None


def _dangerous_function_from_ast(expression: exp.Expression) -> str | None:
    """从 AST 中识别危险函数调用。"""
    dangerous = {name.lower() for name in DANGEROUS_FUNCTIONS}
    for node in expression.walk():
        if isinstance(node, exp.Anonymous):
            name = str(node.name or "").lower()
            if name in dangerous:
                return name
    return None


def _sql_table_names(expression: exp.Expression) -> set[str]:
    """从 SQLGlot AST 中提取查询涉及的物理表名。"""
    cte_names = {
        str(cte.alias).strip("`\"[]").lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias
    }
    names: set[str] = set()
    for table in expression.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        normalized = str(name).strip("`\"[]").lower()
        if normalized not in cte_names:
            names.add(normalized)
    return names


def _check_allowed_tables(
    expression: exp.Expression,
    allowed_tables: list[str] | None,
) -> SQLGuardResult | None:
    """校验 SQL 只能访问当前数据集授权表。"""
    if not allowed_tables:
        return None
    allowed = {str(name).split(".")[-1].strip("`\"[]").lower() for name in allowed_tables if name}
    if not allowed:
        return None
    used_tables = _sql_table_names(expression)
    blocked = sorted(name for name in used_tables if name not in allowed)
    if blocked:
        return _fail(
            "SQL_GUARD_BLOCKED",
            f"SQL 引用了当前数据集未授权的表：{', '.join(blocked)}",
            blocked[0],
        )
    return None


def _limit_value(expression: exp.Expression) -> int | None:
    """读取 SQLGlot AST 外层 LIMIT/FETCH 行数。"""
    limit = expression.args.get("limit")
    if not isinstance(limit, exp.Limit):
        return None
    value = limit.args.get("expression")
    if isinstance(value, exp.Literal) and not value.is_string:
        try:
            return int(value.this)
        except (TypeError, ValueError):
            return None
    return None


def _normalize_limit_with_sqlglot(
    expression: exp.Expression,
    dialect: str,
    constraints: dict[str, Any],
) -> tuple[str, list[str]]:
    """使用 SQLGlot AST 按查询约束补齐或裁剪外层行数限制。"""
    warnings: list[str] = []
    if not constraints.get("enabled"):
        return expression.sql(dialect=dialect), warnings

    default_limit = int(constraints["default_limit"])
    max_limit = int(constraints["max_limit"])
    target_limit = min(default_limit, max_limit)

    current = _limit_value(expression)
    if current is not None:
        if current > max_limit:
            expression.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
            warnings.append(f"结果行数限制已从 {current} 裁剪为 {max_limit}")
        return expression.sql(dialect=dialect), warnings

    expression.set("limit", exp.Limit(expression=exp.Literal.number(target_limit)))
    warnings.append(f"未指定返回行数，已自动补充限制 {target_limit}")
    return expression.sql(dialect=dialect), warnings


def guard_readonly_sql(
    sql: str | None,
    *,
    dialect: str | None = None,
    query_constraints: dict[str, Any] | None = None,
    allowed_tables: list[str] | None = None,
) -> SQLGuardResult:
    """校验并规范化只读 SQL。

    该函数只做静态安全判断，不连接数据库，也不尝试证明 SQL 业务语义正确。
    """
    raw_sql = (sql or "").strip()
    if not raw_sql:
        return _fail("EMPTY_SQL", "SQL 不能为空")

    dialect_name = _normalize_dialect(dialect)
    constraints = normalize_query_constraints(query_constraints)
    without_comments = _strip_comments(raw_sql).strip()
    without_comments = sanitize_filter_sql(without_comments) or without_comments
    masked = _mask_quoted_content(without_comments)
    parts = _statement_parts(masked)
    non_empty_parts = [part for part in parts if part]
    if len(non_empty_parts) > 1:
        return _fail("MULTI_STATEMENT", "SQL 只允许单条只读查询，已拦截多语句")

    forbidden = _contains_forbidden_keyword(masked)
    if forbidden:
        return _fail(
            "FORBIDDEN_KEYWORD",
            f"SQL 包含危险关键字 '{forbidden}'，已拦截",
            forbidden,
        )

    for code, pattern, label in DANGEROUS_PATTERNS:
        if pattern.search(masked):
            return _fail(code, f"SQL 包含危险语法 '{label}'，已拦截", label)

    parsed = _parse_with_sqlglot(without_comments.rstrip().rstrip(";").strip(), dialect_name)
    if isinstance(parsed, SQLGuardResult):
        return parsed
    statements = [statement for statement in parsed if statement is not None]
    if len(statements) != 1:
        return _fail("MULTI_STATEMENT", "SQL 只允许单条只读查询，已拦截多语句")
    expression = statements[0]

    ast_forbidden = _forbidden_expression(expression)
    if ast_forbidden:
        return _fail(
            "FORBIDDEN_KEYWORD",
            f"SQL 包含危险关键字 '{ast_forbidden}'，已拦截",
            ast_forbidden,
        )

    first = _first_token(masked)
    if first not in {"select", "with"}:
        return _fail("NOT_READONLY", "SQL 只允许 SELECT/WITH 只读查询", first or None)
    if not isinstance(expression, exp.Query):
        return _fail("NOT_READONLY", "SQL 只允许 SELECT/WITH 只读查询", type(expression).__name__)

    allowed_table_error = _check_allowed_tables(expression, allowed_tables)
    if allowed_table_error:
        return allowed_table_error

    dangerous_function = _contains_dangerous_function(masked)
    if dangerous_function:
        return _fail(
            "DANGEROUS_FUNCTION",
            f"SQL 包含危险函数 '{dangerous_function}'，已拦截",
            dangerous_function,
        )

    ast_dangerous_function = _dangerous_function_from_ast(expression)
    if ast_dangerous_function:
        return _fail(
            "DANGEROUS_FUNCTION",
            f"SQL 包含危险函数 '{ast_dangerous_function}'，已拦截",
            ast_dangerous_function,
        )

    for code, pattern, label in DANGEROUS_PATTERNS:
        if pattern.search(masked):
            return _fail(code, f"SQL 包含危险语法 '{label}'，已拦截", label)

    normalized_sql, warnings = _normalize_limit_with_sqlglot(expression, dialect_name, constraints)
    return SQLGuardResult(ok=True, normalized_sql=normalized_sql, warnings=warnings)
