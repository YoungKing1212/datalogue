# ============================================================
# File Name   : sql_diagnosis.py
# Description:
#   SQL 执行失败的确定性诊断工具。
#
# Responsibilities:
#   - 根据数据库错误、SQL、DDL 和语义层资产生成结构化诊断。
#   - 稳定输出诊断分类、重试策略和默认修复建议。
#   - 供 SQL 审计节点在 LLM 增强前确定硬性决策。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from __future__ import annotations

import re
from typing import Any


DIAGNOSIS_META = {
    "FIELD_NOT_FOUND": {
        "category": "schema",
        "title": "字段不存在",
        "severity": "fixable",
        "retryable": True,
        "suggested_action": "检查字段名、指标表达式和时间字段配置，改用已选表中存在的字段。",
    },
    "TABLE_NOT_SELECTED": {
        "category": "dataset_config",
        "title": "表未加入数据集",
        "severity": "architectural",
        "retryable": False,
        "suggested_action": "先在数据集配置中选择相关数据源表，并重新同步表结构。",
    },
    "TABLE_NOT_FOUND": {
        "category": "schema",
        "title": "表不存在或不可访问",
        "severity": "architectural",
        "retryable": False,
        "suggested_action": "检查数据源中表是否存在、schema 是否正确，必要时重新同步元数据。",
    },
    "AGGREGATION_ERROR": {
        "category": "sql_semantics",
        "title": "聚合或分组错误",
        "severity": "fixable",
        "retryable": True,
        "suggested_action": "调整 GROUP BY、聚合函数或明细字段，避免聚合查询中混用未分组字段。",
    },
    "TYPE_ERROR": {
        "category": "sql_semantics",
        "title": "字段类型或运算符不兼容",
        "severity": "fixable",
        "retryable": True,
        "suggested_action": "检查过滤值、类型转换和运算符，按字段真实类型改写条件。",
    },
    "PERMISSION_DENIED": {
        "category": "permission",
        "title": "数据源权限不足",
        "severity": "architectural",
        "retryable": False,
        "suggested_action": "确认当前数据源账号具备对应库表的读取权限。",
    },
    "SYNTAX_OR_DIALECT": {
        "category": "dialect",
        "title": "SQL 语法或方言不兼容",
        "severity": "fixable",
        "retryable": True,
        "suggested_action": "按目标数据源方言改写 SQL 语法、函数、引号或分页表达式。",
    },
    "TIMEOUT": {
        "category": "performance",
        "title": "SQL 执行超时",
        "severity": "architectural",
        "retryable": False,
        "suggested_action": "缩小查询范围、增加过滤条件，或优化索引和预聚合配置。",
    },
    "UNKNOWN_EXECUTION_ERROR": {
        "category": "unknown",
        "title": "未知 SQL 执行错误",
        "severity": "fixable",
        "retryable": True,
        "suggested_action": "结合错误信息、表结构和样例数据重新生成更保守的查询。",
    },
}


_FIELD_PATTERNS = (
    re.compile(r"unknown column ['\"]?([^'\"`]+)['\"]?", re.IGNORECASE),
    re.compile(r"no such column:\s*([`\"\[]?[\w.]+[`\"\]]?)", re.IGNORECASE),
    re.compile(r"column ['\"]?([^'\"`]+)['\"]? does not exist", re.IGNORECASE),
)
_TABLE_PATTERNS = (
    re.compile(r"no such table:\s*([`\"\[]?[\w.]+[`\"\]]?)", re.IGNORECASE),
    re.compile(r"relation ['\"]?([^'\"`]+)['\"]? does not exist", re.IGNORECASE),
    re.compile(r"table ['\"]?([^'\"`]+)['\"]? doesn't exist", re.IGNORECASE),
)
_FROM_TABLE_RE = re.compile(r"\bfrom\s+[`\"\[]?([\w.]+)[`\"\]]?", re.IGNORECASE)
_JOIN_TABLE_RE = re.compile(r"\bjoin\s+[`\"\[]?([\w.]+)[`\"\]]?", re.IGNORECASE)


def _clean_identifier(value: str | None) -> str | None:
    """清理错误文本中提取出的字段或表名。"""
    if not value:
        return None
    cleaned = value.strip().strip("`\"[]")
    return cleaned or None


def _match_first(patterns: tuple[re.Pattern, ...], text: str) -> str | None:
    """从错误文本中提取第一个命中的标识符。"""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return _clean_identifier(match.group(1))
    return None


def _selected_table_names(structured: dict | None) -> set[str]:
    """读取数据集中已选择的表名。"""
    if not structured:
        return set()
    names: set[str] = set()
    tables_json = structured.get("tables_json") or {}
    for table in tables_json.get("tables") or []:
        name = table.get("name")
        if name:
            names.add(str(name).lower())
    for group in ("metrics", "dimensions", "fields"):
        for item in structured.get(group) or []:
            table_name = item.get("table_name")
            if table_name:
                names.add(str(table_name).lower())
    return names


def _sql_table_names(sql: str | None) -> set[str]:
    """从 SQL 中粗略提取 FROM/JOIN 表名，用于表未选判断。"""
    if not sql:
        return set()
    names = {m.group(1).lower() for m in _FROM_TABLE_RE.finditer(sql)}
    names.update(m.group(1).lower() for m in _JOIN_TABLE_RE.finditer(sql))
    return {name.split(".")[-1] for name in names}


def _field_in_semantic_assets(field: str | None, structured: dict | None) -> bool:
    """判断缺失字段是否来自语义层配置，来自配置时应视作需人工修复。"""
    if not field or not structured:
        return False
    normalized = field.split(".")[-1].strip("`\"[]").lower()
    for metric in structured.get("metrics") or []:
        expr = str(metric.get("expr") or "").lower()
        time_field = str(metric.get("time_field") or "").lower()
        filter_sql = str(metric.get("filter_sql") or "").lower()
        if normalized and (normalized in expr or normalized == time_field or normalized in filter_sql):
            return True
    for item in (structured.get("dimensions") or []) + (structured.get("fields") or []):
        column = str(item.get("column_name") or "").split(".")[-1].lower()
        if normalized == column:
            return True
    return False


def classify_sql_execution_error(
    *,
    error: str | None,
    sql: str | None = None,
    ddl_context: str | None = None,
    schema_structured: dict | None = None,
    datasource_dialect: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """对 SQL 执行错误做确定性分类并生成默认诊断。"""
    message = error or ""
    lower = message.lower()
    evidence: dict[str, Any] = {
        "matched_error": message,
        "datasource_dialect": datasource_dialect,
        "retry_count": retry_count,
    }

    selected_tables = _selected_table_names(schema_structured)
    sql_tables = _sql_table_names(sql)
    if selected_tables:
        evidence["selected_tables"] = sorted(selected_tables)
    if sql_tables:
        evidence["sql_tables"] = sorted(sql_tables)

    if any(marker in lower for marker in ("permission denied", "access denied", "not authorized", "权限")):
        code = "PERMISSION_DENIED"
    elif any(marker in lower for marker in ("timeout", "timed out", "statement timeout", "execution was interrupted")):
        code = "TIMEOUT"
    elif any(marker in lower for marker in ("not in group by", "group by", "misuse of aggregate", "aggregate function")):
        code = "AGGREGATION_ERROR"
    elif any(marker in lower for marker in ("invalid input syntax", "datatype mismatch", "cannot cast", "operator does not exist", "type mismatch", "incompatible type")):
        code = "TYPE_ERROR"
    elif "尚未选择任何数据源表" in message or "无法确定主表" in message or "没选表" in message:
        code = "TABLE_NOT_SELECTED"
    elif (missing_table := _match_first(_TABLE_PATTERNS, message)):
        evidence["wrong_table"] = missing_table
        table_short = missing_table.split(".")[-1].lower()
        if selected_tables and table_short not in selected_tables:
            code = "TABLE_NOT_SELECTED"
        else:
            code = "TABLE_NOT_FOUND"
    elif (missing_field := _match_first(_FIELD_PATTERNS, message)):
        evidence["wrong_field"] = missing_field
        code = "FIELD_NOT_FOUND"
    elif any(marker in lower for marker in ("syntax error", "sql syntax", "parse error", "near ", "方言")):
        code = "SYNTAX_OR_DIALECT"
    else:
        code = "UNKNOWN_EXECUTION_ERROR"

    meta = DIAGNOSIS_META[code]
    wrong_field = evidence.get("wrong_field")
    if code == "FIELD_NOT_FOUND" and _field_in_semantic_assets(wrong_field, schema_structured):
        severity = "architectural"
        retryable = False
        detail = f"字段 {wrong_field} 来自语义层配置，但当前所选表结构中不可用。"
        suggested_action = "请修正语义层指标、维度或字段映射后重新提问。"
    else:
        severity = meta["severity"]
        retryable = bool(meta["retryable"])
        detail = _default_detail(code, evidence)
        suggested_action = meta["suggested_action"]

    if code == "TABLE_NOT_FOUND" and sql_tables and selected_tables and not sql_tables.issubset(selected_tables):
        code = "TABLE_NOT_SELECTED"
        meta = DIAGNOSIS_META[code]
        severity = meta["severity"]
        retryable = bool(meta["retryable"])
        detail = _default_detail(code, evidence)
        suggested_action = meta["suggested_action"]

    return {
        "code": code,
        "category": DIAGNOSIS_META[code]["category"],
        "title": DIAGNOSIS_META[code]["title"],
        "detail": detail,
        "suggested_action": suggested_action,
        "severity": severity,
        "retryable": retryable,
        "evidence": evidence,
        "original_error": message,
        "root_cause": DIAGNOSIS_META[code]["title"],
        "wrong_field": evidence.get("wrong_field"),
        "suggested_fix": suggested_action,
    }


def _default_detail(code: str, evidence: dict[str, Any]) -> str:
    """按分类生成默认中文诊断详情。"""
    if code == "FIELD_NOT_FOUND" and evidence.get("wrong_field"):
        return f"SQL 引用了不存在或不可访问的字段：{evidence['wrong_field']}。"
    if code == "TABLE_NOT_SELECTED":
        return "SQL 引用了当前数据集未选择的表，或数据集尚未维护可查询表。"
    if code == "TABLE_NOT_FOUND" and evidence.get("wrong_table"):
        return f"SQL 引用了不存在或不可访问的表：{evidence['wrong_table']}。"
    if code == "AGGREGATION_ERROR":
        return "SQL 的聚合函数、明细字段和 GROUP BY 组合不兼容。"
    if code == "TYPE_ERROR":
        return "SQL 中的字段类型、过滤值或运算符不兼容。"
    if code == "PERMISSION_DENIED":
        return "数据源账号没有读取相关库表或字段的权限。"
    if code == "SYNTAX_OR_DIALECT":
        return "SQL 语法不符合目标数据源方言，或使用了不兼容函数。"
    if code == "TIMEOUT":
        return "SQL 执行时间超过数据源或系统允许的上限。"
    return "SQL 执行失败，当前错误无法被确定性规则归入更具体分类。"


def merge_llm_sql_diagnosis(base: dict[str, Any], llm_result: dict[str, Any] | None) -> dict[str, Any]:
    """把 LLM 的自然语言补充合并到确定性诊断，保留硬性分类和重试策略。"""
    result = dict(base)
    if not isinstance(llm_result, dict):
        return result
    for target_key, source_key in (
        ("detail", "root_cause"),
        ("wrong_field", "wrong_field"),
        ("suggested_action", "suggested_fix"),
    ):
        value = llm_result.get(source_key)
        if value not in (None, "", [], {}):
            result[target_key] = value
    result["root_cause"] = result.get("detail") or result.get("title")
    result["suggested_fix"] = result.get("suggested_action")
    return result
