# ============================================================
# File Name   : dataset_context.py
# Description:
#   数据集问数上下文组装服务。
#
# Responsibilities:
#   - 为 SQL 生成链路组装语义资产、所选表字段、样例和权限上下文。
#   - 按 token 预算裁剪 prompt 文本，并优先保留命中资产。
#   - 返回调试摘要，便于排查上下文过大或资产缺失问题。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.dataset import (
    AnalysisBlueprint,
    BusinessTerm,
    DatasetSourceTable,
    SemanticDataset,
    SemanticDimension,
    SemanticMetric,
    SourceColumn,
    SourceTable,
)
from app.utils.query_constraints import normalize_query_constraints, render_query_constraints_instruction
from app.utils.schema_formatter import ROLE_CODE, UNUSED_ROLES, estimate_tokens, _is_enum_dim

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_TOKEN_BUDGET = 4000


@dataclass
class ContextEntry:
    """可裁剪上下文条目。"""

    section: str
    text: str
    asset_type: str
    asset_id: int | None = None
    asset_name: str | None = None
    priority: int = 0
    pinned: bool = False
    original_index: int = 0


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数，中文和英文混合场景按 4 字符折算。"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _normalize_text(text: Any) -> str:
    """将文本归一化为可做包含匹配的形式。"""
    return re.sub(r"\s+", "", str(text or "").lower())


def _coerce_text_list(value: Any) -> list[str]:
    """兼容 JSON 字段中的字符串列表。"""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _compact_json(value: Any) -> str:
    """压缩 JSON，减少上下文占用。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _asset_tokens(*values: Any) -> list[str]:
    """生成资产可匹配词。"""
    tokens: list[str] = []
    for value in values:
        if isinstance(value, list):
            tokens.extend(_coerce_text_list(value))
        elif value not in (None, "", [], {}):
            tokens.append(str(value))
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = _normalize_text(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(token)
    return deduped


def _matched_ref_keys(matched_assets: dict[str, Any] | None) -> set[tuple[str, int]]:
    """从语义资产解析结果中提取显式命中资产。"""
    keys: set[tuple[str, int]] = set()
    if not isinstance(matched_assets, dict):
        return keys

    for section in ("assets", "terms", "metrics", "dimensions", "fields", "blueprints"):
        items = matched_assets.get(section) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            asset_type = item.get("asset_type")
            asset_id = item.get("asset_id") or item.get("id")
            if asset_type and isinstance(asset_id, int):
                keys.add((str(asset_type), asset_id))
    return keys


def _question_hits(question: str, tokens: list[str]) -> bool:
    """判断资产候选词是否命中用户问题。"""
    normalized_question = _normalize_text(question)
    if not normalized_question:
        return False
    for token in tokens:
        normalized = _normalize_text(token)
        if normalized and normalized in normalized_question:
            return True
    return False


def _is_pinned(
    asset_type: str,
    asset_id: int | None,
    question: str,
    tokens: list[str],
    matched_ref_keys: set[tuple[str, int]],
) -> bool:
    """显式命中或问题文本命中的资产应优先保留。"""
    if asset_id is not None and (asset_type, asset_id) in matched_ref_keys:
        return True
    return _question_hits(question, tokens)


def _field_display_name(column: SourceColumn) -> str:
    """选择字段最适合问数上下文的展示名称。"""
    return (
        column.effective_desc
        or column.user_description
        or column.ai_description
        or column.column_comment
        or column.column_name
    )


def _column_structured(column: SourceColumn) -> dict[str, Any]:
    """将源字段转为结构化上下文对象。"""
    return {
        "id": column.id,
        "name": column.column_name,
        "column_name": column.column_name,
        "display_name": _field_display_name(column),
        "table_name": column.table.table_name if column.table else None,
        "data_type": column.data_type,
        "column_comment": column.column_comment,
        "business_desc": column.business_desc,
        "ai_description": column.ai_description,
        "user_description": column.user_description,
        "effective_desc": column.effective_desc,
        "semantic_role": column.user_semantic_role
        or column.ai_semantic_role
        or column.semantic_role,
        "default_agg": column.ai_suggested_agg or column.default_agg,
        "synonyms": column.suggested_synonyms or [],
        "sample_values": column.sample_values or [],
        "desc_source": column.desc_source,
        "review_status": column.review_status,
    }


def _metric_structured(metric: SemanticMetric) -> dict[str, Any]:
    """将指标转为结构化上下文对象。"""
    return {
        "id": metric.id,
        "name": metric.name,
        "display_name": metric.display_name,
        "expr": metric.expr,
        "table_name": metric.table_name,
        "time_field": metric.time_field,
        "filter_sql": metric.filter_sql,
        "synonyms": metric.synonyms or [],
    }


def _dimension_structured(dimension: SemanticDimension) -> dict[str, Any]:
    """将维度转为结构化上下文对象。"""
    return {
        "id": dimension.id,
        "name": dimension.name,
        "display_name": dimension.display_name,
        "column_name": dimension.column_name,
        "table_name": dimension.table_name,
        "join_to": dimension.join_to,
        "join_key": dimension.join_key,
        "synonyms": dimension.synonyms or [],
    }


def _term_structured(term: BusinessTerm) -> dict[str, Any]:
    """将业务术语转为结构化上下文对象。"""
    return {
        "id": term.id,
        "name": term.name,
        "display_name": term.display_name,
        "term_type": term.term_type,
        "aliases": term.aliases or [],
        "forbidden_aliases": term.forbidden_aliases or [],
        "definition": term.definition,
        "asset_links": [
            {
                "asset_type": link.asset_type,
                "asset_id": link.asset_id,
                "asset_name": link.asset_name,
            }
            for link in (term.asset_links or [])
        ],
    }


def _blueprint_structured(blueprint: AnalysisBlueprint) -> dict[str, Any]:
    """将分析蓝图转为结构化上下文对象。"""
    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "display_name": blueprint.name,
        "trigger_keywords": blueprint.trigger_keywords or [],
        "trigger_examples": blueprint.trigger_examples or [],
        "implementation_type": blueprint.implementation_type,
    }


def _metric_entry(
    metric: SemanticMetric,
    question: str,
    matched_ref_keys: set[tuple[str, int]],
    original_index: int,
) -> ContextEntry:
    synonyms = ", ".join(metric.synonyms or [])
    time_field = f" 时间字段={metric.time_field}" if metric.time_field else ""
    table = f" 表={metric.table_name}" if metric.table_name else ""
    text = (
        f"- {metric.name} ({metric.display_name}): 表达式={metric.expr}{table}{time_field}"
        f"{' 同义词=' + synonyms if synonyms else ''}"
        f"{' 过滤=' + metric.filter_sql if metric.filter_sql else ''}"
    )
    tokens = _asset_tokens(metric.name, metric.display_name, metric.synonyms)
    return ContextEntry(
        section="metrics",
        text=text,
        asset_type="metric",
        asset_id=metric.id,
        asset_name=metric.name,
        priority=90,
        pinned=_is_pinned("metric", metric.id, question, tokens, matched_ref_keys),
        original_index=original_index,
    )


def _dimension_entry(
    dimension: SemanticDimension,
    question: str,
    matched_ref_keys: set[tuple[str, int]],
    original_index: int,
) -> ContextEntry:
    synonyms = ", ".join(dimension.synonyms or [])
    enums = ", ".join(_coerce_text_list(dimension.enum_values)[:20])
    text = (
        f"- {dimension.name} ({dimension.display_name}): 字段={dimension.column_name}"
        f"{' 表=' + dimension.table_name if dimension.table_name else ''}"
        f"{' 枚举=' + enums if enums else ''}"
        f"{' 同义词=' + synonyms if synonyms else ''}"
    )
    tokens = _asset_tokens(dimension.name, dimension.display_name, dimension.synonyms, dimension.enum_values)
    return ContextEntry(
        section="dimensions",
        text=text,
        asset_type="dimension",
        asset_id=dimension.id,
        asset_name=dimension.name,
        priority=80,
        pinned=_is_pinned("dimension", dimension.id, question, tokens, matched_ref_keys),
        original_index=original_index,
    )


def _term_entry(
    term: BusinessTerm,
    question: str,
    matched_ref_keys: set[tuple[str, int]],
    original_index: int,
) -> ContextEntry:
    aliases = ", ".join(_coerce_text_list(term.aliases))
    link_text = ""
    links = [
        f"{link.asset_type}:{link.asset_name or link.asset_id}" for link in (term.asset_links or [])
    ]
    if links:
        link_text = f" 关联资产={', '.join(links[:8])}"
    text = (
        f"- {term.name} ({term.display_name}): 类型={term.term_type}"
        f"{' 同义词=' + aliases if aliases else ''}"
        f"{' 定义=' + term.definition if term.definition else ''}"
        f"{link_text}"
    )
    tokens = _asset_tokens(term.name, term.display_name, term.aliases)
    return ContextEntry(
        section="terms",
        text=text,
        asset_type="term",
        asset_id=term.id,
        asset_name=term.name,
        priority=70,
        pinned=_is_pinned("term", term.id, question, tokens, matched_ref_keys),
        original_index=original_index,
    )


def _blueprint_entry(
    blueprint: AnalysisBlueprint,
    question: str,
    matched_ref_keys: set[tuple[str, int]],
    original_index: int,
) -> ContextEntry:
    keywords = ", ".join(_coerce_text_list(blueprint.trigger_keywords)[:10])
    examples = " | ".join(_coerce_text_list(blueprint.trigger_examples)[:3])
    text = (
        f"- {blueprint.name}: 类型={blueprint.implementation_type}"
        f"{' 触发词=' + keywords if keywords else ''}"
        f"{' 示例=' + examples if examples else ''}"
    )
    tokens = _asset_tokens(
        blueprint.name,
        blueprint.description,
        blueprint.when_to_use,
        blueprint.trigger_keywords,
        blueprint.trigger_examples,
    )
    return ContextEntry(
        section="blueprints",
        text=text,
        asset_type="blueprint",
        asset_id=blueprint.id,
        asset_name=blueprint.name,
        priority=60,
        pinned=_is_pinned("blueprint", blueprint.id, question, tokens, matched_ref_keys),
        original_index=original_index,
    )


def _field_entry(
    column: SourceColumn,
    question: str,
    matched_ref_keys: set[tuple[str, int]],
    original_index: int,
) -> "ContextEntry | None":
    role = column.user_semantic_role or column.ai_semantic_role or column.semantic_role
    if role in UNUSED_ROLES:
        return None
    table_name = column.table.table_name if column.table else ""
    sample_values = ", ".join(str(v) for v in _coerce_text_list(column.sample_values)[:5])
    default_agg = column.ai_suggested_agg or column.default_agg
    text = (
        f"- {table_name}.{column.column_name} ({column.data_type})"
        f" 名称={_field_display_name(column)}"
        f"{' 角色=' + role if role else ''}"
        f"{' 默认聚合=' + default_agg if default_agg else ''}"
        f"{' 样例=' + sample_values if sample_values else ''}"
    )
    tokens = _asset_tokens(
        column.column_name,
        _field_display_name(column),
        column.column_comment,
        column.business_desc,
        column.suggested_synonyms,
        column.sample_values,
    )
    return ContextEntry(
        section="fields",
        text=text,
        asset_type="field",
        asset_id=column.id,
        asset_name=f"{table_name}.{column.column_name}" if table_name else column.column_name,
        priority=50,
        pinned=_is_pinned("field", column.id, question, tokens, matched_ref_keys),
        original_index=original_index,
    )


def _selected_source_columns(db: Session, dataset_id: int) -> tuple[list[DatasetSourceTable], list[SourceColumn]]:
    """读取数据集已选表和字段。"""
    selected_links = db.query(DatasetSourceTable).filter(DatasetSourceTable.dataset_id == dataset_id).all()
    selected_table_ids = [link.source_table_id for link in selected_links]
    if not selected_table_ids:
        return selected_links, []
    columns = (
        db.query(SourceColumn)
        .join(SourceTable, SourceColumn.table_id == SourceTable.id)
        .filter(SourceColumn.table_id.in_(selected_table_ids))
        .order_by(SourceTable.table_name, SourceColumn.ordinal_position)
        .all()
    )
    return selected_links, columns


def _section_title(section: str) -> str:
    """上下文分组标题。"""
    titles = {
        "metrics": "【指标列表】",
        "dimensions": "【维度列表】",
        "terms": "【业务术语】",
        "blueprints": "【分析蓝图】",
        "fields": "【所选表字段与样例】",
    }
    return titles[section]


def _trim_entries(
    fixed_text: str,
    entries: list[ContextEntry],
    token_budget: int,
) -> tuple[list[ContextEntry], dict[str, Any]]:
    """按预算裁剪上下文条目，命中资产优先。"""
    budget = max(200, int(token_budget or DEFAULT_CONTEXT_TOKEN_BUDGET))
    fixed_tokens = _estimate_tokens(fixed_text)
    sorted_entries = sorted(
        entries,
        key=lambda item: (not item.pinned, -item.priority, item.original_index),
    )
    selected: list[ContextEntry] = []
    used_tokens = fixed_tokens
    dropped: list[ContextEntry] = []

    for entry in sorted_entries:
        entry_tokens = _estimate_tokens(f"{_section_title(entry.section)}\n{entry.text}")
        if used_tokens + entry_tokens <= budget or entry.pinned:
            selected.append(entry)
            used_tokens += entry_tokens
        else:
            dropped.append(entry)

    selected.sort(key=lambda item: item.original_index)
    dropped.extend(entry for entry in entries if entry not in selected and entry not in dropped)
    return selected, {
        "token_budget": budget,
        "estimated_tokens": used_tokens,
        "fixed_tokens": fixed_tokens,
        "total_entries": len(entries),
        "retained_entries": len(selected),
        "dropped_entries": len(entries) - len(selected),
        "pinned_retained": sum(1 for entry in selected if entry.pinned),
        "dropped_assets": [
            {
                "asset_type": entry.asset_type,
                "asset_id": entry.asset_id,
                "asset_name": entry.asset_name,
                "section": entry.section,
            }
            for entry in dropped[:50]
        ],
    }


def _render_context(
    dataset: SemanticDataset,
    entries: list[ContextEntry],
    query_constraints: dict[str, Any],
    blueprint_context: str,
) -> str:
    """渲染最终 prompt 文本。"""
    lines = [
        "【数据集问数上下文】",
        "【语义层】",
        f"数据集: {dataset.name}",
        f"描述: {dataset.description or '无'}",
        "",
    ]
    if dataset.tables_json:
        lines.append(f"tables_json: {_compact_json(dataset.tables_json)}")
        lines.append("")
    constraints_text = render_query_constraints_instruction(query_constraints)
    if constraints_text:
        lines.append(constraints_text)
        lines.append("")
    if dataset.prompt_instructions and dataset.prompt_instructions.strip():
        lines.append("【数据集级 LLM 约束（硬性要求）】")
        lines.append(dataset.prompt_instructions.strip())
        lines.append("")
    if blueprint_context:
        lines.append(blueprint_context)
        lines.append("")

    section_order = ["metrics", "dimensions", "terms", "blueprints", "fields"]
    entries_by_section = {section: [] for section in section_order}
    for entry in entries:
        entries_by_section.setdefault(entry.section, []).append(entry)

    for section in section_order:
        lines.append(_section_title(section))
        section_entries = entries_by_section.get(section) or []
        if section_entries:
            lines.extend(entry.text for entry in section_entries)
        else:
            lines.append("（无）")
        lines.append("")

    lines.append("【权限信息】")
    lines.append("当前未配置数据集级权限策略；按数据集绑定数据源和已选表范围执行。")
    return "\n".join(lines).strip()


def _build_ddl_context(source_columns: list[SourceColumn], selected_links: list[DatasetSourceTable]) -> str:
    """构建所选表 DDL 文本，包含字段样例。"""
    lines = ["【所选表结构】", ""]
    if not selected_links:
        lines.append("（该数据集尚未选择任何表）")
        return "\n".join(lines)

    tables: dict[int, SourceTable] = {}
    for column in source_columns:
        if column.table:
            tables[column.table.id] = column.table

    for table in sorted(tables.values(), key=lambda item: item.table_name):
        lines.append(f"表: {table.table_name}")
        if table.table_comment:
            lines.append(f"  描述: {table.table_comment}")
        if table.business_desc:
            lines.append(f"  业务描述: {table.business_desc}")
        for column in [c for c in source_columns if c.table_id == table.id]:
            role = column.user_semantic_role or column.ai_semantic_role or column.semantic_role
            if role in UNUSED_ROLES:
                continue
            role_code = ROLE_CODE.get(role or "", "")
            default_agg = column.ai_suggested_agg or column.default_agg
            desc = (column.business_desc or column.column_comment or "").strip()
            sample_list = _coerce_text_list(column.sample_values)
            # 枚举维度：样例内联到括号
            if _is_enum_dim(role or "", sample_list):
                unique = list(dict.fromkeys(str(v) for v in sample_list))[:4]
                desc = f"{desc}({'/'.join(unique)})" if desc else f"({'/'.join(unique)})"
                sample_list = []
            agg_suffix = f",{default_agg}" if role_code == "M" and default_agg and default_agg.upper() != "NONE" else ""
            role_tag = f" [{role_code}{agg_suffix}]" if role_code else ""
            sample_tag = f" 样例={','.join(str(v) for v in sample_list[:3])}" if sample_list else ""
            desc_part = f' "{desc}"' if desc else ""
            lines.append(f"  - {column.column_name}:{column.data_type}{desc_part}{role_tag}{sample_tag}")
        lines.append("")
    return "\n".join(lines)


def build_dataset_query_context(
    db: Session,
    dataset_id: int,
    *,
    question: str = "",
    blueprint_context: str = "",
    matched_assets: dict[str, Any] | None = None,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
) -> dict[str, Any]:
    """组装数据集问数上下文。

    prompt 文本按 token_budget 裁剪；schema_structured 保持完整，供后续资产解析、
    DSL 编译和调试使用。
    """
    dataset = db.get(SemanticDataset, dataset_id)
    if not dataset:
        return {
            "schema_context": "",
            "schema_structured": None,
            "ddl_context": None,
            "query_constraints": normalize_query_constraints(None),
            "dataset_prompt_instructions": None,
            "dataset_context_debug": {
                "dataset_id": dataset_id,
                "error": "DATASET_NOT_FOUND",
                "token_budget": token_budget,
            },
        }

    metrics = db.query(SemanticMetric).filter(SemanticMetric.dataset_id == dataset.id).all()
    dimensions = db.query(SemanticDimension).filter(SemanticDimension.dataset_id == dataset.id).all()
    terms = (
        db.query(BusinessTerm)
        .filter(BusinessTerm.dataset_id == dataset.id, BusinessTerm.status == "active")
        .all()
    )
    blueprints = (
        db.query(AnalysisBlueprint)
        .filter(AnalysisBlueprint.dataset_id == dataset.id, AnalysisBlueprint.status == "active")
        .all()
    )
    selected_links, source_columns = _selected_source_columns(db, dataset.id)
    query_constraints = normalize_query_constraints(dataset.query_constraints)
    matched_ref_keys = _matched_ref_keys(matched_assets)

    entries: list[ContextEntry] = []
    original_index = 0
    for metric in metrics:
        entries.append(_metric_entry(metric, question, matched_ref_keys, original_index))
        original_index += 1
    for dimension in dimensions:
        entries.append(_dimension_entry(dimension, question, matched_ref_keys, original_index))
        original_index += 1
    for term in terms:
        entries.append(_term_entry(term, question, matched_ref_keys, original_index))
        original_index += 1
    for blueprint in blueprints:
        entries.append(_blueprint_entry(blueprint, question, matched_ref_keys, original_index))
        original_index += 1
    for column in source_columns:
        entry = _field_entry(column, question, matched_ref_keys, original_index)
        if entry:
            entries.append(entry)
        original_index += 1

    fixed_context = _render_context(dataset, [], query_constraints, blueprint_context)
    retained_entries, trim_debug = _trim_entries(fixed_context, entries, token_budget)
    schema_context = _render_context(dataset, retained_entries, query_constraints, blueprint_context)
    ddl_context = _build_ddl_context(source_columns, selected_links)
    prompt_instructions = dataset.prompt_instructions or ""
    if blueprint_context:
        prompt_instructions = f"{prompt_instructions}\n\n{blueprint_context}".strip()

    structured = {
        "dataset_name": dataset.name,
        "tables_json": dataset.tables_json or {},
        "metrics": [_metric_structured(metric) for metric in metrics],
        "dimensions": [_dimension_structured(dimension) for dimension in dimensions],
        "fields": [_column_structured(column) for column in source_columns],
        "terms": [_term_structured(term) for term in terms],
        "blueprints": [_blueprint_structured(blueprint) for blueprint in blueprints],
        "permissions": {
            "status": "not_configured",
            "description": "当前未配置数据集级权限策略；按数据集绑定数据源和已选表范围执行。",
        },
    }

    debug = {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "asset_counts": {
            "metrics": len(metrics),
            "dimensions": len(dimensions),
            "terms": len(terms),
            "blueprints": len(blueprints),
            "fields": len(source_columns),
            "selected_tables": len(selected_links),
        },
        "retained_counts": {
            section: sum(1 for entry in retained_entries if entry.section == section)
            for section in ("metrics", "dimensions", "terms", "blueprints", "fields")
        },
        "pinned_assets": [
            {
                "asset_type": entry.asset_type,
                "asset_id": entry.asset_id,
                "asset_name": entry.asset_name,
                "section": entry.section,
            }
            for entry in retained_entries
            if entry.pinned
        ],
        **trim_debug,
    }
    logger.info(
        "数据集问数上下文组装完成: dataset_id=%s tokens=%s/%s assets=%s retained=%s",
        dataset.id,
        debug["estimated_tokens"],
        debug["token_budget"],
        debug["asset_counts"],
        debug["retained_counts"],
    )

    return {
        "schema_context": schema_context,
        "schema_structured": structured,
        "ddl_context": ddl_context,
        "query_constraints": query_constraints,
        "dataset_prompt_instructions": prompt_instructions or None,
        "dataset_context_debug": debug,
        "schema_tokens": estimate_tokens(schema_context),
    }


__all__ = ["DEFAULT_CONTEXT_TOKEN_BUDGET", "build_dataset_query_context"]
