# ============================================================
# File Name   : asset_recall.py
# Description:
#   SubAgent 轻量候选资产召回服务。
#
# Responsibilities:
#   - 前移轻量 Schema 召回，获得规划所需的结构化上下文。
#   - 统一输出 blueprint/metric/dimension/term/field/table 六类候选资产。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.dataset_context import build_dataset_query_context
from app.services.subagent_planning.contracts import CandidateAsset

LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET = 2500
SCORE_MODEL_VERSION = "candidate_asset_score_v2"
MAX_CONFIDENCE = 0.99

BLUEPRINT_CANDIDATE_METADATA_KEYS = {
    "id",
    "name",
    "display_name",
    "description",
    "when_to_use",
    "implementation_type",
    "trigger_keywords",
    "trigger_examples",
    "parameters",
}

SIGNAL_WEIGHTS = {
    "exact": 0.55,
    "contains": 0.28,
    "alias": 0.22,
    "synonym": 0.22,
    "trigger_example": 0.26,
    "field_display": 0.35,
    "table_context": 0.28,
}

SIGNAL_REASON_ORDER = {
    "exact": 0,
    "contains": 1,
    "alias": 2,
    "synonym": 3,
    "trigger_example": 4,
    "field_display": 5,
    "table_context": 6,
}


def _candidate_context_token_budget() -> int:
    try:
        return int(
            getattr(
                get_settings(),
                "SUBAGENT_CANDIDATE_ASSET_CONTEXT_TOKEN_BUDGET",
                LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET,
            )
            or LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET
        )
    except (TypeError, ValueError):
        return LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return value


def _first_text(*values: Any) -> str:
    for value in _text_values(*values):
        return value
    return ""


def _text_values(*values: Any) -> list[str]:
    texts: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            texts.extend(_text_values(*value))
        elif value not in (None, "", [], {}):
            text = str(value).strip()
            if text:
                texts.append(text)
    return texts


def _norm(text: Any) -> str:
    return re.sub(r"[\s_`'\".]+", "", str(text or "").strip().lower())


def _blueprint_candidate_metadata(blueprint: dict[str, Any]) -> dict[str, Any]:
    """只保留规划判断所需蓝图摘要；SQL 模板和步骤主体留在 DatasetAgent 内部执行层。"""

    metadata: dict[str, Any] = {}
    for key in BLUEPRINT_CANDIDATE_METADATA_KEYS:
        value = blueprint.get(key)
        if value not in (None, "", [], {}):
            metadata[key] = value
    return metadata


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _matched_fragments(question: str, normalized: str) -> list[str]:
    if not normalized or not question:
        return []
    if normalized in question:
        return [normalized]
    fragments: list[str] = []
    seen: set[str] = set()
    if _has_cjk(normalized):
        cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]+", normalized))
        max_size = min(6, len(cjk_text))
        for size in range(max_size, 1, -1):
            for index in range(0, len(cjk_text) - size + 1):
                fragment = cjk_text[index : index + size]
                if fragment in seen or fragment not in question:
                    continue
                if any(fragment in existing for existing in fragments):
                    continue
                fragments.append(fragment)
                seen.add(fragment)
    for fragment in re.findall(r"[a-z0-9]{2,}", normalized):
        if fragment in question and fragment not in seen:
            fragments.append(fragment)
            seen.add(fragment)
    return fragments


def _match_factor(question: str, normalized: str) -> tuple[float, str, list[str]]:
    if normalized == question:
        return 1.0, "full_exact", [normalized]
    if normalized in question:
        return 1.0, "phrase_in_question", [normalized]
    if question in normalized:
        return 0.9, "question_in_value", [question]
    fragments = _matched_fragments(question, normalized)
    if not fragments:
        return 0.0, "", []
    covered = sum(len(fragment) for fragment in fragments)
    coverage = covered / max(1, min(len(question), len(normalized)))
    if coverage >= 0.55:
        return 0.85, "strong_overlap", fragments
    return 0.65, "partial_overlap", fragments


def _score_input(signal_type: str, *values: Any) -> dict[str, Any]:
    return {"type": signal_type, "values": _text_values(*values)}


def _score(question: str, *inputs: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    q = _norm(question)
    if not q:
        return 0.0, []
    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    total = 0.0
    for item in inputs:
        signal_type = str(item.get("type") or "contains")
        weight = float(item.get("weight") or SIGNAL_WEIGHTS.get(signal_type, SIGNAL_WEIGHTS["contains"]))
        for text in _text_values(item.get("values")):
            normalized = _norm(text)
            if not normalized:
                continue
            factor, match, fragments = _match_factor(q, normalized)
            if factor <= 0:
                continue
            key = (signal_type, normalized)
            if key in seen:
                continue
            seen.add(key)
            score = round(weight * factor, 4)
            total += score
            signals.append(
                {
                    "type": signal_type,
                    "value": text,
                    "score": score,
                    "match": match,
                    "fragments": fragments,
                }
            )
    signals.sort(key=lambda item: item.get("score", 0), reverse=True)
    return min(MAX_CONFIDENCE, round(total, 4)), signals


def _match_reason(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "context_candidate"
    types = {str(signal.get("type") or "") for signal in signals if signal.get("type")}
    ordered = sorted(types, key=lambda value: SIGNAL_REASON_ORDER.get(value, 99))
    return "+".join(ordered)


def _asset(
    asset_type: str,
    asset_id: str | int,
    name: str,
    source: str,
    confidence: float,
    signals: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return CandidateAsset(
        asset_type=asset_type,
        asset_id=asset_id,
        name=name,
        display_name=metadata.get("display_name") or metadata.get("semantic") or name,
        source=source,
        confidence=confidence,
        match_signals=signals,
        metadata=metadata,
        usage="candidate",
        match_reason=_match_reason(signals),
    ).to_dict()


def _table_context_by_name(structured: dict[str, Any]) -> dict[str, list[str]]:
    tables_json = structured.get("tables_json") or {}
    if not isinstance(tables_json, dict):
        tables_json = {}
    selected = tables_json.get("selected_tables") or tables_json.get("tables") or []
    contexts: dict[str, list[str]] = {}
    for item in selected:
        if isinstance(item, str):
            name = item
            values = [item]
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("table_name") or "")
            values = _text_values(
                name,
                item.get("display_name"),
                item.get("description"),
                item.get("comment"),
                item.get("semantic"),
            )
        else:
            continue
        normalized = _norm(name)
        if normalized:
            contexts[normalized] = values
    return contexts


def _score_audit(assets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_type: dict[str, dict[str, Any]] = {}
    scored_assets = 0
    signal_types: set[str] = set()
    for asset in assets:
        asset_type = str(asset.get("asset_type") or "")
        confidence = float(asset.get("confidence") or 0)
        bucket = by_type.setdefault(
            asset_type,
            {
                "asset_type": asset_type,
                "count": 0,
                "scored_count": 0,
                "total_confidence": 0.0,
                "max_confidence": 0.0,
            },
        )
        bucket["count"] += 1
        bucket["total_confidence"] += confidence
        bucket["max_confidence"] = max(bucket["max_confidence"], confidence)
        if confidence > 0:
            scored_assets += 1
            bucket["scored_count"] += 1
        for signal in asset.get("match_signals") or []:
            signal_type = signal.get("type")
            if signal_type:
                signal_types.add(str(signal_type))
    top_asset_types: list[dict[str, Any]] = []
    for item in by_type.values():
        count = max(1, int(item["count"]))
        top_asset_types.append(
            {
                "asset_type": item["asset_type"],
                "count": item["count"],
                "scored_count": item["scored_count"],
                "max_confidence": round(float(item["max_confidence"]), 4),
                "avg_confidence": round(float(item["total_confidence"]) / count, 4),
            }
        )
    top_asset_types.sort(
        key=lambda item: (item["max_confidence"], item["scored_count"], item["count"]),
        reverse=True,
    )
    coverage = {
        "total_assets": len(assets),
        "scored_assets": scored_assets,
        "scored_ratio": round(scored_assets / len(assets), 4) if assets else 0.0,
        "signal_types": sorted(signal_types, key=lambda value: SIGNAL_REASON_ORDER.get(value, 99)),
    }
    return top_asset_types[:3], coverage


def _table_assets(structured: dict[str, Any], question: str) -> list[dict[str, Any]]:
    tables_json = structured.get("tables_json") or {}
    if not isinstance(tables_json, dict):
        tables_json = {}
    selected = tables_json.get("selected_tables") or tables_json.get("tables") or []
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected:
        if isinstance(item, str):
            name = item
            metadata = {"table_name": item}
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("table_name") or "")
            metadata = dict(item)
            metadata["table_name"] = name
        else:
            continue
        if not name:
            continue
        normalized = _norm(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        confidence, signals = _score(
            question,
            _score_input("exact", name),
            _score_input(
                "table_context",
                name,
                metadata.get("display_name"),
                metadata.get("description"),
                metadata.get("comment"),
                metadata.get("semantic"),
            ),
        )
        assets.append(_asset("table", name, name, "schema", confidence, signals, metadata))
    for field in structured.get("fields") or []:
        mapping = _as_mapping(field)
        if not mapping:
            continue
        name = _first_text(mapping.get("table_name"), mapping.get("table"))
        normalized = _norm(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        metadata = {"table_name": name, "source": "fields"}
        confidence, signals = _score(question, _score_input("exact", name), _score_input("table_context", name))
        assets.append(_asset("table", name, name, "schema", confidence, signals, metadata))
    return assets


def build_candidate_assets_from_context(
    *,
    question: str,
    dataset_id: int,
    context: dict[str, Any],
    manifest_version: str | None,
    bound_schema_version: str | None,
) -> dict[str, Any]:
    structured = context.get("schema_structured") or {}
    assets: list[dict[str, Any]] = []
    if not isinstance(structured, dict):
        structured = {}
    table_contexts = _table_context_by_name(structured)
    for raw_blueprint in structured.get("blueprints") or []:
        blueprint = _as_mapping(raw_blueprint)
        if not blueprint:
            continue
        name = _first_text(blueprint.get("name"), blueprint.get("display_name"))
        asset_id = blueprint.get("id") or name
        if not asset_id or not name:
            continue
        confidence, signals = _score(
            question,
            _score_input("exact", name),
            _score_input("contains", blueprint.get("display_name"), blueprint.get("description"), blueprint.get("when_to_use")),
            _score_input("alias", blueprint.get("trigger_keywords")),
            _score_input("trigger_example", blueprint.get("trigger_examples")),
        )
        metadata = _blueprint_candidate_metadata(blueprint)
        assets.append(
            _asset(
                "blueprint",
                asset_id,
                name,
                "analysis_blueprint",
                confidence,
                signals,
                metadata,
            )
        )
    for raw_metric in structured.get("metrics") or []:
        metric = _as_mapping(raw_metric)
        if not metric:
            continue
        name = _first_text(metric.get("name"), metric.get("display_name"))
        asset_id = metric.get("id") or name
        if not asset_id or not name:
            continue
        confidence, signals = _score(
            question,
            _score_input("exact", name),
            _score_input("contains", metric.get("display_name"), metric.get("description"), metric.get("expr")),
            _score_input("synonym", metric.get("synonyms")),
        )
        assets.append(
            _asset(
                "metric",
                asset_id,
                name,
                "semantic_metric",
                confidence,
                signals,
                dict(metric),
            )
        )
    for raw_dimension in structured.get("dimensions") or []:
        dimension = _as_mapping(raw_dimension)
        if not dimension:
            continue
        name = _first_text(dimension.get("name"), dimension.get("display_name"))
        asset_id = dimension.get("id") or name
        if not asset_id or not name:
            continue
        confidence, signals = _score(
            question,
            _score_input("exact", name),
            _score_input("contains", dimension.get("display_name"), dimension.get("description"), dimension.get("expr")),
            _score_input("synonym", dimension.get("synonyms")),
        )
        assets.append(
            _asset(
                "dimension",
                asset_id,
                name,
                "semantic_dimension",
                confidence,
                signals,
                dict(dimension),
            )
        )
    for raw_term in structured.get("terms") or []:
        term = _as_mapping(raw_term)
        if not term:
            continue
        name = _first_text(term.get("name"), term.get("display_name"))
        asset_id = term.get("id") or name
        if not asset_id or not name:
            continue
        confidence, signals = _score(
            question,
            _score_input("exact", name),
            _score_input("contains", term.get("display_name"), term.get("description")),
            _score_input("alias", term.get("aliases")),
            _score_input("synonym", term.get("synonyms")),
        )
        assets.append(
            _asset(
                "term",
                asset_id,
                name,
                "business_term",
                confidence,
                signals,
                dict(term),
            )
        )
    for raw_field in structured.get("fields") or []:
        field = _as_mapping(raw_field)
        if not field:
            continue
        table_name = _first_text(field.get("table_name"), field.get("table"))
        column_name = _first_text(field.get("column_name"), field.get("name"), field.get("column"))
        if not table_name or not column_name:
            continue
        asset_id = f"table:{table_name}.column:{column_name}"
        confidence, signals = _score(
            question,
            _score_input("exact", column_name),
            _score_input(
                "field_display",
                field.get("display_name"),
                field.get("semantic"),
                field.get("business_desc"),
                field.get("effective_desc"),
                field.get("column_comment"),
                field.get("description"),
            ),
            _score_input("synonym", field.get("synonyms")),
            _score_input("table_context", table_name, table_contexts.get(_norm(table_name))),
        )
        assets.append(_asset("field", asset_id, column_name, "schema", confidence, signals, dict(field)))
    assets.extend(_table_assets(structured, question))
    assets.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    top_asset_types, coverage = _score_audit(assets)
    summary = {
        "blueprint_count": sum(1 for asset in assets if asset["asset_type"] == "blueprint"),
        "metric_count": sum(1 for asset in assets if asset["asset_type"] == "metric"),
        "dimension_count": sum(1 for asset in assets if asset["asset_type"] == "dimension"),
        "term_count": sum(1 for asset in assets if asset["asset_type"] == "term"),
        "field_count": sum(1 for asset in assets if asset["asset_type"] == "field"),
        "table_count": sum(1 for asset in assets if asset["asset_type"] == "table"),
        "score_model_version": SCORE_MODEL_VERSION,
        "top_asset_types": top_asset_types,
        "coverage": coverage,
    }
    return {
        "dataset_id": dataset_id,
        "question": question,
        "assets": assets,
        "summary": summary,
        "recall_debug": {
            "schema_source": "lightweight_schema_recall",
            "manifest_version": manifest_version,
            "bound_schema_version": bound_schema_version,
            "score_model_version": SCORE_MODEL_VERSION,
            "top_asset_types": top_asset_types,
            "coverage": coverage,
            "dataset_context_debug": context.get("dataset_context_debug") or {},
        },
        "context": context,
    }


def recall_candidate_assets(
    db: Session,
    *,
    dataset_id: int,
    question: str,
    manifest_version: str | None,
    bound_schema_version: str | None,
) -> dict[str, Any]:
    context = build_dataset_query_context(
        db,
        dataset_id,
        question=question,
        token_budget=_candidate_context_token_budget(),
    )
    return build_candidate_assets_from_context(
        question=question,
        dataset_id=dataset_id,
        context=context,
        manifest_version=manifest_version,
        bound_schema_version=bound_schema_version,
    )
