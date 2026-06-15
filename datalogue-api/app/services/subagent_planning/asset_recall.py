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

from app.services.dataset_context import build_dataset_query_context
from app.services.subagent_planning.contracts import CandidateAsset

LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET = 2500


def _norm(text: Any) -> str:
    return re.sub(r"[\s_`'\".]+", "", str(text or "").strip().lower())


def _score(question: str, *texts: Any) -> tuple[float, list[dict[str, Any]]]:
    q = _norm(question)
    signals: list[dict[str, Any]] = []
    best = 0.0
    for raw in texts:
        text = str(raw or "").strip()
        normalized = _norm(text)
        if not normalized:
            continue
        if normalized == q:
            best = max(best, 0.98)
            signals.append({"type": "exact", "value": text, "score": 0.98})
        elif normalized in q or q in normalized:
            best = max(best, 0.82)
            signals.append({"type": "contains", "value": text, "score": 0.82})
    return best, signals


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
        match_reason=signals[0]["type"] if signals else "context_candidate",
    ).to_dict()


def _table_assets(structured: dict[str, Any], question: str) -> list[dict[str, Any]]:
    tables_json = structured.get("tables_json") or {}
    selected = tables_json.get("selected_tables") or tables_json.get("tables") or []
    assets: list[dict[str, Any]] = []
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
        confidence, signals = _score(question, name, metadata.get("description"))
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
    for blueprint in structured.get("blueprints") or []:
        confidence, signals = _score(
            question,
            blueprint.get("name"),
            blueprint.get("description"),
            blueprint.get("when_to_use"),
            " ".join(blueprint.get("trigger_keywords") or []),
        )
        metadata = dict(blueprint)
        assets.append(
            _asset(
                "blueprint",
                blueprint.get("id") or blueprint.get("name"),
                str(blueprint.get("name") or ""),
                "analysis_blueprint",
                confidence,
                signals,
                metadata,
            )
        )
    for metric in structured.get("metrics") or []:
        confidence, signals = _score(question, metric.get("name"), metric.get("description"), metric.get("expr"))
        assets.append(
            _asset(
                "metric",
                metric.get("id") or metric.get("name"),
                str(metric.get("name") or ""),
                "semantic_metric",
                confidence,
                signals,
                dict(metric),
            )
        )
    for dimension in structured.get("dimensions") or []:
        confidence, signals = _score(question, dimension.get("name"), dimension.get("description"), dimension.get("expr"))
        assets.append(
            _asset(
                "dimension",
                dimension.get("id") or dimension.get("name"),
                str(dimension.get("name") or ""),
                "semantic_dimension",
                confidence,
                signals,
                dict(dimension),
            )
        )
    for term in structured.get("terms") or []:
        aliases = term.get("aliases") or []
        confidence, signals = _score(question, term.get("name"), term.get("display_name"), " ".join(map(str, aliases)))
        assets.append(
            _asset(
                "term",
                term.get("id") or term.get("name"),
                str(term.get("name") or term.get("display_name") or ""),
                "business_term",
                confidence,
                signals,
                dict(term),
            )
        )
    for field in structured.get("fields") or []:
        table_name = field.get("table_name") or field.get("table")
        column_name = field.get("column_name") or field.get("name") or field.get("column")
        asset_id = f"table:{table_name}.column:{column_name}"
        confidence, signals = _score(question, column_name, field.get("semantic"), field.get("description"), table_name)
        assets.append(_asset("field", asset_id, str(column_name or ""), "schema", confidence, signals, dict(field)))
    assets.extend(_table_assets(structured, question))
    summary = {
        "blueprint_count": sum(1 for asset in assets if asset["asset_type"] == "blueprint"),
        "metric_count": sum(1 for asset in assets if asset["asset_type"] == "metric"),
        "dimension_count": sum(1 for asset in assets if asset["asset_type"] == "dimension"),
        "term_count": sum(1 for asset in assets if asset["asset_type"] == "term"),
        "field_count": sum(1 for asset in assets if asset["asset_type"] == "field"),
        "table_count": sum(1 for asset in assets if asset["asset_type"] == "table"),
    }
    assets.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return {
        "dataset_id": dataset_id,
        "question": question,
        "assets": assets,
        "summary": summary,
        "recall_debug": {
            "schema_source": "lightweight_schema_recall",
            "manifest_version": manifest_version,
            "bound_schema_version": bound_schema_version,
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
        token_budget=LIGHTWEIGHT_CONTEXT_TOKEN_BUDGET,
    )
    return build_candidate_assets_from_context(
        question=question,
        dataset_id=dataset_id,
        context=context,
        manifest_version=manifest_version,
        bound_schema_version=bound_schema_version,
    )
