# ============================================================
# File Name   : answer_explanation.py
# Description:
#   问数回答解释包生成服务。
#
# Responsibilities:
#   - 汇总本轮问数使用的口径、数据来源、SQL 摘要和风险信息。
#   - 根据语义资产命中、歧义和执行链路计算回答置信度。
#   - 为最终回答和前端消息元数据提供稳定的结构化解释。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

from app.graph.state import AgentState
from app.schemas.dsl import get_dsl_item_name, normalize_dsl


LOW_CONFIDENCE_THRESHOLD = 0.75


def _clean_text(value: Any) -> str:
    """把任意值转为可展示的短文本。"""
    if value in (None, "", [], {}):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _dedupe(values: list[Any]) -> list[str]:
    """按展示文本去重，保留原顺序。"""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _asset_label(asset: dict[str, Any]) -> str:
    """选择语义资产最适合展示的名称。"""
    return _clean_text(
        asset.get("display_name")
        or asset.get("name")
        or asset.get("asset_name")
        or asset.get("column_name")
        or asset.get("asset_id")
    )


def _dsl_refs(dsl: dict[str, Any], key: str) -> list[str]:
    """读取 DSL 中的资产引用展示名。"""
    refs = dsl.get(key) or []
    if not isinstance(refs, list):
        return []
    return _dedupe([get_dsl_item_name(item) for item in refs])


def _sql_expression(sql: str | None, dialect: str | None) -> exp.Expression | None:
    """尽力解析 SQL；解析失败时由调用方降级为文本预览。"""
    if not sql:
        return None
    try:
        return sqlglot.parse_one(sql, read=dialect or None)
    except Exception:
        try:
            return sqlglot.parse_one(sql)
        except Exception:
            return None


def _sql_tables(expression: exp.Expression | None) -> list[str]:
    if not expression:
        return []
    return _dedupe([table.name for table in expression.find_all(exp.Table) if table.name])


def _sql_columns(expression: exp.Expression | None) -> list[str]:
    if not expression:
        return []
    columns = []
    for column in expression.find_all(exp.Column):
        name = ".".join(part for part in (column.table, column.name) if part)
        columns.append(name)
    return _dedupe(columns)


def _sql_preview(sql: str | None, limit: int = 500) -> str:
    text = _clean_text(sql)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _sql_summary(sql: str | None, state: AgentState) -> dict[str, Any]:
    """把 SQL 解析成前端可读摘要。"""
    dialect = state.get("datasource_dialect") or ""
    expression = _sql_expression(sql, dialect)
    summary: dict[str, Any] = {
        "dialect": dialect or None,
        "tables": _sql_tables(expression),
        "columns": _sql_columns(expression),
        "preview": _sql_preview(sql),
        "parse_ok": expression is not None,
    }
    if not expression:
        return summary

    where = expression.find(exp.Where)
    group = expression.find(exp.Group)
    order = expression.find(exp.Order)
    limit = expression.find(exp.Limit)
    summary.update(
        {
            "filters": _clean_text(where.sql(dialect=dialect or None)) if where else "",
            "group_by": _clean_text(group.sql(dialect=dialect or None)) if group else "",
            "order_by": _clean_text(order.sql(dialect=dialect or None)) if order else "",
            "limit": _clean_text(limit.expression.sql(dialect=dialect or None)) if limit else "",
        }
    )
    return summary


def _source_from_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从语义资产命中里提取表字段来源。"""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for asset in assets:
        table = _clean_text(asset.get("table_name"))
        column = _clean_text(asset.get("column_name"))
        if not table and not column:
            continue
        key = (table, column, _clean_text(asset.get("asset_type")))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "table": table or None,
                "column": column or None,
                "asset_type": asset.get("asset_type"),
                "asset_id": asset.get("asset_id"),
                "name": _asset_label(asset),
                "source": "semantic_asset",
            }
        )
    return out


def _source_from_sql(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """从 SQL 摘要兜底生成来源。"""
    out = [{"table": table, "column": None, "source": "sql_parse"} for table in summary["tables"]]
    if not out:
        return []
    known_tables = {item["table"] for item in out}
    for column in summary.get("columns") or []:
        table = column.split(".", 1)[0] if "." in column else None
        if table and table in known_tables:
            out.append({"table": table, "column": column.split(".", 1)[1], "source": "sql_parse"})
    return out


def _caliber(state: AgentState, dsl: dict[str, Any]) -> dict[str, Any]:
    """汇总指标、维度、术语、蓝图和约束口径。"""
    semantic = state.get("semantic_asset_resolution") or {}
    terms = semantic.get("terms") or []
    metrics = semantic.get("metrics") or []
    dimensions = semantic.get("dimensions") or []
    blueprints = semantic.get("blueprints") or []
    term_normalization = state.get("term_normalization") or {}
    route_payload = state.get("route_payload") or {}
    query_constraints = state.get("query_constraints") or {}

    blueprint_names = [_asset_label(asset) for asset in blueprints]
    if route_payload.get("blueprint_id"):
        blueprint_names.append(route_payload.get("name") or route_payload.get("blueprint_id"))
    if state.get("blueprint_match"):
        blueprint_names.append((state.get("blueprint_match") or {}).get("name"))

    filters = dsl.get("filters") or []
    filter_fields = []
    if isinstance(filters, list):
        filter_fields = [get_dsl_item_name(item.get("field")) for item in filters if isinstance(item, dict)]

    return {
        "metrics": _dedupe([_asset_label(asset) for asset in metrics] + _dsl_refs(dsl, "metrics")),
        "dimensions": _dedupe(
            [_asset_label(asset) for asset in dimensions] + _dsl_refs(dsl, "dimensions")
        ),
        "terms": _dedupe(
            [_asset_label(asset) for asset in terms]
            + [_asset_label(item) for item in term_normalization.get("matched_terms") or []]
            + _dsl_refs(dsl, "terms")
        ),
        "blueprints": _dedupe(blueprint_names + _dsl_refs(dsl, "blueprints")),
        "blueprint_params": route_payload.get("params") or {},
        "fields": _dedupe(_dsl_refs(dsl, "fields")),
        "filters": _dedupe(filter_fields),
        "time_range": dsl.get("time_range"),
        "limit": dsl.get("limit") or query_constraints.get("default_limit"),
        "query_constraints": query_constraints,
        "generation_mode": state.get("generation_mode"),
    }


def _risk_items(state: AgentState, sql_summary: dict[str, Any]) -> list[dict[str, str]]:
    """根据链路状态整理风险提示。"""
    risks: list[dict[str, str]] = []
    semantic = state.get("semantic_asset_resolution") or {}
    term_normalization = state.get("term_normalization") or {}
    context_debug = state.get("dataset_context_debug") or {}

    if state.get("generation_mode") == "inferred":
        risks.append({"code": "inferred_sql", "message": "本次查询基于表结构推断，未完全命中已维护指标。"})
    if state.get("generation_mode") == "analysis_blueprint_semantic":
        risks.append({"code": "semantic_blueprint", "message": "命中的是语义计划蓝图，实际 SQL 仍由问数链路生成。"})
    if semantic.get("ambiguities"):
        risks.append({"code": "asset_ambiguity", "message": "存在多个置信度接近的语义资产，需要确认口径。"})
    if semantic.get("unresolved"):
        risks.append({"code": "unresolved_asset", "message": "部分指标、维度或字段未在语义层中明确解析。"})
    if term_normalization.get("has_conflict"):
        risks.append({"code": "term_conflict", "message": "业务术语存在同名或同义词冲突。"})
    if state.get("sql_retry_trace"):
        risks.append({"code": "sql_retry", "message": "查询执行链路存在不稳定，建议复核字段口径和结果。"})
    if state.get("sql_diagnosis") or state.get("sql_audit_result"):
        risks.append({"code": "sql_diagnosis", "message": "SQL 链路出现过诊断信息，建议复核配置或结果。"})
    if context_debug.get("dropped_entries", 0) > 0:
        risks.append({"code": "context_trimmed", "message": "数据集上下文因 token 预算被裁剪，未保留所有资产。"})
    if state.get("error"):
        risks.append({"code": "workflow_error", "message": f"链路存在错误：{state.get('error')}"})
    if not sql_summary.get("parse_ok") and sql_summary.get("preview"):
        risks.append({"code": "sql_parse_failed", "message": "SQL 摘要解析失败，仅展示 SQL 文本预览。"})
    if not state.get("sql_result") and not state.get("sql"):
        risks.append({"code": "no_sql_result", "message": "本次没有成功执行 SQL，回答只基于路由或澄清信息。"})

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in risks:
        if item["code"] in seen:
            continue
        seen.add(item["code"])
        deduped.append(item)
    return deduped


def _confidence(state: AgentState, risks: list[dict[str, str]], dsl: dict[str, Any]) -> dict[str, Any]:
    """计算回答置信度。"""
    score = 0.92
    reasons: list[str] = []
    risk_codes = {item["code"] for item in risks}

    deductions = {
        "asset_ambiguity": (0.28, "语义资产存在歧义"),
        "term_conflict": (0.35, "业务术语存在冲突"),
        "unresolved_asset": (0.2, "部分资产未解析"),
        "inferred_sql": (0.18, "查询基于表结构推断"),
        "semantic_blueprint": (0.1, "语义计划蓝图仍需生成 SQL"),
        "sql_retry": (0.08, "查询执行链路存在不稳定"),
        "sql_diagnosis": (0.18, "SQL 链路存在诊断"),
        "context_trimmed": (0.08, "上下文被裁剪"),
        "workflow_error": (0.3, "工作流存在错误"),
        "no_sql_result": (0.25, "未成功执行 SQL"),
        "sql_parse_failed": (0.05, "SQL 摘要解析失败"),
    }
    for code, (deduction, reason) in deductions.items():
        if code in risk_codes:
            score -= deduction
            reasons.append(reason)

    dsl_confidence = dsl.get("confidence")
    if isinstance(dsl_confidence, int | float):
        score = min(score, float(dsl_confidence))
        if dsl_confidence < LOW_CONFIDENCE_THRESHOLD:
            reasons.append("DSL 生成置信度偏低")

    if (state.get("semantic_asset_resolution") or {}).get("ambiguities"):
        score = min(score, 0.62)
    if (state.get("semantic_asset_resolution") or {}).get("unresolved"):
        score = min(score, 0.72)
    if (state.get("term_normalization") or {}).get("has_conflict"):
        score = min(score, 0.45)

    score = round(max(0.05, min(score, 0.99)), 2)
    if score < LOW_CONFIDENCE_THRESHOLD:
        level = "low"
    elif score < 0.88:
        level = "medium"
    else:
        level = "high"

    return {
        "score": score,
        "level": level,
        "threshold": LOW_CONFIDENCE_THRESHOLD,
        "reasons": _dedupe(reasons) or ["语义资产和 SQL 执行链路未发现明显风险"],
    }


def _confirmation(confidence: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """低置信时生成用户确认提示。"""
    required = confidence.get("level") == "low"
    if not required:
        return {"required": False, "message": ""}

    semantic = state.get("semantic_asset_resolution") or {}
    ambiguity = (semantic.get("ambiguities") or [{}])[0]
    hint = ambiguity.get("resolution_hint")
    if hint:
        message = hint
    elif semantic.get("unresolved"):
        names = "、".join(
            _dedupe([item.get("text") for item in semantic.get("unresolved") or []])[:3]
        )
        message = f"请确认“{names}”对应的指标、维度或字段口径后再继续。"
    elif (state.get("term_normalization") or {}).get("has_conflict"):
        message = "请先确认业务术语口径，避免基于错误定义继续查询。"
    else:
        message = "当前回答置信度偏低，请确认口径、数据来源或时间范围后再继续。"
    return {"required": True, "message": message}


def build_answer_explanation(state: AgentState) -> dict[str, Any]:
    """生成最终回答解释包。"""
    raw_dsl = state.get("dsl") or {}
    dsl = normalize_dsl(raw_dsl) if isinstance(raw_dsl, dict) else {}
    sql = state.get("sql") or (dsl.get("direct_sql") if isinstance(dsl, dict) else None)
    summary = _sql_summary(sql, state)
    semantic = state.get("semantic_asset_resolution") or {}
    sources = _source_from_assets(semantic.get("assets") or [])
    if not sources:
        sources = _source_from_sql(summary)
    risks = _risk_items(state, summary)
    confidence = _confidence(state, risks, dsl)

    return {
        "version": "1.0",
        "caliber": _caliber(state, dsl),
        "data_sources": sources,
        "sql_summary": summary,
        "confidence": confidence,
        "risks": risks,
        "confirmation": _confirmation(confidence, state),
    }


def render_answer_explanation_markdown(explanation: dict[str, Any]) -> str:
    """把解释包渲染为可追加到最终回答的 Markdown。"""
    caliber = explanation.get("caliber") or {}
    sql_summary = explanation.get("sql_summary") or {}
    confidence = explanation.get("confidence") or {}
    risks = explanation.get("risks") or []
    confirmation = explanation.get("confirmation") or {}
    sources = explanation.get("data_sources") or []

    source_labels = _dedupe(
        [
            ".".join(part for part in (item.get("table"), item.get("column")) if part)
            for item in sources
            if isinstance(item, dict)
        ]
    )
    caliber_bits = []
    for label, key in (("指标", "metrics"), ("维度", "dimensions"), ("术语", "terms"), ("蓝图", "blueprints")):
        values = caliber.get(key) or []
        if values:
            caliber_bits.append(f"{label}：{'、'.join(values[:6])}")
    if caliber.get("time_range"):
        caliber_bits.append(f"时间范围：{caliber['time_range']}")
    if caliber.get("limit"):
        caliber_bits.append(f"返回上限：{caliber['limit']}")

    lines = ["", "---", "### 口径与可信度"]
    lines.append(f"- 口径说明：{'; '.join(caliber_bits) if caliber_bits else '未识别到明确语义口径'}")
    lines.append(f"- 数据来源：{'、'.join(source_labels[:8]) if source_labels else '未能确定具体表或字段'}")
    if sql_summary.get("preview"):
        table_text = "、".join(sql_summary.get("tables") or []) or "未解析到表"
        lines.append(f"- SQL 摘要：涉及 {table_text}；预览 `{sql_summary['preview'][:160]}`")
    else:
        lines.append("- SQL 摘要：本次未生成 SQL")
    lines.append(
        f"- 置信度：{confidence.get('level', 'unknown')}（{confidence.get('score', 0):.2f}）"
    )
    risk_text = "；".join(item.get("message", "") for item in risks if item.get("message"))
    lines.append(f"- 风险提示：{risk_text if risk_text else '未发现明显风险'}")
    if confirmation.get("required"):
        lines.append(f"- 需要确认：{confirmation.get('message')}")
    return "\n".join(lines)
