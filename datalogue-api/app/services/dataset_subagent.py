# ============================================================
# File Name   : dataset_subagent.py
# Description:
#   Phase 5/6/7：DatasetSubAgent 门面。
#
#   职责：把单 dataset 业务能力（schema/term/metric/dimension/blueprint）封装到
#   DatasetSubAgent 对象，让 LeadAgent（chat 层）通过它调能力，避免 chat.py 直接
#   import services/analysis_blueprint.py / graph/nodes.py 私有辅助。
#
#   边界：
#   - LeadAgent（chat.py）只与本对象交互，不直接查 AnalysisBlueprint / 拼参数 / 跑 SQL
#   - Graph（nodes.py）不感知本对象存在，只读 initial_state 注入的 blueprint_context 等
#   - 服务调用方通过 dataclass 字段 db 访问 ORM；业务逻辑委托给 services/analysis_blueprint.py
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dataset import AnalysisBlueprint
from app.services.analysis_blueprint import (
    blueprint_params_from_time_context,
    execute_analysis_blueprint,
)
from app.services.dataset_manifest import evaluate_manifest_runtime_guard
from app.services.observability.tracer import get_observability_tracer
from app.services.query_plan_compiler import compile_query_plan_to_sql
from app.services.runner import DatasetSubAgentRequest, InProcessDatasetSubAgentRunner
from app.services.subagent_planning import (
    AssetDetailService,
    PlannerDetailLoop,
    QueryPlan,
    SubAgentEvent,
    build_blueprint_reference_context,
    build_clarify_result,
    build_query_plan_compiler_context,
    build_reject_result,
    plan_query,
    plan_query_with_detail_context,
    recall_candidate_assets,
)

logger = logging.getLogger(__name__)


def _dsa_end_span(
    tracer: Any,
    trace_context: Any | None,
    *,
    node: str,
    started_at: float,
    output_payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """结束 SubAgent 自有 span；观测失败不影响主链路。"""

    try:
        tracer.end_span(
            trace_context,
            node=node,
            output_payload=output_payload or {},
            elapsed_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            error=error,
        )
    except Exception:
        logger.warning("tracer.end_span 失败 node=%s", node, exc_info=True)


def _dsa_query_plan_span_output(query_plan: QueryPlan) -> dict[str, Any]:
    """提取查询规划 span 的高价值观测字段。"""

    return {
        "query_type": query_plan.query_type,
        "execution_strategy": query_plan.execution_strategy,
        "confidence": query_plan.confidence,
        "planner_source": query_plan.planner_source,
        "fallback_reason": query_plan.fallback_reason,
        "validation_error": (query_plan.debug or {}).get("validation_error"),
        "selected_asset_count": len(query_plan.selected_assets),
        "reference_asset_count": len(query_plan.reference_assets),
        "rejected_asset_count": len(query_plan.rejected_assets),
        "required_input_count": len(query_plan.required_inputs),
        "decision_factors": query_plan.decision_factors,
        "planner_warnings": query_plan.planner_warnings,
        "governance_suggestions": query_plan.governance_suggestions,
    }


def _dsa_manifest_guard_summary(manifest_guard: dict[str, Any] | None) -> dict[str, Any]:
    guard = manifest_guard or {}
    permission_scope = guard.get("permission_scope") or {}
    quality_status = guard.get("quality_status") or {}
    return {
        "manifest_guard_status": guard.get("status"),
        "block_reason": guard.get("block_reason"),
        "manifest_version": guard.get("manifest_version"),
        "bound_schema_version": guard.get("bound_schema_version"),
        "latest_schema_version": guard.get("latest_schema_version"),
        "schema_hash": guard.get("schema_hash"),
        "review_status": guard.get("review_status"),
        "permission_scope_status": permission_scope.get("status"),
        "quality_status": quality_status.get("status"),
    }


# ============================================================
# 模块级私有辅助：analysis_blueprint 相关（Phase 5 迁入）
# ============================================================


def _format_blueprint_list(items: Any, *, key: str = "") -> list[str]:
    """将蓝图 JSON 列表字段转换为适合提示词消费的短文本。"""
    if not isinstance(items, list):
        return []
    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, str) and item.strip():
            lines.append(f"{idx}. {item.strip()}")
            continue
        if not isinstance(item, dict):
            continue
        if key and item.get(key):
            title = str(item.get(key)).strip()
        else:
            title = str(item.get("name") or item.get("column") or f"第{idx}项").strip()
        details = []
        for field in (
            "type",
            "semantic",
            "role",
            "purpose",
            "extract_hint",
            "default_expr",
            "required",
            "key_rules",
        ):
            value = item.get(field)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            details.append(f"{field}={value}")
        suffix = f"；{'; '.join(details)}" if details else ""
        lines.append(f"{idx}. {title}{suffix}")
    return lines


def _format_blueprint_semantic_context(bp: AnalysisBlueprint) -> str:
    """把手动创建的语义计划蓝图转成 QueryGraph 可使用的业务约束。"""
    lines = [
        "【命中的分析蓝图语义计划】",
        f"蓝图名称: {bp.name}",
        "执行方式: semantic_plan，不能要求用户提供 SQL；请基于数据集语义层和所选表结构生成查询。",
    ]
    if bp.when_to_use:
        lines.append(f"适用场景: {bp.when_to_use}")
    if bp.description:
        lines.append(f"业务描述: {bp.description}")
    # trigger_keywords / trigger_examples / attribution_hints 属路由阶段数据，SQL 生成不需要
    parameter_lines = _format_blueprint_list(bp.parameters, key="name")
    if parameter_lines:
        lines.append("需要从用户问题中理解的业务参数:")
        lines.extend(parameter_lines)
    output_lines = _format_blueprint_list(bp.output_schema, key="column")
    if output_lines:
        lines.append("期望输出列或结果口径:")
        lines.extend(output_lines)
    step_lines = _format_blueprint_list(bp.steps, key="name")
    if step_lines:
        lines.append("业务分析步骤:")
        lines.extend(step_lines)
    lines.append("硬性要求: 不要向用户索要 SQL；不要把参数占位符当成输出内容；优先按蓝图业务步骤组织查询。")
    return "\n".join(lines)


# ============================================================
# 模块级私有辅助：term 归一化（Phase 6 迁入）
#   原位于 app/graph/nodes.py；语义资产解析也是 dataset 业务工具，迁到门面。
#   graph 层 term_normalize_node 暂时保留调用（T4 Agent 后续删除节点）。
# ============================================================


def _dsa_coerce_text_list(value: Any) -> list[str]:
    """把 JSON / 字符串 / 列表里的别名清洗成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        raw_items = list(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                raw_items = parsed if isinstance(parsed, list) else [stripped]
            except (ValueError, TypeError):
                raw_items = [item.strip() for item in re.split(r"[,，、;/；\n]+", stripped) if item.strip()]
        else:
            raw_items = [item.strip() for item in re.split(r"[,，、;/；\n]+", stripped) if item.strip()]
    else:
        raw_items = [str(value)]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _dsa_semantic_match_text(text: Any) -> str:
    """统一语义资产匹配用文本，忽略大小写、空白、下划线和常见引用符。"""
    if text is None:
        return ""
    return re.sub(r"[\s_`'\".]+", "", str(text).strip().lower())


def _dsa_dedupe_texts(values: list[Any]) -> list[str]:
    """按语义匹配规则去重，保留原始展示文本。"""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        norm = _dsa_semantic_match_text(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(text)
    return out


def _dsa_term_match_candidates(term: dict) -> list[tuple[str, str]]:
    """返回业务术语可匹配词，包含标准名、展示名和同义词。"""
    candidates: list[tuple[str, str]] = []
    if term.get("name"):
        candidates.append((str(term["name"]), "exact"))
    if term.get("display_name") and term.get("display_name") != term.get("name"):
        candidates.append((str(term["display_name"]), "display_name"))
    for alias in _dsa_coerce_text_list(term.get("aliases")):
        candidates.append((alias, "synonym"))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token, match_type in candidates:
        norm = _dsa_semantic_match_text(token)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append((token, match_type))
    return deduped


def _dsa_match_term_in_question(term: dict, question: str) -> dict | None:
    """在用户问题中匹配一个业务术语。"""
    q_norm = _dsa_semantic_match_text(question)
    if not q_norm:
        return None

    best: dict | None = None
    for token, match_type in _dsa_term_match_candidates(term):
        token_norm = _dsa_semantic_match_text(token)
        if not token_norm:
            continue
        confidence = 0.0
        if token_norm == q_norm:
            confidence = {"exact": 0.97, "display_name": 0.95, "synonym": 0.9}.get(
                match_type, 0.88
            )
        elif len(token_norm) >= 2 and token_norm in q_norm:
            confidence = {"exact": 0.9, "display_name": 0.88, "synonym": 0.84}.get(
                match_type, 0.8
            )
        if confidence <= 0:
            continue
        candidate = {
            "term_id": term.get("id"),
            "name": term.get("name"),
            "display_name": term.get("display_name") or term.get("name"),
            "term_type": term.get("term_type"),
            "definition": term.get("definition"),
            "matched_text": token,
            "match_type": match_type,
            "confidence": round(confidence, 2),
            "aliases": term.get("aliases") or [],
            "asset_links": term.get("asset_links") or [],
        }
        if best is None or candidate["confidence"] > best["confidence"]:
            best = candidate
    return best


def _dsa_build_term_conflicts(matches: list[dict]) -> list[dict]:
    """识别本次问题命中的术语冲突。"""
    by_token: dict[str, list[dict]] = {}
    for match in matches:
        token = _dsa_semantic_match_text(match.get("matched_text"))
        if not token:
            continue
        by_token.setdefault(token, []).append(match)

    conflicts: list[dict] = []
    for token, owners in by_token.items():
        unique_ids = {m.get("term_id") for m in owners}
        if len(unique_ids) <= 1:
            continue
        conflicts.append(
            {
                "type": "alias_collision",
                "token": owners[0].get("matched_text") or token,
                "term_ids": sorted(i for i in unique_ids if i is not None),
                "terms": [
                    {
                        "id": m.get("term_id"),
                        "name": m.get("name"),
                        "display_name": m.get("display_name"),
                        "definition": m.get("definition"),
                    }
                    for m in owners
                ],
                "severity": "warning",
                "message": "同一个名称或同义词命中了多个业务术语",
            }
        )
    return conflicts


def _dsa_clarification_candidates_from_conflicts(conflicts: list[dict]) -> list[dict]:
    """将术语冲突压平成前端可展示、后端可解析的候选列表。"""
    candidates: list[dict] = []
    seen: set[int] = set()
    for conflict in conflicts or []:
        token = conflict.get("token")
        for term in conflict.get("terms") or []:
            term_id = term.get("id") or term.get("term_id")
            if term_id is None or term_id in seen:
                continue
            seen.add(term_id)
            candidates.append(
                {
                    "index": len(candidates) + 1,
                    "term_id": term_id,
                    "name": term.get("name"),
                    "display_name": term.get("display_name") or term.get("name"),
                    "definition": term.get("definition"),
                    "term_type": term.get("term_type"),
                    "aliases": _dsa_coerce_text_list(term.get("aliases")),
                    "matched_text": token,
                }
            )
    return candidates


# ============================================================
# 模块级私有辅助：semantic asset resolution（Phase 7 迁入）
# ============================================================


# 语义资产大类 → schema_structured 桶名映射（与原 nodes.py 一致）
_DSA_SEMANTIC_ASSET_BUCKETS: dict[str, str] = {
    "term": "terms",
    "metric": "metrics",
    "dimension": "dimensions",
    "field": "fields",
    "blueprint": "blueprints",
}

# 资产类型问题语气偏置（与原 nodes.py 一致，独立维护避免依赖 graph 模块）
_DSA_METRIC_PATTERNS = (
    "多少",
    "统计",
    "汇总",
    "合计",
    "总数",
    "趋势",
    "同比",
    "环比",
    "排名",
    "top",
    "平均",
    "占比",
    "gmv",
    "订单数",
    "销售额",
    "收入",
    "利润",
    "成本",
)
_DSA_DETAIL_PATTERNS = (
    "明细",
    "列表",
    "记录",
    "清单",
    "详情",
    "逐条",
    "每一条",
    "有哪些",
    "所有",
)
_DSA_KNOWLEDGE_PATTERNS = (
    "是什么",
    "什么意思",
    "定义",
    "解释",
    "口径",
    "怎么算",
    "如何计算",
    "规则",
    "知识库",
)
_DSA_BLUEPRINT_PATTERNS = (
    "分析",
    "归因",
    "诊断",
    "日报",
    "周报",
    "月报",
    "报表",
    "报告",
    "拆解",
    "复盘",
)


def _dsa_normalized_text(text: str) -> str:
    """归一化问题文本，便于做确定性入口路由匹配。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _dsa_field_aliases(field: dict) -> list[str]:
    """字段资产可匹配名称，排除样例值，避免把查询参数值误当资产名。"""
    column_name = field.get("column_name") or field.get("name")
    short_column = str(column_name).split(".")[-1] if column_name else None
    return _dsa_dedupe_texts(
        [
            column_name,
            short_column,
            field.get("display_name"),
            field.get("column_comment"),
            field.get("business_desc"),
            field.get("effective_desc"),
            field.get("user_description"),
            field.get("ai_description"),
            *_dsa_coerce_text_list(field.get("synonyms")),
        ]
    )


def _dsa_asset_identity(asset: dict) -> str:
    """生成资产去重键；字段可能没有跨环境稳定 ID，退回 name。"""
    return f"{asset.get('asset_type')}:{asset.get('asset_id') or asset.get('name')}"


def _dsa_context_bias(question: str, asset_type: str) -> float:
    """根据问题语气给资产类型加轻量偏置，避免同名资产时选错大类。"""
    q_norm = _dsa_normalized_text(question)
    if asset_type == "metric" and any(p in q_norm for p in _DSA_METRIC_PATTERNS):
        return 0.06
    if asset_type in ("dimension", "field") and any(p in q_norm for p in _DSA_DETAIL_PATTERNS):
        return 0.05
    if asset_type == "term" and any(p in q_norm for p in _DSA_KNOWLEDGE_PATTERNS):
        return 0.08
    if asset_type == "blueprint" and any(p in q_norm for p in _DSA_BLUEPRINT_PATTERNS):
        return 0.08
    return 0.0


def _dsa_asset_aliases(asset_type: str, item: dict) -> list[tuple[str, str]]:
    """返回 (alias, match_type) 列表，match_type 供前端和审计解释来源。"""
    aliases: list[tuple[str, str]] = []
    if item.get("name"):
        aliases.append((str(item["name"]), "exact"))
    if item.get("display_name") and item.get("display_name") != item.get("name"):
        aliases.append((str(item["display_name"]), "display_name"))

    if asset_type == "field":
        for alias in _dsa_field_aliases(item):
            match_type = "column_label" if alias != item.get("column_name") else "exact"
            aliases.append((alias, match_type))
    elif asset_type == "blueprint":
        for keyword in _dsa_coerce_text_list(item.get("trigger_keywords")):
            aliases.append((keyword, "trigger_keyword"))
        for example in _dsa_coerce_text_list(item.get("trigger_examples")):
            aliases.append((example, "trigger_example"))
    else:
        for synonym in _dsa_coerce_text_list(item.get("synonyms")):
            aliases.append((synonym, "synonym"))
        for alias in _dsa_coerce_text_list(item.get("aliases")):
            aliases.append((alias, "synonym"))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alias, match_type in aliases:
        norm = _dsa_semantic_match_text(alias)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append((alias, match_type))
    return deduped


def _dsa_build_semantic_asset_catalog(structured: dict | None) -> list[dict]:
    """从 schema_structured 构建统一资产列表。"""
    if not structured:
        return []
    catalog: list[dict] = []
    for asset_type, bucket in _DSA_SEMANTIC_ASSET_BUCKETS.items():
        for item in structured.get(bucket) or []:
            name = item.get("name") or item.get("column_name")
            if not name:
                continue
            display_name = item.get("display_name") or name
            catalog.append(
                {
                    "asset_type": asset_type,
                    "asset_id": item.get("id"),
                    "name": name,
                    "display_name": display_name,
                    "table_name": item.get("table_name"),
                    "column_name": item.get("column_name"),
                    "term_type": item.get("term_type"),
                    "implementation_type": item.get("implementation_type"),
                    "asset_links": item.get("asset_links") or [],
                    "_item": item,
                    "_aliases": _dsa_asset_aliases(asset_type, item),
                }
            )
    return catalog


def _dsa_candidate_from_match(
    asset: dict,
    *,
    query_text: str,
    matched_text: str,
    match_type: str,
    confidence: float,
) -> dict:
    """把一次命中转成可序列化候选，去掉内部字段。"""
    return {
        "asset_type": asset["asset_type"],
        "asset_id": asset.get("asset_id"),
        "name": asset.get("name"),
        "display_name": asset.get("display_name"),
        "table_name": asset.get("table_name"),
        "column_name": asset.get("column_name"),
        "term_type": asset.get("term_type"),
        "implementation_type": asset.get("implementation_type"),
        "matched_text": matched_text,
        "query_text": query_text,
        "match_type": match_type,
        "confidence": round(min(confidence, 0.99), 2),
    }


def _dsa_match_semantic_asset(
    asset: dict, query_text: str, question: str, preferred_type: str | None = None
) -> dict | None:
    """计算单个查询词与资产的最佳命中。"""
    query_norm = _dsa_semantic_match_text(query_text)
    question_norm = _dsa_semantic_match_text(question)
    if not query_norm:
        return None

    best: dict | None = None
    for alias, match_type in asset.get("_aliases") or []:
        alias_norm = _dsa_semantic_match_text(alias)
        if not alias_norm:
            continue

        confidence = 0.0
        if query_norm == alias_norm:
            confidence = {
                "exact": 0.96,
                "display_name": 0.94,
                "synonym": 0.88,
                "column_label": 0.86,
                "trigger_keyword": 0.86,
                "trigger_example": 0.78,
            }.get(match_type, 0.82)
        elif len(alias_norm) >= 2 and alias_norm in query_norm:
            confidence = 0.78
        elif len(query_norm) >= 2 and query_norm in alias_norm:
            confidence = 0.72
        elif query_text == question and len(alias_norm) >= 2 and alias_norm in question_norm:
            confidence = 0.74

        if confidence <= 0:
            continue
        confidence += _dsa_context_bias(question, asset["asset_type"])
        if preferred_type == asset["asset_type"]:
            confidence += 0.04
        candidate = _dsa_candidate_from_match(
            asset,
            query_text=query_text,
            matched_text=alias,
            match_type=match_type,
            confidence=confidence,
        )
        if best is None or candidate["confidence"] > best["confidence"]:
            best = candidate
    return best


def _dsa_linked_asset_candidates(term_candidate: dict, catalog: list[dict]) -> list[dict]:
    """术语命中后，把术语显式关联的语义资产也加入候选。"""
    term_asset = next(
        (
            asset
            for asset in catalog
            if asset["asset_type"] == "term" and asset.get("asset_id") == term_candidate.get("asset_id")
        ),
        None,
    )
    if not term_asset:
        return []

    by_identity = {_dsa_asset_identity(asset): asset for asset in catalog}
    out: list[dict] = []
    for link in term_asset.get("asset_links") or []:
        key = f"{link.get('asset_type')}:{link.get('asset_id')}"
        asset = by_identity.get(key)
        if not asset:
            continue
        out.append(
            _dsa_candidate_from_match(
                asset,
                query_text=term_candidate["query_text"],
                matched_text=term_candidate["matched_text"],
                match_type="linked_term",
                confidence=max(term_candidate["confidence"] - 0.08, 0.5),
            )
        )
    return out


def _dsa_entity_query_terms(entities: dict, question: str) -> list[dict]:
    """把上游实体和原问题整理成待解析词。"""
    terms: list[dict] = []
    for entity in entities.get("terms") or []:
        if entity:
            terms.append({"text": str(entity), "preferred_type": "term"})
    for entity in entities.get("metrics") or []:
        if entity:
            terms.append({"text": str(entity), "preferred_type": "metric"})
    for entity in entities.get("dimensions") or []:
        if entity:
            terms.append({"text": str(entity), "preferred_type": "dimension"})

    filters = entities.get("filters")
    if isinstance(filters, list):
        for item in filters:
            if isinstance(item, dict) and item.get("field"):
                terms.append({"text": str(item["field"]), "preferred_type": "field"})

    if question:
        terms.append({"text": question, "preferred_type": None})

    deduped: list[dict] = []
    seen: set[tuple[str, str | None]] = set()
    for term in terms:
        norm = _dsa_semantic_match_text(term["text"])
        key = (norm, term.get("preferred_type"))
        if not norm or key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def _dsa_to_compat_metric_resolution(
    semantic_resolution: dict, entities: dict, structured: dict | None
) -> dict:
    """把统一资产解析降级成旧 metric_resolution 输出，供旧节点和前端兼容。"""
    by_type = {
        bucket: {str(item.get("name")): item for item in (structured or {}).get(bucket) or []}
        for bucket in ("metrics", "dimensions")
    }

    def _resolve_entity(entity: str, asset_type: str) -> dict:
        bucket = "metrics" if asset_type == "metric" else "dimensions"
        candidates = [
            c
            for c in semantic_resolution.get(bucket, [])
            if c.get("query_text") == entity or c.get("matched_text") == entity
        ]
        if not candidates:
            # 原问题全文命中的候选也可作为兼容解析结果。
            candidates = semantic_resolution.get(bucket, [])
        if not candidates:
            return {
                "entity": entity,
                "resolved": None,
                "status": "unresolved",
                "match_type": None,
                "asset_type": asset_type,
                "asset_id": None,
                "confidence": 0.0,
            }
        best = max(candidates, key=lambda c: c.get("confidence", 0))
        resolved = best.get("name")
        known = by_type.get(bucket, {}).get(str(resolved))
        return {
            "entity": entity,
            "resolved": resolved,
            "status": "matched" if known or resolved else "unresolved",
            "match_type": best.get("match_type"),
            "asset_type": asset_type,
            "asset_id": best.get("asset_id"),
            "confidence": best.get("confidence"),
        }

    resolved_metrics = [
        _resolve_entity(str(entity), "metric") for entity in (entities.get("metrics") or []) if entity
    ]
    resolved_dimensions = [
        _resolve_entity(str(entity), "dimension")
        for entity in (entities.get("dimensions") or [])
        if entity
    ]

    all_matched = all(r["status"] == "matched" for r in resolved_metrics)
    unresolved = [r["entity"] for r in resolved_metrics if r["status"] == "unresolved"]
    return {
        "metrics": resolved_metrics,
        "dimensions": resolved_dimensions,
        "all_matched": all_matched,
        "unresolved": unresolved,
    }


def _dsa_public_candidate_assets(candidate_assets: dict[str, Any]) -> dict[str, Any]:
    """对外暴露候选资产召回结构时移除内部 QueryGraph 上下文。"""
    return {
        key: value
        for key, value in (candidate_assets or {}).items()
        if key != "context"
    }


def _dsa_int_or_none(value: Any) -> int | None:
    if value in (None, "", [], {}):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dsa_plan_blueprint_id(query_plan: QueryPlan) -> Any:
    for assets in (query_plan.selected_assets, query_plan.reference_assets):
        for asset in assets:
            if asset.asset_type == "blueprint":
                return asset.asset_id
    return None


_DSA_STATE_OUTPUT_KEYS = {
    "conversation_id",
    "original_question",
    "resolved_question",
    "manifest_version",
    "bound_schema_version",
    "time_context",
    "thread_context",
    "route_decision",
    "schema_status",
    "lead_agent_context",
    "skip_subagent_report",
    "report_owner",
    "subagent_report_skipped",
    "lead_agent_report",
    "intent",
    "entities",
    "entry_intent",
    "entry_route",
    "entry_reason",
    "blueprint_id",
    "blueprint_match",
    "blueprint_context",
    "knowledge_term_id",
    "route_payload",
    "clarification_response",
    "clarification_resolution_result",
    "prior_capsule",
    "prior_capsule_status",
    "out_capsule",
    "multiturn_context",
    "turn_type",
    "merge_debug",
    "selected_term_id",
    "schema_context",
    "schema_structured",
    "ddl_context",
    "query_constraints",
    "dataset_context_debug",
    "datasource_context",
    "term_normalization",
    "semantic_asset_resolution",
    "metric_resolution",
    "candidate_assets",
    "query_plan",
    "query_plan_debug",
    "query_plan_compilation",
    "control_plane",
    "query_artifact",
    "dataset_prompt_instructions",
    "dsl",
    "dsl_valid",
    "sql",
    "sql_result",
    "datasource_dialect",
    "sql_audit_result",
    "sql_diagnosis",
    "sql_retry_trace",
    "answer",
    "answer_explanation",
    "sql_list",
    "error",
    "generation_mode",
    "execution_source",
    "should_retry",
    "token_usage",
}


def _dsa_is_state_output(value: dict[str, Any]) -> bool:
    """判断字典是否像 QueryGraph 节点输出片段。"""
    return bool(_DSA_STATE_OUTPUT_KEYS.intersection(value.keys()))


def _dsa_find_state_output(value: object, lg_node: str = "", depth: int = 0) -> dict[str, Any]:
    """递归查找 LangGraph/LCEL 事件里的真实 state 输出。"""
    if depth > 5 or not isinstance(value, dict):
        return {}

    if lg_node and isinstance(value.get(lg_node), dict):
        nested = _dsa_find_state_output(value[lg_node], lg_node, depth + 1)
        return nested or value[lg_node]

    if _dsa_is_state_output(value):
        return value

    for key in ("output", "__end__", "state", "result"):
        nested = _dsa_find_state_output(value.get(key), lg_node, depth + 1)
        if nested:
            return nested

    if len(value) == 1:
        nested = _dsa_find_state_output(next(iter(value.values())), lg_node, depth + 1)
        if nested:
            return nested

    return {}


def _dsa_extract_graph_event_output(event: dict[str, Any]) -> dict[str, Any]:
    """从 runner 事件中解出可合并的 QueryGraph state 片段。"""
    metadata = event.get("metadata") or {}
    lg_node = metadata.get("langgraph_node") or ""
    output = (event.get("data") or {}).get("output") or {}
    return _dsa_find_state_output(output, lg_node)


def _dsa_build_run_routing(
    state: dict[str, Any],
    request: DatasetSubAgentRequest,
) -> dict[str, Any]:
    """整理 LeadAgent 路由决策和 Graph initial_state，供查询规划器消费。"""
    route_decision = dict(request.route_decision or {})
    routing = {
        **route_decision,
        "dataset_id": request.dataset_id,
        "entry_route": state.get("entry_route") or route_decision.get("entry_route") or route_decision.get("decision"),
        "entry_intent": state.get("entry_intent") or route_decision.get("entry_intent") or state.get("intent"),
        "entry_reason": state.get("entry_reason") or route_decision.get("reason"),
        "blueprint_id": state.get("blueprint_id") or route_decision.get("blueprint_id"),
        "blueprint_match": state.get("blueprint_match") or route_decision.get("blueprint_match"),
        "entities": state.get("entities") or route_decision.get("entities") or {},
        "route_payload": state.get("route_payload") or route_decision.get("route_payload") or {},
        "original_question": state.get("original_question"),
        "resolved_question": state.get("resolved_question"),
        "time_context": state.get("time_context") or request.time_context,
    }
    return {key: value for key, value in routing.items() if value not in (None, "", [], {})}


def _dsa_request_task_capsule(request: DatasetSubAgentRequest) -> dict[str, Any] | None:
    capsule = request.query_task_capsule
    return capsule if isinstance(capsule, dict) else None


def _dsa_request_turn_event(
    request: DatasetSubAgentRequest,
    capsule: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(request.turn_event, dict):
        return request.turn_event
    turn_event = (capsule or {}).get("turn_event") if isinstance(capsule, dict) else None
    return turn_event if isinstance(turn_event, dict) else None


def _dsa_state_task_capsule(state: dict[str, Any]) -> dict[str, Any] | None:
    capsule = state.get("query_task_capsule")
    return capsule if isinstance(capsule, dict) else None


def _dsa_task_capsule_standalone_question(capsule: dict[str, Any] | None) -> str | None:
    standalone_question = (capsule or {}).get("standalone_question") if isinstance(capsule, dict) else None
    if standalone_question is None:
        return None
    text = str(standalone_question).strip()
    return text or None


def _dsa_task_capsule_base_question(capsule: dict[str, Any] | None) -> str | None:
    if not isinstance(capsule, dict):
        return None
    for key in ("base_question", "original_question"):
        value = capsule.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _dsa_prepare_task_capsule_state(
    state: dict[str, Any],
    request: DatasetSubAgentRequest,
) -> tuple[dict[str, Any], str]:
    """把 request 级 QueryTaskCapsule 补齐到 SubAgent state，供直调路径消费。"""

    current_question = state.get("question")
    request_capsule = _dsa_request_task_capsule(request)
    state_capsule = _dsa_state_task_capsule(state)
    capsule = state_capsule or request_capsule
    if capsule is not None and state_capsule is None:
        state["query_task_capsule"] = capsule

    if state.get("turn_event") is None:
        turn_event = _dsa_request_turn_event(request, capsule)
        if turn_event is not None:
            state["turn_event"] = turn_event

    if state.get("original_question") in (None, ""):
        original_question = current_question or request.question
        if original_question:
            state["original_question"] = original_question

    standalone_question = _dsa_task_capsule_standalone_question(capsule)
    if standalone_question:
        state["question"] = standalone_question
    elif not state.get("question"):
        state["question"] = request.question

    return state, str(state.get("question") or request.question)


def _dsa_clean_blueprint_input_params(value: Any) -> dict[str, Any]:
    """提取可安全传给蓝图执行器的简单参数值。"""
    if not isinstance(value, dict):
        return {}

    params: dict[str, Any] = {}
    for key, param_value in value.items():
        if not isinstance(key, str) or not key:
            continue
        if param_value in (None, "", [], {}):
            continue
        if isinstance(param_value, str | int | float | bool):
            params[key] = param_value
    return params


def _dsa_route_payload_blueprint_input_params(route_payload: Any) -> dict[str, Any]:
    """从 route_payload 中提取规划层已确认的蓝图参数。"""
    if not isinstance(route_payload, dict):
        return {}

    params: dict[str, Any] = {}
    for field in ("params", "input_params", "parameters"):
        params.update(_dsa_clean_blueprint_input_params(route_payload.get(field)))
    return params


def _dsa_build_blueprint_execute_input_params(routing: dict[str, Any]) -> dict[str, Any]:
    """合并蓝图执行参数：routing.entities 优先于 route_payload，time_context 在解析层兜底。"""
    params = _dsa_route_payload_blueprint_input_params(routing.get("route_payload"))
    params.update(_dsa_clean_blueprint_input_params(routing.get("entities")))
    return params


def _dsa_append_text(existing: Any, addition: str) -> str:
    existing_text = str(existing or "").strip()
    addition_text = str(addition or "").strip()
    if not existing_text:
        return addition_text
    if not addition_text:
        return existing_text
    return f"{existing_text}\n\n{addition_text}"


def _dsa_build_query_graph_state(
    *,
    state: dict[str, Any],
    request: DatasetSubAgentRequest,
    question: str,
    routing: dict[str, Any],
    candidate_assets: dict[str, Any],
    public_candidate_assets: dict[str, Any],
    query_plan: QueryPlan,
    sql_generation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把候选资产上下文与查询计划注入 QueryGraph 初始状态。"""
    context = candidate_assets.get("context") if isinstance(candidate_assets, dict) else {}
    context = context if isinstance(context, dict) else {}
    datasource_context = context.get("datasource_context") or {}
    task_capsule = _dsa_state_task_capsule(state) or _dsa_request_task_capsule(request)
    turn_event = state.get("turn_event")
    if turn_event is None:
        turn_event = _dsa_request_turn_event(request, task_capsule)
    query_graph_state = dict(state)
    query_graph_state.update(
        {
            "question": question,
            "original_question": state.get("original_question")
            or request.question,
            "query_task_capsule": task_capsule,
            "turn_event": turn_event,
            "dataset_id": request.dataset_id,
            "manifest_version": request.manifest_version,
            "bound_schema_version": request.bound_schema_version,
            "time_context": state.get("time_context") or request.time_context,
            "thread_context": state.get("thread_context") or request.thread_context,
            "route_decision": state.get("route_decision") or request.route_decision,
            "schema_status": state.get("schema_status") or request.schema_status,
            "lead_agent_context": state.get("lead_agent_context") or request.lead_agent_context,
            "entry_route": "query_graph",
            "entry_intent": routing.get("entry_intent") or query_plan.query_type,
            "entry_reason": routing.get("entry_reason") or query_plan.fallback_reason,
            "entities": routing.get("entities") or state.get("entities") or {},
            "schema_context": context.get("schema_context"),
            "schema_structured": context.get("schema_structured"),
            "ddl_context": context.get("ddl_context"),
            "query_constraints": context.get("query_constraints"),
            "dataset_context_debug": context.get("dataset_context_debug"),
            "datasource_context": datasource_context,
            "dataset_prompt_instructions": context.get("dataset_prompt_instructions"),
            "candidate_assets": public_candidate_assets,
            "query_plan": query_plan.to_dict(),
            "query_plan_debug": {
                "execution_strategy": query_plan.execution_strategy,
                "planner_source": query_plan.planner_source,
                "confidence": query_plan.confidence,
                "fallback_reason": query_plan.fallback_reason,
                "explanation": query_plan.explanation,
                "decision_factors": query_plan.decision_factors,
                "planner_warnings": query_plan.planner_warnings,
                "governance_suggestions": query_plan.governance_suggestions,
                "debug": query_plan.debug,
            },
        }
    )
    if sql_generation_context is not None:
        query_graph_state["sql_generation_context"] = sql_generation_context
    compiler_context = build_query_plan_compiler_context(sql_generation_context)
    query_plan_compilation = compile_query_plan_to_sql(
        query_plan=query_plan,
        sql_generation_context=compiler_context,
        dialect=datasource_context.get("dialect") or datasource_context.get("db_type"),
        query_constraints=context.get("query_constraints"),
        allowed_tables=datasource_context.get("allowed_tables") or [],
    )
    query_graph_state["query_plan_compilation"] = query_plan_compilation
    query_graph_state["query_plan_debug"]["query_plan_compilation"] = query_plan_compilation.get("trace")
    if query_plan_compilation.get("ok"):
        # 编译 SQL 只写入控制面 / 查询产物 / trace 形态，避免回流到 planner prompt。
        query_graph_state["control_plane"] = {
            **(query_graph_state.get("control_plane") or {}),
            "query_plan_compilation": query_plan_compilation["control_plane"],
        }
        query_graph_state["query_artifact"] = query_plan_compilation["query_artifact"]
    if query_plan.execution_strategy == "blueprint_as_reference":
        reference_context = build_blueprint_reference_context(query_plan)
        query_graph_state["blueprint_context"] = _dsa_append_text(
            query_graph_state.get("blueprint_context"),
            reference_context,
        )
        query_graph_state["dataset_prompt_instructions"] = _dsa_append_text(
            query_graph_state.get("dataset_prompt_instructions"),
            reference_context,
        )
    return query_graph_state


# ============================================================
# DatasetSubAgent 门面
# ============================================================


@dataclass
class DatasetSubAgent:
    """单 dataset subAgent 门面：持有资产 + 对外暴露可编排能力。

    Phase 5 起，LeadAgent（chat 层）通过本对象调 blueprint 能力，
    不再直接 import services/analysis_blueprint.py。Graph 层不感知本对象存在。

    资产访问通过 db session；本类不持有缓存，所有读写都走 DB。
    """

    db: Session
    dataset_id: int

    async def run(
        self,
        request: DatasetSubAgentRequest,
        trace_context: Any | None,
        *,
        graph: Any,
        initial_state: dict[str, Any] | None = None,
        graph_kwargs: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SubAgentEvent, None]:
        """统一编排单数据集 SubAgent：资产召回、查询规划和策略执行。"""
        state, question = _dsa_prepare_task_capsule_state(dict(initial_state or {}), request)
        routing = _dsa_build_run_routing(state, request)
        multiturn_context = state.get("multiturn_context") or {}
        tracer = get_observability_tracer()
        manifest_guard = evaluate_manifest_runtime_guard(
            self.db,
            request.dataset_id,
            route_decision=request.route_decision,
            schema_status=request.schema_status,
        )
        state["manifest_guard"] = manifest_guard
        if manifest_guard.get("status") != "ok":
            final_state = {
                **state,
                "answer": "当前 Manifest 未通过执行前校验，本轮已阻断执行。",
                "error": manifest_guard.get("block_reason") or "manifest_blocked",
                "entry_route": "blocked",
                "entry_intent": "manifest_guard",
                "manifest_guard": manifest_guard,
                "route_decision": request.route_decision,
                "schema_status": request.schema_status,
                "should_retry": False,
            }
            yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
            return
        manifest_guard_summary = _dsa_manifest_guard_summary(manifest_guard)

        candidate_span_started_at = time.monotonic()
        try:
            tracer.start_span(
                trace_context,
                node="subagent.candidate_assets",
                display_name="subagent.candidate_assets",
                input_payload={
                    "dataset_id": request.dataset_id,
                    "question": question,
                    "manifest_version": request.manifest_version,
                    "bound_schema_version": request.bound_schema_version,
                    **manifest_guard_summary,
                },
                trace_tags=["subagent"],
            )
        except Exception:
            logger.warning("tracer.start_span 失败 node=subagent.candidate_assets", exc_info=True)
        try:
            candidate_assets = recall_candidate_assets(
                self.db,
                dataset_id=request.dataset_id,
                question=question,
                manifest_version=request.manifest_version,
                bound_schema_version=request.bound_schema_version,
            )
        except Exception as exc:
            _dsa_end_span(
                tracer,
                trace_context,
                node="subagent.candidate_assets",
                started_at=candidate_span_started_at,
                error=repr(exc),
            )
            raise
        public_candidate_assets = _dsa_public_candidate_assets(candidate_assets)
        _dsa_end_span(
            tracer,
            trace_context,
            node="subagent.candidate_assets",
            started_at=candidate_span_started_at,
            output_payload={
                "asset_count": len(public_candidate_assets.get("assets") or []),
                "summary": public_candidate_assets.get("summary") or {},
                "recall_debug": public_candidate_assets.get("recall_debug") or {},
            },
        )
        yield SubAgentEvent(
            event_type="candidate_assets",
            payload={
                "node": "candidate_assets",
                "display_name": "subagent.candidate_assets",
                "status": "done",
                "candidate_assets": public_candidate_assets,
            },
        )

        settings = get_settings()
        detail_loop_enabled = bool(settings.SUBAGENT_PLANNER_DETAIL_LOOP_ENABLED)
        detail_loop_result = None
        sql_generation_context: dict[str, Any] | None = None
        query_plan_span_started_at = time.monotonic()
        try:
            tracer.start_span(
                trace_context,
                node="subagent.query_plan",
                display_name="subagent.query_plan",
                input_payload={
                    "dataset_id": request.dataset_id,
                    "question": question,
                    "routing": {
                        "entry_route": routing.get("entry_route"),
                        "entry_intent": routing.get("entry_intent"),
                        "blueprint_id": routing.get("blueprint_id"),
                    },
                    **manifest_guard_summary,
                    "candidate_asset_count": len(public_candidate_assets.get("assets") or []),
                    "candidate_asset_summary": public_candidate_assets.get("summary") or {},
                },
                trace_tags=["subagent"],
            )
        except Exception:
            logger.warning("tracer.start_span 失败 node=subagent.query_plan", exc_info=True)
        try:
            if detail_loop_enabled:
                detail_service = AssetDetailService(
                    candidate_assets=candidate_assets,
                    full_field_limit=settings.SUBAGENT_PLANNER_TABLE_FULL_FIELD_LIMIT,
                    compact_field_limit=settings.SUBAGENT_PLANNER_TABLE_COMPACT_FIELD_LIMIT,
                    field_search_default_top_k=settings.SUBAGENT_PLANNER_FIELD_SEARCH_DEFAULT_TOP_K,
                    field_search_max_top_k=settings.SUBAGENT_PLANNER_FIELD_SEARCH_MAX_TOP_K,
                )
                detail_loop = PlannerDetailLoop(
                    max_rounds=settings.SUBAGENT_PLANNER_DETAIL_MAX_ROUNDS,
                    max_requests_per_round=settings.SUBAGENT_PLANNER_DETAIL_MAX_REQUESTS_PER_ROUND,
                    planner_call=plan_query_with_detail_context,
                    detail_service=detail_service,
                )
                detail_loop_result = detail_loop.run(
                    db=self.db,
                    question=question,
                    routing=routing,
                    candidate_assets=candidate_assets,
                    multiturn_context=multiturn_context,
                    lead_agent_context=request.lead_agent_context,
                )
                query_plan = detail_loop_result.query_plan
                sql_generation_context = detail_loop_result.sql_generation_context
            else:
                query_plan = plan_query(
                    db=self.db,
                    question=question,
                    routing=routing,
                    candidate_assets=public_candidate_assets,
                    multiturn_context=multiturn_context,
                    lead_agent_context=request.lead_agent_context,
                )
        except Exception as exc:
            _dsa_end_span(
                tracer,
                trace_context,
                node="subagent.query_plan",
                started_at=query_plan_span_started_at,
                error=repr(exc),
            )
            raise
        query_plan_payload = query_plan.to_dict()
        _dsa_end_span(
            tracer,
            trace_context,
            node="subagent.query_plan",
            started_at=query_plan_span_started_at,
            output_payload=_dsa_query_plan_span_output(query_plan),
        )
        if detail_loop_result is not None:
            yield SubAgentEvent(
                event_type="asset_detail",
                payload={
                    "node": "asset_detail",
                    "display_name": "subagent.asset_detail",
                    "status": "done",
                    "detail_rounds": detail_loop_result.detail_rounds,
                    "requested_count": len(detail_loop_result.attempted_detail_requests),
                    "coverage": query_plan.asset_detail_coverage
                    or (sql_generation_context or {}).get("coverage")
                    or {},
                    "risk_flags": query_plan.risk_flags,
                    "warnings": detail_loop_result.warnings,
                },
            )
        yield SubAgentEvent(
            event_type="query_plan",
            payload={
                "node": "query_plan",
                "display_name": "subagent.query_plan",
                "status": "done",
                "query_plan": query_plan_payload,
            },
        )

        strategy = query_plan.execution_strategy
        if strategy == "clarify":
            result = build_clarify_result(query_plan)
            final_state = dict(result.final_state)
            final_state["candidate_assets"] = public_candidate_assets
            if sql_generation_context is not None:
                final_state["sql_generation_context"] = sql_generation_context
            yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
            return

        if strategy == "reject":
            result = build_reject_result(query_plan)
            final_state = dict(result.final_state)
            final_state["candidate_assets"] = public_candidate_assets
            if sql_generation_context is not None:
                final_state["sql_generation_context"] = sql_generation_context
            yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
            return

        if strategy == "blueprint_execute":
            final_state = self._run_blueprint_execute(
                query_plan=query_plan,
                question=question,
                routing=routing,
                candidate_assets=public_candidate_assets,
                trace_context=trace_context,
            )
            if sql_generation_context is not None:
                final_state["sql_generation_context"] = sql_generation_context
            yield SubAgentEvent(event_type="result", payload={"final_state": final_state})
            return

        if graph is None:
            raise ValueError(
                f"DatasetSubAgent {strategy} strategy requires graph: dataset_id={request.dataset_id}"
            )

        query_graph_state = _dsa_build_query_graph_state(
            state=state,
            request=request,
            question=question,
            routing=routing,
            candidate_assets=candidate_assets,
            public_candidate_assets=public_candidate_assets,
            query_plan=query_plan,
            sql_generation_context=sql_generation_context,
        )
        final_state = dict(query_graph_state)
        runner = InProcessDatasetSubAgentRunner(graph, self.db)
        async for event in runner.run(
            request,
            trace_context,
            query_graph_state,
            **(graph_kwargs or {}),
        ):
            output = _dsa_extract_graph_event_output(event)
            if output:
                final_state.update(output)
            yield SubAgentEvent(event_type="graph_event", payload={"event": event})

        final_state["query_plan"] = query_plan_payload
        final_state["candidate_assets"] = public_candidate_assets
        yield SubAgentEvent(event_type="result", payload={"final_state": final_state})

    def _run_blueprint_execute(
        self,
        *,
        query_plan: QueryPlan,
        question: str,
        routing: dict[str, Any],
        candidate_assets: dict[str, Any],
        trace_context: Any | None,
    ) -> dict[str, Any]:
        """执行固定蓝图策略，并补齐 run 对外统一 final_state 字段。"""
        blueprint_id = _dsa_plan_blueprint_id(query_plan) or routing.get("blueprint_id")
        outcome = self.resolve_analysis_blueprint(
            blueprint_id=_dsa_int_or_none(blueprint_id),
            question=question,
            entry_route="analysis_blueprint",
            original_question=routing.get("original_question") or question,
            resolved_question=routing.get("resolved_question") or question,
            time_context=routing.get("time_context"),
            input_params=_dsa_build_blueprint_execute_input_params(routing),
            trace_context=trace_context,
        )
        return {
            "query_plan": query_plan.to_dict(),
            "candidate_assets": candidate_assets,
            "answer": outcome.get("answer"),
            "sql": outcome.get("sql"),
            "sql_list": outcome.get("sql_list") or [],
            "sql_result": outcome.get("sql_result"),
            "error": outcome.get("error"),
            "route_payload": outcome.get("route_payload") or {},
            "should_retry": outcome.get("should_retry", False),
            "entry_route": "analysis_blueprint",
            "entry_intent": "analysis_blueprint",
            "blueprint_id": outcome.get("blueprint_id") or _dsa_int_or_none(blueprint_id),
            "blueprint_name": outcome.get("blueprint_name"),
            "blueprint_context": outcome.get("blueprint_context"),
            "generation_mode": outcome.get("generation_mode"),
            "blueprint_outcome_status": outcome.get("status"),
            "execution_time_ms": outcome.get("execution_time_ms"),
        }

    # ──────────── Phase 5：分析蓝图解析 ────────────

    def resolve_analysis_blueprint(
        self,
        *,
        blueprint_id: int | None,
        question: str,
        entry_route: str | None = None,
        original_question: str | None = None,
        resolved_question: str | None = None,
        time_context: dict | None = None,
        input_params: dict[str, Any] | None = None,
        tracer: Any | None = None,
        trace_context: Any | None = None,
    ) -> dict[str, Any]:
        """5 分支 outcome（与原 analysis_blueprint_execute_node 节点 1:1 等价）。

        分支：
        - not_applicable：无 blueprint_id 或 entry_route != "analysis_blueprint"
        - not_found：blueprint_id 查无 / 跨 dataset
        - semantic_plan：manual 语义计划蓝图（不进 chat 早退，注入 initial_state 走 Graph）
        - executed：SQL 模板蓝图执行成功（chat 早退 + 报告生成）
        - clarification：缺参（chat 早退 + 让用户补参）
        - error：执行失败（chat 早退 + error answer）

        返回 dict 13 字段（与原节点同构，便于等价性 fixture 冻结）。
        """
        span = None
        if tracer is not None and trace_context is not None:
            try:
                span = tracer.start_span(
                    trace_context,
                    node="analysis_blueprint_resolve",
                    display_name="analysis_blueprint_resolve",
                    input_payload={"blueprint_id": blueprint_id, "question": question},
                )
            except Exception:  # 兜底：tracer 不可用时不影响主流程
                span = None
                logger.warning("tracer.start_span 失败，跳过 span", exc_info=True)

        try:
            outcome = self._resolve_analysis_blueprint_impl(
                blueprint_id=blueprint_id,
                question=question,
                entry_route=entry_route,
                original_question=original_question,
                resolved_question=resolved_question,
                time_context=time_context,
                input_params=input_params,
            )
            if span is not None:
                try:
                    span.end_span(
                        output_payload={
                            "status": outcome["status"],
                            "blueprint_id": outcome.get("blueprint_id"),
                            "blueprint_name": outcome.get("blueprint_name"),
                            "generation_mode": outcome.get("generation_mode"),
                            "route_payload_kind": (outcome.get("route_payload") or {}).get("kind"),
                            "execution_time_ms": outcome.get("execution_time_ms"),
                            "missing": (outcome.get("route_payload") or {}).get("missing"),
                        },
                        error=outcome.get("error"),
                    )
                except Exception:
                    logger.warning("tracer.end_span 失败", exc_info=True)
            return outcome
        except Exception as exc:
            if span is not None:
                try:
                    span.end_span(error=repr(exc))
                except Exception:
                    pass
            raise

    def _resolve_analysis_blueprint_impl(
        self,
        *,
        blueprint_id: int | None,
        question: str,
        entry_route: str | None,
        original_question: str | None,
        resolved_question: str | None,
        time_context: dict | None,
        input_params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """resolve_analysis_blueprint 内部实现：5 分支决策 + 返回 13 字段 dict。"""
        # 分支 1：not_applicable —— 无 blueprint_id 或 entry_route 错
        if not blueprint_id or (entry_route is not None and entry_route != "analysis_blueprint"):
            logger.info(
                "分析蓝图不适用: blueprint_id=%s, entry_route=%s",
                blueprint_id,
                entry_route,
            )
            # 兼容旧节点行为：无 blueprint_id 时填 "未命中分析蓝图"；entry_route 错时填"不属于当前数据集"
            err_msg = "未命中分析蓝图，无法执行" if not blueprint_id else "分析蓝图不存在或不属于当前数据集"
            return jsonable_encoder({
                "status": "not_applicable",
                "blueprint_id": None,
                "blueprint_name": None,
                "sql_result": None,
                "sql": None,
                "sql_list": [],
                "generation_mode": None,
                "blueprint_context": None,
                "answer": None,
                "error": err_msg,
                "should_retry": False,
                "route_payload": {"kind": "not_applicable"},
            })

        # 分支 2：not_found —— blueprint_id 查无 / 跨 dataset
        bp = self.db.get(AnalysisBlueprint, blueprint_id)
        if not bp or (self.dataset_id and bp.dataset_id != self.dataset_id):
            logger.info(
                "分析蓝图未命中: blueprint_id=%s, dataset_id=%s, exists=%s",
                blueprint_id,
                self.dataset_id,
                bool(bp),
            )
            return jsonable_encoder({
                "status": "not_found",
                "blueprint_id": blueprint_id,
                "blueprint_name": None,
                "sql_result": None,
                "sql": None,
                "sql_list": [],
                "generation_mode": None,
                "blueprint_context": None,
                "answer": None,
                "error": "分析蓝图不存在或不属于当前数据集",
                "should_retry": False,
                "route_payload": {
                    "kind": "not_found",
                    "blueprint_id": blueprint_id,
                },
            })

        logger.info("分析蓝图执行开始: blueprint_id=%s, dataset_id=%s", bp.id, self.dataset_id)

        # 分支 3：semantic_plan —— manual 语义计划
        implementation_type = (bp.implementation_type or "").strip()
        if implementation_type == "semantic_plan":
            blueprint_context = _format_blueprint_semantic_context(bp)
            logger.info(
                "分析蓝图为语义计划，转入 QueryGraph: blueprint_id=%s, context_len=%s",
                bp.id,
                len(blueprint_context),
            )
            return jsonable_encoder({
                "status": "semantic_plan",
                "blueprint_id": bp.id,
                "blueprint_name": bp.name,
                "sql_result": None,
                "sql": None,
                "sql_list": [],
                "generation_mode": "analysis_blueprint_semantic",
                "blueprint_context": blueprint_context,
                "answer": None,
                "error": None,
                "should_retry": False,
                "route_payload": {
                    "kind": "analysis_blueprint_semantic",
                    "blueprint_id": bp.id,
                    "name": bp.name,
                    "implementation_type": implementation_type,
                },
            })

        # 分支 4/5/6：execute_analysis_blueprint 返回结果分类
        result = execute_analysis_blueprint(
            self.db,
            bp,
            question=question,
            input_params={
                **blueprint_params_from_time_context(bp, time_context),
                **(input_params or {}),
            },
            require_active=True,
            count_usage=True,
        )
        if not result.get("ok"):
            missing = result.get("missing") or []
            answer = result.get("error") or "分析蓝图执行失败"
            display_sql = result.get("sql_preview") or result.get("sql")
            if missing:
                # 分支 4：clarification —— 缺参
                return jsonable_encoder({
                    "status": "clarification",
                    "blueprint_id": bp.id,
                    "blueprint_name": bp.name,
                    "sql_result": None,
                    "sql": display_sql,
                    "sql_list": [display_sql] if display_sql else [],
                    "generation_mode": None,
                    "blueprint_context": None,
                    "answer": answer,
                    "error": answer,
                    "should_retry": False,
                    "route_payload": {
                        "kind": "clarification",
                        "blueprint_id": bp.id,
                        "params": result.get("params") or {},
                        "sql_template": result.get("sql"),
                        "original_question": original_question or question,
                        "resolved_question": resolved_question or question,
                        "missing": missing,
                    },
                })
            # 分支 5：error —— 执行失败（非缺参）
            return jsonable_encoder({
                "status": "error",
                "blueprint_id": bp.id,
                "blueprint_name": bp.name,
                "sql_result": None,
                "sql": display_sql,
                "sql_list": [display_sql] if display_sql else [],
                "generation_mode": None,
                "blueprint_context": None,
                "answer": answer,
                "error": answer,
                "should_retry": False,
                "route_payload": {
                    "kind": "analysis_blueprint_error",
                    "blueprint_id": bp.id,
                    "params": result.get("params") or {},
                    "sql_template": result.get("sql"),
                    "original_question": original_question or question,
                    "resolved_question": resolved_question or question,
                },
            })

        # 分支 6：executed —— SQL 模板执行成功
        display_sql = result.get("sql_preview") or result["sql"]
        return jsonable_encoder({
            "status": "executed",
            "blueprint_id": bp.id,
            "blueprint_name": bp.name,
            "sql_result": result["sql_result"],
            "sql": display_sql,
            "sql_list": [display_sql],
            "generation_mode": "analysis_blueprint",
            "blueprint_context": None,
            "answer": None,
            "error": None,
            "should_retry": False,
            "route_payload": {
                "kind": "analysis_blueprint",
                "blueprint_id": bp.id,
                "name": bp.name,
                "params": result["params"],
                "sql_template": result["sql"],
                "original_question": original_question or question,
                "resolved_question": resolved_question or question,
                "execution_time_ms": result["execution_time_ms"],
            },
            "execution_time_ms": result["execution_time_ms"],
        })

    # ──────────── Phase 6：业务术语归一化 ────────────

    def resolve_term_conflict(
        self,
        *,
        question: str,
        terms: list[dict] | None = None,
        entities: dict | None = None,
        selected_term_id: int | None = None,
        tracer: Any | None = None,
        trace_context: Any | None = None,
    ) -> dict[str, Any]:
        """5 分支 outcome（与原 term_normalize_node 节点 1:1 等价）。

        分支：
        - not_applicable：无 term 候选，透明通过
        - resolved：单 term 命中，自动归一化（注入 entities.terms）
        - needs_clarification：多 term 冲突，让用户选（chat 早退）
        - missing_term：term 缺 id/name（错误早退）
        - error：异常降级

        输入参数：
        - terms：来自 schema_structured.terms 的候选列表（已结构化）
        - entities：来自上游 route_query_intent 的实体字典（会被原地更新 terms 字段）
        - selected_term_id：多轮澄清回复后用户选择的 term_id

        返回 dict（与原 term_normalize_node 同构 + Phase 6 新增）：
        - status / term_normalization：向后兼容原节点输出
        - selected_term_id / resolved_question / answer / error / should_retry
        - route_payload：含 kind, conflicts, candidates（needs_clarification 时）
        """
        span = None
        if tracer is not None and trace_context is not None:
            try:
                span = tracer.start_span(
                    trace_context,
                    node="term_conflict_resolve",
                    display_name="term_conflict_resolve",
                    input_payload={
                        "question": question,
                        "terms_count": len(terms or []),
                        "selected_term_id": selected_term_id,
                    },
                )
            except Exception:
                span = None
                logger.warning("tracer.start_span 失败，跳过 span", exc_info=True)

        try:
            outcome = self._resolve_term_conflict_impl(
                question=question,
                terms=terms,
                entities=entities,
                selected_term_id=selected_term_id,
            )
            if span is not None:
                try:
                    span.end_span(
                        output_payload={
                            "status": outcome["status"],
                            "selected_term_id": outcome.get("selected_term_id"),
                            "resolved_question": outcome.get("resolved_question"),
                            "match_count": len((outcome.get("term_normalization") or {}).get("matched_terms") or []),
                            "has_conflict": (outcome.get("term_normalization") or {}).get("has_conflict"),
                            "route_payload_kind": (outcome.get("route_payload") or {}).get("kind"),
                        },
                        error=outcome.get("error"),
                    )
                except Exception:
                    logger.warning("tracer.end_span 失败", exc_info=True)
            return outcome
        except Exception as exc:
            if span is not None:
                try:
                    span.end_span(error=repr(exc))
                except Exception:
                    pass
            # 分支 5：error —— 异常降级（与节点行为对齐，保留 question 透传）
            return jsonable_encoder({
                "status": "error",
                "term_normalization": {"matched_terms": [], "conflicts": [], "has_conflict": False},
                "selected_term_id": None,
                "resolved_question": None,
                "answer": None,
                "error": repr(exc),
                "should_retry": False,
                "route_payload": {"kind": "term_conflict_error"},
            })

    def _resolve_term_conflict_impl(
        self,
        *,
        question: str,
        terms: list[dict] | None,
        entities: dict | None,
        selected_term_id: int | None,
    ) -> dict[str, Any]:
        """resolve_term_conflict 内部实现：5 分支决策 + 返回 8 字段 dict。"""
        terms = terms or []
        logger.info("term_conflict 开始: terms=%s", len(terms))

        # 分支 1：missing_term —— term 配置缺 id/name（错误早退）
        invalid_terms = [
            t for t in terms
            if not (t.get("id") or t.get("term_id")) or not (t.get("name") or t.get("display_name"))
        ]
        if invalid_terms:
            logger.warning("term_conflict 候选缺字段: invalid=%s", len(invalid_terms))
            return jsonable_encoder({
                "status": "missing_term",
                "term_normalization": {"matched_terms": [], "conflicts": [], "has_conflict": False},
                "selected_term_id": None,
                "resolved_question": None,
                "answer": "业务术语配置缺失，请联系管理员补全术语字段。",
                "error": "term 配置缺 id 或 name",
                "should_retry": False,
                "route_payload": {
                    "kind": "term_conflict_missing",
                    "invalid_count": len(invalid_terms),
                },
            })

        # 与原节点一致：先按 confidence 排序找所有命中，再识别冲突
        matches = [
            match for term in terms if (match := _dsa_match_term_in_question(term, question))
        ]
        matches.sort(key=lambda item: item.get("confidence", 0), reverse=True)
        conflicts = _dsa_build_term_conflicts(matches)

        # 多轮澄清：用户已选过 term_id，过滤到该 term 并清空冲突
        selected_matches: list[dict] = []
        if selected_term_id is not None:
            selected_matches = [
                match
                for match in matches
                if int(match.get("term_id") or 0) == int(selected_term_id)
            ]
            if selected_matches:
                matches = selected_matches
                conflicts = []

        term_normalization = {
            "matched_terms": matches,
            "conflicts": conflicts,
            "has_conflict": bool(conflicts),
            "selected_term_id": int(selected_term_id) if selected_matches else None,
            "resolved_by": "clarification" if selected_matches else None,
        }

        # 分支 3：needs_clarification —— 多 term 冲突，让用户选
        if conflicts:
            candidates = _dsa_clarification_candidates_from_conflicts(conflicts)
            names = "、".join(
                sorted(
                    {
                        term.get("display_name") or term.get("name") or str(term.get("id"))
                        for conflict in conflicts
                        for term in conflict.get("terms", [])
                    }
                )
            )
            answer = f"“{conflicts[0]['token']}”可能对应多个业务术语：{names}。请先确认你要使用哪个口径。"
            logger.info("term_conflict 发现冲突: %s", conflicts)
            return jsonable_encoder({
                "status": "needs_clarification",
                "term_normalization": term_normalization,
                "selected_term_id": None,
                "resolved_question": None,
                "answer": answer,
                "error": None,
                "should_retry": False,
                "route_payload": {
                    "kind": "term_conflict_clarification",
                    "conflicts": conflicts,
                    "candidates": candidates,
                },
            })

        # 分支 2：resolved —— 单 term 或澄清后单 term，归一化到 entities.terms
        if matches:
            existing_terms = _dsa_coerce_text_list((entities or {}).get("terms"))
            normalized_terms = _dsa_dedupe_texts([
                *existing_terms,
                *[m["matched_text"] for m in matches],
            ])
            updated_entities = dict(entities or {})
            updated_entities["terms"] = normalized_terms
            logger.info(
                "term_conflict 完成: matched=%s, selected_term_id=%s",
                len(matches),
                term_normalization["selected_term_id"],
            )
            return jsonable_encoder({
                "status": "resolved",
                "term_normalization": term_normalization,
                "selected_term_id": term_normalization["selected_term_id"],
                "resolved_question": question,
                "answer": None,
                "error": None,
                "should_retry": False,
                "route_payload": {
                    "kind": "term_conflict_resolved",
                    "matched_term_ids": [m.get("term_id") for m in matches],
                },
                "entities": updated_entities,
            })

        # 分支 0：not_applicable —— 无命中，透明通过
        logger.info("term_conflict 无命中: 透传 question")
        return jsonable_encoder({
            "status": "not_applicable",
            "term_normalization": term_normalization,
            "selected_term_id": None,
            "resolved_question": None,
            "answer": None,
            "error": None,
            "should_retry": False,
            "route_payload": {"kind": "not_applicable"},
        })

    # ──────────── Phase 7：语义资产解析（metric / dimension / term / field / blueprint） ────────────

    def resolve_metric(
        self,
        *,
        question: str,
        entities: dict | None = None,
        schema_structured: dict | None = None,
        tracer: Any | None = None,
        trace_context: Any | None = None,
    ) -> dict[str, Any]:
        """5 分支 outcome（与原 semantic_asset_resolution_node 节点 1:1 等价）。

        分支：
        - not_applicable：无任何资产命中（term/metric/dimension/field/blueprint 全空）
        - resolved：唯一资产匹配，自动解析
        - needs_clarification：多资产置信度接近（让用户选）
        - missing_metric：metric 配置缺 id/name（错误早退）
        - error：异常降级

        返回 dict（与原节点同构 + Phase 7 新增）：
        - status / semantic_asset_resolution / metric_resolution：向后兼容原节点输出
        - selected_metric_id / resolved_question / answer / error / should_retry
        - route_payload：含 kind, ambiguities, unresolved
        """
        span = None
        if tracer is not None and trace_context is not None:
            try:
                span = tracer.start_span(
                    trace_context,
                    node="metric_resolve",
                    display_name="metric_resolve",
                    input_payload={
                        "question": question,
                        "has_schema": bool(schema_structured),
                        "entity_count": sum(
                            len(v) for k, v in (entities or {}).items()
                            if k in ("terms", "metrics", "dimensions", "filters")
                        ),
                    },
                )
            except Exception:
                span = None
                logger.warning("tracer.start_span 失败，跳过 span", exc_info=True)

        try:
            outcome = self._resolve_metric_impl(
                question=question,
                entities=entities,
                schema_structured=schema_structured,
            )
            if span is not None:
                try:
                    semantic = outcome.get("semantic_asset_resolution") or {}
                    span.end_span(
                        output_payload={
                            "status": outcome["status"],
                            "selected_metric_id": outcome.get("selected_metric_id"),
                            "asset_count": len(semantic.get("assets") or []),
                            "ambiguity_count": len(semantic.get("ambiguities") or []),
                            "unresolved_count": len(semantic.get("unresolved") or []),
                            "metric_count": len((outcome.get("metric_resolution") or {}).get("metrics") or []),
                            "route_payload_kind": (outcome.get("route_payload") or {}).get("kind"),
                        },
                        error=outcome.get("error"),
                    )
                except Exception:
                    logger.warning("tracer.end_span 失败", exc_info=True)
            return outcome
        except Exception as exc:
            if span is not None:
                try:
                    span.end_span(error=repr(exc))
                except Exception:
                    pass
            # 分支 5：error —— 异常降级（保留 metric_resolution 兼容字段）
            return jsonable_encoder({
                "status": "error",
                "semantic_asset_resolution": {
                    "assets": [], "terms": [], "metrics": [], "dimensions": [],
                    "fields": [], "blueprints": [], "ambiguities": [], "unresolved": [],
                },
                "metric_resolution": {"metrics": [], "dimensions": [], "all_matched": True, "unresolved": []},
                "selected_metric_id": None,
                "resolved_question": None,
                "answer": None,
                "error": repr(exc),
                "should_retry": False,
                "route_payload": {"kind": "metric_resolve_error"},
            })

    def _resolve_metric_impl(
        self,
        *,
        question: str,
        entities: dict | None,
        schema_structured: dict | None,
    ) -> dict[str, Any]:
        """resolve_metric 内部实现：5 分支决策 + 返回 8 字段 dict。"""
        entities = entities or {}
        logger.info("semantic_asset_resolution 开始解析资产")

        # 分支 1：missing_metric —— metric/dimension 配置缺 id/name（错误早退）
        invalid_metrics = [
            m for m in (schema_structured or {}).get("metrics") or []
            if not (m.get("id")) or not (m.get("name"))
        ]
        if invalid_metrics:
            logger.warning("metric_resolve 候选缺字段: invalid=%s", len(invalid_metrics))
            return jsonable_encoder({
                "status": "missing_metric",
                "semantic_asset_resolution": {
                    "assets": [], "terms": [], "metrics": [], "dimensions": [],
                    "fields": [], "blueprints": [], "ambiguities": [], "unresolved": [],
                },
                "metric_resolution": {"metrics": [], "dimensions": [], "all_matched": True, "unresolved": []},
                "selected_metric_id": None,
                "resolved_question": None,
                "answer": "指标配置缺失，请联系管理员补全指标字段。",
                "error": "metric 配置缺 id 或 name",
                "should_retry": False,
                "route_payload": {
                    "kind": "metric_resolve_missing",
                    "invalid_count": len(invalid_metrics),
                },
            })

        # 与原节点一致：构建 catalog → 逐 query term 匹配 → 术语链接扩展
        catalog = _dsa_build_semantic_asset_catalog(schema_structured)
        best_by_asset: dict[str, dict] = {}
        candidates_by_query: dict[str, list[dict]] = {}

        for query_term in _dsa_entity_query_terms(entities, question):
            text = query_term["text"]
            preferred_type = query_term.get("preferred_type")
            matched_for_query: list[dict] = []
            for asset in catalog:
                candidate = _dsa_match_semantic_asset(asset, text, question, preferred_type)
                if not candidate:
                    continue
                key = _dsa_asset_identity(candidate)
                if key not in best_by_asset or candidate["confidence"] > best_by_asset[key]["confidence"]:
                    best_by_asset[key] = candidate
                matched_for_query.append(candidate)

            if matched_for_query:
                matched_for_query.sort(key=lambda c: c["confidence"], reverse=True)
                candidates_by_query[text] = matched_for_query

        # 术语关联扩展：命中业务术语时，把显式绑定资产加入解析结果
        for candidate in list(best_by_asset.values()):
            if candidate.get("asset_type") != "term":
                continue
            for linked in _dsa_linked_asset_candidates(candidate, catalog):
                key = _dsa_asset_identity(linked)
                if key not in best_by_asset or linked["confidence"] > best_by_asset[key]["confidence"]:
                    best_by_asset[key] = linked

        sorted_assets = sorted(
            best_by_asset.values(),
            key=lambda c: (c.get("confidence", 0), c.get("asset_type") == "metric"),
            reverse=True,
        )
        semantic_resolution: dict[str, Any] = {
            "assets": sorted_assets,
            "terms": [],
            "metrics": [],
            "dimensions": [],
            "fields": [],
            "blueprints": [],
            "ambiguities": [],
            "unresolved": [],
        }
        for candidate in sorted_assets:
            bucket = _DSA_SEMANTIC_ASSET_BUCKETS.get(candidate["asset_type"])
            if bucket:
                semantic_resolution[bucket].append(candidate)

        for text, candidates in candidates_by_query.items():
            if len(candidates) < 2:
                continue
            top = candidates[0]
            close_candidates = [
                c for c in candidates[:5] if top["confidence"] - c["confidence"] <= 0.08
            ]
            if len(close_candidates) >= 2:
                semantic_resolution["ambiguities"].append(
                    {
                        "text": text,
                        "reason": "多个语义资产置信度接近",
                        "candidates": close_candidates,
                        "resolution_hint": f"请确认“{text}”具体指哪个业务资产",
                    }
                )

        explicit_terms = [t for t in _dsa_entity_query_terms(entities, question) if t.get("preferred_type")]
        for term in explicit_terms:
            text = term["text"]
            if text not in candidates_by_query:
                semantic_resolution["unresolved"].append(
                    {"text": text, "preferred_type": term.get("preferred_type")}
                )

        metric_resolution = _dsa_to_compat_metric_resolution(semantic_resolution, entities, schema_structured)

        # 选最高 confidence metric 作为 selected_metric_id（用于 Phase 7 的 resolved_question 透传）
        top_metric = sorted_assets[0] if sorted_assets else None
        selected_metric_id = (
            top_metric.get("asset_id") if top_metric and top_metric.get("asset_type") == "metric" else None
        )

        # 分支 3：needs_clarification —— 有歧义候选
        if semantic_resolution["ambiguities"]:
            first = semantic_resolution["ambiguities"][0]
            answer = first.get("resolution_hint") or "存在多个语义资产候选，请确认。"
            logger.info("metric_resolve 发现歧义: %s", semantic_resolution["ambiguities"])
            return jsonable_encoder({
                "status": "needs_clarification",
                "semantic_asset_resolution": semantic_resolution,
                "metric_resolution": metric_resolution,
                "selected_metric_id": None,
                "resolved_question": None,
                "answer": answer,
                "error": None,
                "should_retry": False,
                "route_payload": {
                    "kind": "metric_resolve_clarification",
                    "ambiguities": semantic_resolution["ambiguities"],
                    "unresolved": semantic_resolution["unresolved"],
                },
            })

        # 分支 2：resolved —— 有资产命中且无歧义
        if sorted_assets:
            logger.info(
                "metric_resolve 完成: assets=%s, terms=%s, metrics=%s, dimensions=%s, fields=%s, "
                "blueprints=%s, ambiguities=%s, unresolved=%s",
                len(semantic_resolution["assets"]),
                len(semantic_resolution["terms"]),
                len(semantic_resolution["metrics"]),
                len(semantic_resolution["dimensions"]),
                len(semantic_resolution["fields"]),
                len(semantic_resolution["blueprints"]),
                len(semantic_resolution["ambiguities"]),
                len(semantic_resolution["unresolved"]),
            )
            return jsonable_encoder({
                "status": "resolved",
                "semantic_asset_resolution": semantic_resolution,
                "metric_resolution": metric_resolution,
                "selected_metric_id": selected_metric_id,
                "resolved_question": question,
                "answer": None,
                "error": None,
                "should_retry": False,
                "route_payload": {
                    "kind": "metric_resolve_resolved",
                    "asset_ids": [a.get("asset_id") for a in sorted_assets],
                },
            })

        # 分支 0：not_applicable —— 无任何资产命中
        logger.info("metric_resolve 无资产命中: 透传 question")
        return jsonable_encoder({
            "status": "not_applicable",
            "semantic_asset_resolution": semantic_resolution,
            "metric_resolution": metric_resolution,
            "selected_metric_id": None,
            "resolved_question": None,
            "answer": None,
            "error": None,
            "should_retry": False,
            "route_payload": {"kind": "not_applicable"},
        })
