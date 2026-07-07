# ============================================================
# File Name   : blueprint_analyzer.py
# Description:
#   分析蓝图 SQL 草稿 AI 分析服务。
#
# Responsibilities:
#   - 调用 LLM 理解 SQL 草稿的业务含义并生成蓝图草案。
#   - 用确定性 SQL 解析结果辅助校验和补齐 AI 输出字段。
#
# Author      : yangkai
# Created On  : 2026-06-08
# ============================================================

import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.graph.llm import get_llm
from app.utils import safe_json_parse
from app.prompts import BLUEPRINT_SQL_ANALYSIS_SYSTEM, BLUEPRINT_DESCRIPTION_SYSTEM


logger = logging.getLogger(__name__)

_PARAM_HINTS = {
    "start": ("start_date", "date", "时间起点，默认本月1号", "MONTH_START"),
    "begin": ("start_date", "date", "时间起点，默认本月1号", "MONTH_START"),
    "from": ("start_date", "date", "时间起点，默认本月1号", "MONTH_START"),
    "end": ("end_date", "date", "时间终点，默认今天", "TODAY"),
    "finish": ("end_date", "date", "时间终点，默认今天", "TODAY"),
    "to": ("end_date", "date", "时间终点，默认今天", "TODAY"),
    "date": ("report_date", "date", "报表日期，默认今天", "TODAY"),
    "region": ("region", "string", "区域名称，未提及时传 NULL", "NULL"),
    "province": ("province", "string", "省份名称，未提及时传 NULL", "NULL"),
    "city": ("city", "string", "城市名称，未提及时传 NULL", "NULL"),
    "category": ("category", "string", "品类名称，未提及时传 NULL", "NULL"),
}

_METRIC_TOKENS = {
    "amount",
    "revenue",
    "gmv",
    "sales",
    "count",
    "cnt",
    "num",
    "rate",
    "ratio",
    "margin",
    "profit",
    "cost",
    "avg",
    "sum",
}

_SEMANTIC_LABELS = {
    "category": "品类",
    "region": "区域",
    "province": "省份",
    "city": "城市",
    "revenue": "营收金额",
    "amount": "金额",
    "gmv": "GMV",
    "gross_margin": "毛利额",
    "margin": "毛利",
    "margin_rate": "毛利率",
    "profit": "利润",
    "cost": "成本",
    "order_count": "订单数",
    "cnt": "数量",
}

_SAFE_DEFAULT_EXPRS = {"TODAY", "YESTERDAY", "MONTH_START", "MONTH_END", "NULL"}


def _normalize_variable_name(raw: str) -> str:
    """把 SQL 模板变量名规范成可绑定参数名。"""
    name = re.sub(r"^(p_|v_|in_)", "", raw.strip().lower())
    name = re.sub(r"\W+", "_", name).strip("_")
    return name or "param"


def _replace_template_variables(sql: str) -> str:
    """把常见模板变量替换为 SQLAlchemy 可绑定的 :param 占位符。"""

    def _replace(match: re.Match) -> str:
        return ":" + _normalize_variable_name(match.group(1))

    patterns = [
        r"\$\{\s*([a-zA-Z_][\w]*)[^}]*\}",
        r"#\{\s*([a-zA-Z_][\w]*)[^}]*\}",
        r"\{\{\s*([a-zA-Z_][\w]*)[^}]*\}\}",
    ]
    result = sql
    for pattern in patterns:
        result = re.sub(pattern, _replace, result)
    # 模板变量经常被写在引号里，替换为参数后应去掉这层字面量引号。
    return re.sub(r"(['\"]):([a-zA-Z_][\w]*)\1", r":\2", result)


def _remove_variable_assignments(sql: str) -> str:
    """删除变量赋值语句，避免把变量值带入蓝图分析结果。"""
    assignment_patterns = [
        r"\bset\s+@?[a-zA-Z_][\w]*\s*(?::=|=)\s*[^;]+;",
        r"\bdeclare\s+@?[a-zA-Z_][\w]*\s+[^;=]+(?:=\s*[^;]+|default\s+[^;]+)?;",
    ]
    result = sql
    for pattern in assignment_patterns:
        result = re.sub(pattern, " ", result, flags=re.IGNORECASE)
    return result


def _replace_at_variables(sql: str) -> str:
    """把 @var 变量使用替换成 :var，占位符值由执行时注入。"""
    return re.sub(
        r"(?<!@)@([a-zA-Z_][\w]*)",
        lambda match: ":" + _normalize_variable_name(match.group(1)),
        sql,
    )


def _sanitize_sql_variables(sql: str) -> str:
    """规范 SQL 变量，保留占位符，不保留变量实际值。"""
    result = _remove_variable_assignments(sql or "")
    result = _replace_template_variables(result)
    result = _replace_at_variables(result)
    return _normalize_space(result)


def _variable_name_variants(name: str) -> set[str]:
    """生成变量名的常见展示变体，用于清理 AI 文本输出。"""
    clean = _normalize_variable_name(name)
    variants = {name.strip(), clean}
    if "_" in clean:
        variants.add(clean.replace("_", " "))
    return {item for item in variants if item}


def _extract_assignment_values(expr: str) -> set[str]:
    """从变量赋值表达式中提取实际值。"""
    values = {
        match.group(1) or match.group(2)
        for match in re.finditer(r"'([^']*)'|\"([^\"]*)\"", expr or "")
    }
    stripped = (expr or "").strip()
    if stripped and not values and re.match(r"^[\w\u4e00-\u9fff.-]+$", stripped):
        values.add(stripped)
    return {value for value in values if value and value.upper() not in _SAFE_DEFAULT_EXPRS}


def _variable_protection_context(sql: str) -> dict[str, set[str]]:
    """提取 SQL 中不应出现在蓝图自然语言字段里的参数名和值。"""
    names: set[str] = set()
    values: set[str] = set()
    raw_sql = sql or ""

    for pattern in [
        r"\$\{\s*([a-zA-Z_][\w]*)[^}]*\}",
        r"#\{\s*([a-zA-Z_][\w]*)[^}]*\}",
        r"\{\{\s*([a-zA-Z_][\w]*)[^}]*\}\}",
        r"(?<!@)@([a-zA-Z_][\w]*)",
        r":([a-zA-Z_][\w]*)",
    ]:
        for raw in re.findall(pattern, raw_sql):
            names.update(_variable_name_variants(raw))

    for raw, expr in re.findall(
        r"\bset\s+@?([a-zA-Z_][\w]*)\s*(?::=|=)\s*([^;]+);",
        raw_sql,
        flags=re.IGNORECASE,
    ):
        names.update(_variable_name_variants(raw))
        values.update(_extract_assignment_values(expr))

    for match in re.findall(
        r"\bdeclare\s+@?([a-zA-Z_][\w]*)\s+[^;=]+(?:=\s*([^;]+)|default\s+([^;]+))?;",
        raw_sql,
        flags=re.IGNORECASE,
    ):
        raw = match[0]
        expr = next((item for item in match[1:] if item), "")
        names.update(_variable_name_variants(raw))
        values.update(_extract_assignment_values(str(expr or "")))

    return {"names": names, "values": values}


def _extend_context_with_ai_params(
    context: dict[str, set[str]],
    params: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """把 AI 返回的参数名和疑似实际默认值也纳入清理上下文。"""
    names = set(context.get("names", set()))
    values = set(context.get("values", set()))
    for item in params:
        if not isinstance(item, dict):
            continue
        if item.get("name"):
            names.update(_variable_name_variants(str(item["name"])))
        default_expr = item.get("default_expr")
        if isinstance(default_expr, str) and default_expr.upper() not in _SAFE_DEFAULT_EXPRS:
            values.add(default_expr.strip("'\""))
    return {"names": names, "values": {value for value in values if value}}


def _contains_protected_token(text: Any, context: dict[str, set[str]]) -> bool:
    """判断文本是否包含 SQL 参数名、占位符或变量值。"""
    if not isinstance(text, str) or not text:
        return False
    for value in context.get("values", set()):
        if value and value in text:
            return True
    for name in context.get("names", set()):
        if not name:
            continue
        escaped = re.escape(name)
        if re.search(rf"[:@]\s*{escaped}\b", text, flags=re.IGNORECASE):
            return True
        if re.search(rf"\b{escaped}\b", text, flags=re.IGNORECASE):
            return True
        if f"${{{name}}}" in text or f"#{{{name}}}" in text or f"{{{{{name}}}}}" in text:
            return True
    return False


def _scrub_protected_text(text: Any, context: dict[str, set[str]]) -> str:
    """从文本中删除 SQL 参数名、占位符和变量值。"""
    if not isinstance(text, str):
        return ""
    result = text
    for value in sorted(context.get("values", set()), key=len, reverse=True):
        if value:
            result = result.replace(value, "")
    for name in sorted(context.get("names", set()), key=len, reverse=True):
        if not name:
            continue
        escaped = re.escape(name)
        result = re.sub(rf"\$\{{\s*{escaped}\s*[^}}]*\}}", "", result, flags=re.IGNORECASE)
        result = re.sub(rf"#\{{\s*{escaped}\s*[^}}]*\}}", "", result, flags=re.IGNORECASE)
        result = re.sub(rf"\{{\{{\s*{escaped}\s*[^}}]*\}}\}}", "", result, flags=re.IGNORECASE)
        result = re.sub(rf"[:@]\s*{escaped}\b", "", result, flags=re.IGNORECASE)
        result = re.sub(rf"\b{escaped}\b", "", result, flags=re.IGNORECASE)
    return _normalize_space(result).strip(" ，,。；;：:-")


def _sanitize_text_list(
    values: list,
    context: dict[str, set[str]],
    fallback: list | None = None,
    drop_if_protected: bool = True,
) -> list[str]:
    """清理文本列表，推荐问法和触发词默认丢弃含参数痕迹的项。"""
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        if drop_if_protected and _contains_protected_token(value, context):
            continue
        item = _scrub_protected_text(value, context)
        if item and item not in cleaned:
            cleaned.append(item)
    if cleaned:
        return cleaned
    if fallback:
        return _sanitize_text_list(fallback, context, drop_if_protected=False)
    return []


def _strip_comments(sql: str) -> str:
    """删除 SQL 注释，保留可分析主体。"""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--.*?$", " ", sql, flags=re.MULTILINE)


def _normalize_space(text: str) -> str:
    """压缩空白字符，便于正则分析。"""
    return re.sub(r"\s+", " ", text or "").strip()


def _split_csv(expr: str) -> list[str]:
    """按顶层逗号拆分 SELECT 表达式。"""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    for char in expr:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
            current.append(char)
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        current.append(char)
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _final_select_body(sql: str) -> str:
    """提取最后一个 SELECT 的投影列表。"""
    matches = list(re.finditer(r"\bselect\b", sql, flags=re.IGNORECASE))
    for match in reversed(matches):
        tail = sql[match.end() :]
        from_match = re.search(r"\bfrom\b", tail, flags=re.IGNORECASE)
        if from_match:
            return tail[: from_match.start()].strip()
        semicolon = tail.find(";")
        return (tail[:semicolon] if semicolon >= 0 else tail).strip()
    return ""


def _infer_column_name(expr: str, index: int) -> str:
    """从 SELECT 表达式中推断输出列名。"""
    alias_match = re.search(
        r"\s+as\s+([`\"\[]?[\w\u4e00-\u9fff]+[`\"\]]?)\s*$",
        expr,
        flags=re.IGNORECASE,
    )
    if alias_match:
        return alias_match.group(1).strip('`"[]')
    simple_identifier = re.match(r"^[`\"\[]?([\w\u4e00-\u9fff]+)[`\"\]]?$", expr.strip())
    if simple_identifier:
        return simple_identifier.group(1)
    plain_alias = re.search(r"\s+([`\"\[]?[\w\u4e00-\u9fff]+[`\"\]]?)\s*$", expr)
    if plain_alias and not expr.strip().endswith(")"):
        return plain_alias.group(1).strip('`"[]')
    dotted = re.search(r"([\w]+)\.([`\"\[]?[\w\u4e00-\u9fff]+[`\"\]]?)", expr)
    if dotted:
        return dotted.group(2).strip('`"[]')
    func = re.search(r"\b(sum|count|avg|min|max)\s*\(", expr, flags=re.IGNORECASE)
    if func:
        return f"{func.group(1).lower()}_{index}"
    literal = re.match(r"['\"]([^'\"]+)['\"]$", expr.strip())
    if literal:
        return f"literal_{index}"
    return f"column_{index}"


def _column_role(column: str, expr: str) -> str:
    """判断输出列是指标还是维度。"""
    text = f"{column} {expr}".lower()
    if re.search(r"\b(sum|count|avg|min|max)\s*\(", text):
        return "metric"
    if any(token in text for token in _METRIC_TOKENS):
        return "metric"
    return "dimension"


def _semantic_label(column: str) -> str:
    """按列名推断业务语义标签。"""
    lower = column.lower()
    for token, label in _SEMANTIC_LABELS.items():
        if token in lower:
            return label
    return column


def _extract_parameters(sql: str) -> list[dict[str, Any]]:
    """从过程签名和参数占位符中提取蓝图参数。"""
    found: dict[str, dict[str, Any]] = {}

    for raw in re.findall(r"[:@]([a-zA-Z_][\w]*)", sql):
        name, typ, hint, default_expr = _normalize_param(raw)
        found[name] = {
            "name": name,
            "type": typ,
            "extract_hint": hint,
            "default_expr": default_expr,
            "required": typ == "date",
            "confidence": 0.84,
        }

    signature = re.search(r"\((.*?)\)", sql, flags=re.DOTALL)
    if signature:
        for raw, type_text in re.findall(
            r"\b(?:in|out|inout)?\s*([a-zA-Z_][\w]*)\s+([a-zA-Z]+)",
            signature.group(1),
            flags=re.IGNORECASE,
        ):
            name, typ, hint, default_expr = _normalize_param(raw, type_text)
            found.setdefault(
                name,
                {
                    "name": name,
                    "type": typ,
                    "extract_hint": hint,
                    "default_expr": default_expr,
                    "required": typ == "date",
                    "confidence": 0.78,
                },
            )

    return list(found.values())


def _normalize_param(raw: str, type_text: str | None = None) -> tuple[str, str, str, str]:
    """归一化 SQL 参数名和类型。"""
    clean = re.sub(r"^(p_|v_|in_)", "", raw.lower())
    for token, mapped in _PARAM_HINTS.items():
        if token in clean:
            return mapped
    if type_text and type_text.lower() in ("date", "datetime", "timestamp"):
        return clean, "date", f"{clean} 参数，默认今天", "TODAY"
    return clean, "string", f"{clean} 参数，未提及时传 NULL", "NULL"


def _extract_output_schema(sql: str) -> list[dict[str, Any]]:
    """从最终 SELECT 投影列生成输出 schema。"""
    select_body = _final_select_body(sql)
    if not select_body:
        return []
    output_schema: list[dict[str, Any]] = []
    for index, expr in enumerate(_split_csv(select_body), start=1):
        column = _infer_column_name(expr, index)
        role = _column_role(column, expr)
        output_schema.append(
            {
                "column": column,
                "semantic": _semantic_label(column),
                "unit": "%" if "rate" in column.lower() or "ratio" in column.lower() else "-",
                "role": role,
                "confidence": 0.82 if " as " in expr.lower() else 0.66,
            }
        )
    return output_schema


def _extract_tables(sql: str) -> list[str]:
    """提取 FROM/JOIN 涉及的表名。"""
    tables = re.findall(r"\b(?:from|join)\s+([`\"\[]?[\w.]+[`\"\]]?)", sql, flags=re.IGNORECASE)
    return [table.strip('`"[]') for table in tables]


def _build_steps(sql: str, output_schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根据 SQL 结构生成蓝图业务步骤。"""
    lower = sql.lower()
    steps: list[dict[str, Any]] = []
    step_no = 1
    if re.search(r"\bwhere\b", lower):
        steps.append(
            {
                "step": step_no,
                "name": "基础数据筛选",
                "purpose": "按 SQL 条件和用户参数裁剪业务数据范围",
                "key_rules": ["保留 WHERE 中的业务过滤条件", "参数值由运行时用户问题或默认值提供"],
                "output_columns": [],
                "confidence": 0.82,
            }
        )
        step_no += 1
    if re.search(r"\bgroup\s+by\b", lower) or any(c["role"] == "metric" for c in output_schema):
        steps.append(
            {
                "step": step_no,
                "name": "业务指标聚合",
                "purpose": "按维度汇总指标并生成最终分析结果",
                "key_rules": ["保留 SELECT 中的聚合表达式", "GROUP BY 字段作为分析维度"],
                "output_columns": [c["column"] for c in output_schema],
                "confidence": 0.78,
            }
        )
        step_no += 1
    if re.search(r"\border\s+by\b|\blimit\b", lower):
        steps.append(
            {
                "step": step_no,
                "name": "结果排序与裁剪",
                "purpose": "按 SQL 排序、限制规则输出关键结果",
                "key_rules": ["保留 ORDER BY 和 LIMIT 的结果呈现规则"],
                "output_columns": [c["column"] for c in output_schema],
                "confidence": 0.76,
            }
        )
    if not steps:
        steps.append(
            {
                "step": 1,
                "name": "固定 SQL 查询",
                "purpose": "执行 SQL 草稿定义的固定查询逻辑",
                "key_rules": ["保持原 SQL 只读查询语义"],
                "output_columns": [c["column"] for c in output_schema],
                "confidence": 0.68,
            }
        )
    return steps


def _infer_name(sql: str, output_schema: list[dict[str, Any]]) -> str:
    """根据过程名和输出列推断蓝图名称。"""
    proc = re.search(r"\bprocedure\s+([a-zA-Z_][\w]*)", sql, flags=re.IGNORECASE)
    if proc:
        raw = proc.group(1).lower()
        if "margin" in raw or "profit" in raw:
            return "月度毛利归因报表"
        return raw.replace("_", " ").title()
    columns = " ".join(c["column"].lower() for c in output_schema)
    if "margin" in columns or "profit" in columns:
        return "毛利分析蓝图"
    if "gmv" in columns or "revenue" in columns:
        return "收入分析蓝图"
    return "SQL 分析蓝图"


def _trigger_keywords(output_schema: list[dict[str, Any]], tables: list[str]) -> list[str]:
    """生成入口路由触发词。"""
    keywords: list[str] = []
    for item in output_schema:
        keywords.extend([item["column"], item["semantic"]])
    keywords.extend(table.split(".")[-1] for table in tables)
    clean = []
    for keyword in keywords:
        if keyword and keyword not in clean:
            clean.append(keyword)
    return clean[:8] or ["分析", "报表"]


def _low_confidence_fields(
    params: list[dict[str, Any]],
    output_schema: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成需要人工审核的低置信字段。"""
    lows: list[dict[str, Any]] = []
    for param in params:
        if param.get("confidence", 1) < 0.8:
            lows.append(
                {
                    "path": f"parameters.{param['name']}",
                    "confidence": param.get("confidence"),
                    "reason": "参数来自 SQL 签名或占位符推断，需确认业务含义和默认值",
                }
            )
    for column in output_schema:
        if column.get("confidence", 1) < 0.7:
            lows.append(
                {
                    "path": f"output_schema.{column['column']}",
                    "confidence": column.get("confidence"),
                    "reason": "输出列表达式缺少显式 AS 别名，语义推断置信度较低",
                }
            )
    return lows


def _rule_based_analyze_sql(sql: str) -> dict[str, Any]:
    """用确定性解析生成 AI 分析的参考上下文。"""
    clean_sql = _sanitize_sql_variables(_strip_comments(sql))
    if not clean_sql:
        raise ValueError("sql 不能为空")

    output_schema = _extract_output_schema(clean_sql)
    params = _extract_parameters(clean_sql)
    tables = _extract_tables(clean_sql)
    name = _infer_name(clean_sql, output_schema)
    implementation_type = "stored_procedure" if "procedure" in clean_sql.lower() else "sql_template"
    trigger_keywords = _trigger_keywords(output_schema, tables)
    steps = _build_steps(clean_sql, output_schema)
    low_confidence = _low_confidence_fields(params, output_schema)
    metric_columns = [c["semantic"] for c in output_schema if c["role"] == "metric"]
    dimension_columns = [c["semantic"] for c in output_schema if c["role"] == "dimension"]

    return {
        "name": name,
        "description": _build_description(tables, metric_columns, dimension_columns),
        "trigger_keywords": trigger_keywords,
        "trigger_examples": _trigger_examples(name, trigger_keywords),
        "when_to_use": "当用户询问该 SQL 固化的报表、归因分析或固定分析口径时使用。",
        "parameters": params,
        "implementation_type": implementation_type,
        "call_template": clean_sql if implementation_type == "sql_template" else "",
        "output_schema": output_schema,
        "steps": steps,
        "attribution_hints": _attribution_hints(metric_columns, dimension_columns),
        "raw_sql": clean_sql,
        "ai_confidence": _overall_confidence(params, output_schema),
        "low_confidence_fields": low_confidence,
    }


def _compact_reference(reference: dict[str, Any]) -> str:
    """压缩系统预解析结果，减少传给模型的提示词体积。"""
    keys = [
        "name",
        "description",
        "parameters",
        "implementation_type",
        "output_schema",
        "steps",
        "low_confidence_fields",
    ]
    compact = {key: reference.get(key) for key in keys}
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def _analysis_prompt(sql: str, reference: dict[str, Any]) -> list:
    """构建分析蓝图 AI 提示词。"""
    system = SystemMessage(content=BLUEPRINT_SQL_ANALYSIS_SYSTEM)
    human = HumanMessage(
        content=(
            "请基于 SQL 的真实业务逻辑生成分析蓝图草案。\n\n"
            "要求：\n"
            "1. 理解 SQL 的业务目的，不要机械照抄字段名。\n"
            "2. parameters 要说明参数名、类型、提取提示、默认表达式、是否必填和置信度。\n"
            "3. output_schema 要说明输出列、业务语义、单位、角色 dimension/metric 和置信度。\n"
            "4. steps 要按 SQL 的真实处理链路拆成业务步骤。\n"
            "5. low_confidence_fields 要指出需要人工审核的参数、字段或业务口径。\n"
            "6. implementation_type 只能是 sql_template 或 stored_procedure。\n"
            "7. 如果是可直接执行的 SELECT/WITH，call_template 使用原 SQL 或参数化 SQL；"
            "如果是过程定义，call_template 为空，raw_sql 保留原文。\n\n"
            "8. SQL 中的变量必须使用 :param 占位符，不能输出变量赋值语句，"
            "也不能把变量的实际值写入 raw_sql、call_template 或 default_expr。\n"
            "9. name、description、trigger_keywords、trigger_examples、when_to_use、"
            "steps、attribution_hints、low_confidence_fields 等自然语言字段不能出现 "
            "SQL 参数名、占位符或变量实际值；推荐问法必须是业务问题，不要写 "
            "start_date、end_date、region、:param、@var 这类参数痕迹。\n\n"
            "输出 JSON Schema：\n"
            "{\n"
            '  "name": "蓝图名称",\n'
            '  "description": "业务描述",\n'
            '  "trigger_keywords": ["关键词"],\n'
            '  "trigger_examples": ["用户可能问法"],\n'
            '  "when_to_use": "何时使用",\n'
            '  "parameters": [{"name": "...", "type": "date|string|number", '
            '"extract_hint": "...", "default_expr": "TODAY|MONTH_START|NULL|...", '
            '"required": true, "confidence": 0.8}],\n'
            '  "implementation_type": "sql_template|stored_procedure",\n'
            '  "call_template": "可执行 SQL 模板或空字符串",\n'
            '  "output_schema": [{"column": "...", "semantic": "...", "unit": "-", '
            '"role": "dimension|metric", "confidence": 0.8}],\n'
            '  "steps": [{"step": 1, "name": "...", "purpose": "...", '
            '"key_rules": ["..."], "output_columns": ["..."], "confidence": 0.8}],\n'
            '  "attribution_hints": "归因分析提示",\n'
            '  "raw_sql": "原始 SQL",\n'
            '  "ai_confidence": 0.8,\n'
            '  "low_confidence_fields": [{"path": "...", "confidence": 0.6, '
            '"reason": "..."}]\n'
            "}\n\n"
            f"SQL 草稿（已将变量替换成占位符，禁止还原变量值）：\n{sql}\n\n"
            f"系统预解析参考（可修正，不要盲从）：\n{_compact_reference(reference)}\n"
        )
    )
    return [system, human]


def _description_analysis_prompt(
    payload: dict[str, Any],
    dataset_context: dict[str, Any] | None = None,
) -> list:
    """构建业务场景创建蓝图的 AI 提示词。"""
    system = SystemMessage(content=BLUEPRINT_DESCRIPTION_SYSTEM)
    context_text = json.dumps(dataset_context or {}, ensure_ascii=False, separators=(",", ":"))
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    human = HumanMessage(
        content=(
            "请基于业务场景描述生成分析蓝图草案。\n\n"
            "设计原则：\n"
            "1. 用户输入是声明式业务语义，不是 SQL 或执行步骤，不要要求用户维护 SQL。\n"
            "2. trigger_keywords 和 trigger_examples 要面向真实业务问法。\n"
            "3. parameters 只保留自然语言问题中常见的业务约束，如时间范围、区域、品类等。\n"
            "4. output_schema 描述期望输出的业务字段，不要虚构数据库列名。\n"
            "5. steps 描述分析思路和业务判断链路，不要写 SQL 处理过程。\n"
            "6. implementation_type 固定输出 semantic_plan，call_template 和 raw_sql 固定为空字符串。\n"
            "7. low_confidence_fields 标记需要数据团队确认的口径、字段或指标。\n\n"
            "输出 JSON Schema：\n"
            "{\n"
            '  "name": "蓝图名称",\n'
            '  "description": "业务描述",\n'
            '  "trigger_keywords": ["关键词"],\n'
            '  "trigger_examples": ["用户可能问法"],\n'
            '  "when_to_use": "何时使用",\n'
            '  "parameters": [{"name": "...", "type": "date|string|number", '
            '"extract_hint": "...", "default_expr": "TODAY|MONTH_START|NULL|...", '
            '"required": true, "confidence": 0.8}],\n'
            '  "implementation_type": "semantic_plan",\n'
            '  "call_template": "",\n'
            '  "output_schema": [{"column": "...", "semantic": "...", "unit": "-", '
            '"role": "dimension|metric", "confidence": 0.8}],\n'
            '  "steps": [{"step": 1, "name": "...", "purpose": "...", '
            '"key_rules": ["..."], "output_columns": ["..."], "confidence": 0.8}],\n'
            '  "attribution_hints": "归因分析提示",\n'
            '  "raw_sql": "",\n'
            '  "ai_confidence": 0.8,\n'
            '  "low_confidence_fields": [{"path": "...", "confidence": 0.6, '
            '"reason": "..."}]\n'
            "}\n\n"
            f"业务场景输入：\n{payload_text}\n\n"
            f"当前数据集语义参考（可使用，不要盲从）：\n{context_text}\n"
        )
    )
    return [system, human]


def _ensure_list(value: Any) -> list:
    """把 AI 返回字段规范成 list。"""
    return value if isinstance(value, list) else []


def _sanitize_param_defaults(
    params: list[dict[str, Any]], reference: dict[str, Any]
) -> list[dict[str, Any]]:
    """清理参数默认值，避免保留变量实际值。"""
    reference_defaults = {
        item.get("name"): item.get("default_expr")
        for item in reference.get("parameters", [])
        if isinstance(item, dict)
    }
    cleaned: list[dict[str, Any]] = []
    for item in params:
        if not isinstance(item, dict):
            continue
        param = dict(item)
        name = param.get("name")
        default_expr = param.get("default_expr")
        if isinstance(default_expr, str):
            looks_like_value = bool(
                re.match(r"^['\"]?.+['\"]?$", default_expr)
                and default_expr.upper() not in ("TODAY", "MONTH_START", "NULL")
            )
            if looks_like_value:
                param["default_expr"] = (
                    reference_defaults.get(name) or _normalize_param(str(name))[3]
                )
        cleaned.append(param)
    return cleaned


def _sanitize_steps(
    steps: list,
    context: dict[str, set[str]],
    fallback: list | None = None,
) -> list[dict[str, Any]]:
    """清理步骤中的参数痕迹。"""
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            continue
        key_rules = _sanitize_text_list(
            _ensure_list(item.get("key_rules")),
            context,
            drop_if_protected=True,
        )
        output_columns = [
            str(column)
            for column in _ensure_list(item.get("output_columns"))
            if not _contains_protected_token(str(column), context)
        ]
        step = {
            "step": item.get("step") or index,
            "name": _scrub_protected_text(item.get("name"), context) or f"分析步骤 {index}",
            "purpose": _scrub_protected_text(item.get("purpose"), context),
            "key_rules": key_rules,
            "output_columns": output_columns,
            "confidence": item.get("confidence"),
        }
        cleaned.append(step)
    if cleaned:
        return cleaned
    if fallback:
        return _sanitize_steps(fallback, context)
    return []


def _sanitize_low_confidence_fields(
    fields: list,
    context: dict[str, set[str]],
    fallback: list | None = None,
) -> list[dict[str, Any]]:
    """清理低置信字段说明中的参数痕迹。"""
    cleaned: list[dict[str, Any]] = []
    for item in fields:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        reason = str(item.get("reason") or "")
        if _contains_protected_token(path, context) or _contains_protected_token(reason, context):
            continue
        cleaned.append(
            {
                "path": path,
                "confidence": item.get("confidence"),
                "reason": _scrub_protected_text(reason, context),
            }
        )
    if cleaned:
        return cleaned
    if fallback:
        return _sanitize_low_confidence_fields(fallback, context)
    return []


def _merge_ai_blueprint(
    ai_result: dict[str, Any],
    reference: dict[str, Any],
    sql: str,
    variable_context: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """校验并补齐 AI 返回的蓝图字段。"""
    if not ai_result:
        raise ValueError("AI 未返回有效 JSON")
    context = variable_context or {"names": set(), "values": set()}

    implementation_type = ai_result.get("implementation_type") or reference["implementation_type"]
    if implementation_type not in ("sql_template", "stored_procedure"):
        implementation_type = reference["implementation_type"]

    call_template = ai_result.get("call_template")
    if implementation_type == "sql_template" and not call_template:
        call_template = reference.get("call_template") or _sanitize_sql_variables(
            _strip_comments(sql)
        )
    if implementation_type == "stored_procedure" and call_template is None:
        call_template = ""
    if call_template:
        call_template = _sanitize_sql_variables(str(call_template))

    raw_sql = _sanitize_sql_variables(str(ai_result.get("raw_sql") or sql))
    parameters = _ensure_list(ai_result.get("parameters")) or reference["parameters"]
    context = _extend_context_with_ai_params(context, parameters)
    parameters = _sanitize_param_defaults(parameters, reference)

    confidence = ai_result.get("ai_confidence", reference.get("ai_confidence", 0.7))
    try:
        confidence = round(float(confidence), 2)
    except (TypeError, ValueError):
        confidence = reference.get("ai_confidence", 0.7)

    result = {
        "name": _scrub_protected_text(ai_result.get("name") or reference["name"], context)
        or reference["name"],
        "description": _scrub_protected_text(
            ai_result.get("description") or reference["description"],
            context,
        )
        or reference["description"],
        "trigger_keywords": _sanitize_text_list(
            _ensure_list(ai_result.get("trigger_keywords")),
            context,
            fallback=reference["trigger_keywords"],
        ),
        "trigger_examples": _sanitize_text_list(
            _ensure_list(ai_result.get("trigger_examples")),
            context,
            fallback=reference["trigger_examples"],
        ),
        "when_to_use": _scrub_protected_text(
            ai_result.get("when_to_use") or reference["when_to_use"],
            context,
        )
        or reference["when_to_use"],
        "parameters": parameters,
        "implementation_type": implementation_type,
        "call_template": call_template,
        "output_schema": _ensure_list(ai_result.get("output_schema")) or reference["output_schema"],
        "steps": _sanitize_steps(
            _ensure_list(ai_result.get("steps")),
            context,
            fallback=reference["steps"],
        ),
        "attribution_hints": _scrub_protected_text(
            ai_result.get("attribution_hints") or reference["attribution_hints"],
            context,
        )
        or reference["attribution_hints"],
        "raw_sql": raw_sql,
        "ai_confidence": confidence,
        "low_confidence_fields": _sanitize_low_confidence_fields(
            _ensure_list(ai_result.get("low_confidence_fields")),
            context,
            fallback=reference["low_confidence_fields"],
        ),
        "analysis_engine": "llm",
    }
    return result


def _manual_reference(
    payload: dict[str, Any], dataset_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """根据业务场景输入生成手动蓝图的兜底草案。"""
    name = (payload.get("name") or "").strip() or "业务场景分析蓝图"
    scenario = (payload.get("business_scenario") or "").strip()
    examples = _ensure_list(payload.get("example_questions"))
    rules = (payload.get("business_rules") or "").strip()
    expected_output = (payload.get("expected_output") or "").strip()
    metrics = [
        item.get("display_name") or item.get("name")
        for item in (dataset_context or {}).get("metrics", [])
        if isinstance(item, dict)
    ]
    dimensions = [
        item.get("display_name") or item.get("name")
        for item in (dataset_context or {}).get("dimensions", [])
        if isinstance(item, dict)
    ]
    trigger_keywords = [name]
    trigger_keywords.extend(metrics[:4])
    trigger_keywords.extend(dimensions[:4])
    trigger_keywords = [item for item in trigger_keywords if item][:8]
    return {
        "name": name,
        "description": scenario or name,
        "trigger_keywords": trigger_keywords or ["分析", "归因"],
        "trigger_examples": examples or [f"{name}怎么看", f"{name}有哪些异常"],
        "when_to_use": scenario or f"当用户询问{name}相关问题时使用。",
        "parameters": [
            {
                "name": "date_range",
                "type": "date",
                "extract_hint": "用户提到的分析时间范围，未提及时默认本月",
                "default_expr": "MONTH_START",
                "required": False,
                "confidence": 0.72,
            }
        ],
        "implementation_type": "semantic_plan",
        "call_template": "",
        "output_schema": [],
        "steps": [
            {
                "step": 1,
                "name": "理解业务问题",
                "purpose": "识别用户关注的业务对象、指标和分析范围",
                "key_rules": [rule for rule in [rules, expected_output] if rule],
                "output_columns": [],
                "confidence": 0.7,
            }
        ],
        "attribution_hints": expected_output or "优先解释关键指标变化、异常维度和主要影响因素。",
        "raw_sql": "",
        "ai_confidence": 0.72,
        "low_confidence_fields": [
            {
                "path": "execution",
                "confidence": 0.5,
                "reason": "手动创建蓝图不包含可执行 SQL，需要后续关联执行逻辑或语义查询能力",
            }
        ],
    }


def analyze_sql_for_blueprint(sql: str, db: Session | None = None) -> dict[str, Any]:
    """调用 AI 把 SQL 草稿转换为分析蓝图草案。"""
    total_started_at = time.perf_counter()
    preprocess_started_at = time.perf_counter()
    variable_context = _variable_protection_context(sql)
    sanitized_sql = _sanitize_sql_variables(_strip_comments(sql))
    reference = _rule_based_analyze_sql(sanitized_sql)
    preprocess_ms = int((time.perf_counter() - preprocess_started_at) * 1000)

    prompt_started_at = time.perf_counter()
    messages = _analysis_prompt(sanitized_sql, reference)
    prompt_ms = int((time.perf_counter() - prompt_started_at) * 1000)

    llm_client_started_at = time.perf_counter()
    llm = get_llm(temperature=0.1, role="blueprint", db=db)
    llm_client_ms = int((time.perf_counter() - llm_client_started_at) * 1000)

    llm_invoke_started_at = time.perf_counter()
    response = llm.invoke(messages)
    llm_invoke_ms = int((time.perf_counter() - llm_invoke_started_at) * 1000)

    parse_started_at = time.perf_counter()
    ai_result = safe_json_parse(str(response.content))
    parse_json_ms = int((time.perf_counter() - parse_started_at) * 1000)

    merge_started_at = time.perf_counter()
    result = _merge_ai_blueprint(ai_result, reference, sanitized_sql, variable_context)
    merge_ms = int((time.perf_counter() - merge_started_at) * 1000)
    total_ms = int((time.perf_counter() - total_started_at) * 1000)
    prompt_chars = sum(len(str(message.content)) for message in messages)
    result["analysis_timing_ms"] = {
        "preprocess": preprocess_ms,
        "prompt_build": prompt_ms,
        "llm_client": llm_client_ms,
        "llm_invoke": llm_invoke_ms,
        "llm_total": llm_client_ms + llm_invoke_ms,
        "parse_json": parse_json_ms,
        "merge": merge_ms,
        "total": total_ms,
        "prompt_chars": prompt_chars,
        "sql_chars": len(sanitized_sql),
    }
    logger.info(
        (
            "分析蓝图 AI 阶段耗时: preprocess_ms=%s, prompt_ms=%s, "
            "llm_client_ms=%s, llm_invoke_ms=%s, parse_json_ms=%s, "
            "merge_ms=%s, total_ms=%s, prompt_chars=%s, sql_chars=%s"
        ),
        preprocess_ms,
        prompt_ms,
        llm_client_ms,
        llm_invoke_ms,
        parse_json_ms,
        merge_ms,
        total_ms,
        prompt_chars,
        len(sanitized_sql),
    )
    return result


def analyze_description_for_blueprint(
    payload: dict[str, Any],
    dataset_context: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """调用 AI 把业务场景描述转换为分析蓝图草案。"""
    total_started_at = time.perf_counter()
    reference = _manual_reference(payload, dataset_context)
    messages = _description_analysis_prompt(payload, dataset_context)

    llm_client_started_at = time.perf_counter()
    llm = get_llm(temperature=0.1, role="blueprint", db=db)
    llm_client_ms = int((time.perf_counter() - llm_client_started_at) * 1000)

    llm_invoke_started_at = time.perf_counter()
    response = llm.invoke(messages)
    llm_invoke_ms = int((time.perf_counter() - llm_invoke_started_at) * 1000)

    parse_started_at = time.perf_counter()
    ai_result = safe_json_parse(str(response.content))
    parse_json_ms = int((time.perf_counter() - parse_started_at) * 1000)

    merge_started_at = time.perf_counter()
    result = _merge_ai_blueprint(ai_result, reference, "", {"names": set(), "values": set()})
    result["implementation_type"] = "semantic_plan"
    result["call_template"] = ""
    result["raw_sql"] = ""
    result["analysis_engine"] = "llm"
    result["analysis_source"] = "business_description"
    merge_ms = int((time.perf_counter() - merge_started_at) * 1000)
    total_ms = int((time.perf_counter() - total_started_at) * 1000)
    prompt_chars = sum(len(str(message.content)) for message in messages)
    result["analysis_timing_ms"] = {
        "preprocess": 0,
        "prompt_build": 0,
        "llm_client": llm_client_ms,
        "llm_invoke": llm_invoke_ms,
        "llm_total": llm_client_ms + llm_invoke_ms,
        "parse_json": parse_json_ms,
        "merge": merge_ms,
        "total": total_ms,
        "prompt_chars": prompt_chars,
        "sql_chars": 0,
    }
    logger.info(
        (
            "手动蓝图 AI 阶段耗时: llm_client_ms=%s, llm_invoke_ms=%s, "
            "parse_json_ms=%s, merge_ms=%s, total_ms=%s, prompt_chars=%s"
        ),
        llm_client_ms,
        llm_invoke_ms,
        parse_json_ms,
        merge_ms,
        total_ms,
        prompt_chars,
    )
    return result


def _build_description(
    tables: list[str],
    metrics: list[str],
    dimensions: list[str],
) -> str:
    """生成蓝图描述。"""
    source = "、".join(tables[:3]) if tables else "SQL 草稿"
    metric_text = "、".join(metrics[:4]) if metrics else "查询结果"
    dim_text = "，按" + "、".join(dimensions[:4]) + "分析" if dimensions else ""
    return f"基于 {source} 生成 {metric_text}{dim_text} 的固定分析蓝图。"


def _trigger_examples(name: str, keywords: list[str]) -> list[str]:
    """生成蓝图触发示例。"""
    main = keywords[0] if keywords else name
    return [f"查看{main}分析", f"{name}最新情况"]


def _attribution_hints(metrics: list[str], dimensions: list[str]) -> str:
    """生成归因提示。"""
    if metrics and dimensions:
        return (
            f"优先关注{'、'.join(metrics[:3])}在{'、'.join(dimensions[:3])}上的变化、排名和异常值。"
        )
    if metrics:
        return f"优先关注{'、'.join(metrics[:3])}的趋势、异常和与预期的偏差。"
    return "优先解释输出结果中的关键字段、筛选条件和排序规则。"


def _overall_confidence(params: list[dict[str, Any]], output_schema: list[dict[str, Any]]) -> float:
    """计算蓝图草案整体置信度。"""
    scores = [item.get("confidence", 0.7) for item in params + output_schema]
    if not scores:
        return 0.62
    return round(sum(scores) / len(scores), 2)
