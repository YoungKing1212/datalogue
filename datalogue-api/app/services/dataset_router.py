# ============================================================
# File Name   : dataset_router.py
# Description:
#   数据集 SubAgent Manifest 路由服务。
#
# Responsibilities:
#   - 在未手动选择数据集时，根据 current Manifest 为问题选择数据集。
#   - 在已手动选择数据集时，锁定该数据集并携带 Manifest 版本三元组。
#   - 为聊天入口和后续 LeadAgent 接入提供稳定的路由决策结构。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.schemas.capability_manifest import CapabilityManifestSummary
from app.services.capability_manifest import (
    build_dataset_capability_manifest,
    list_capability_manifest_summaries,
)


AUTO_SELECT_THRESHOLD = 0.65
AUTO_SELECT_MARGIN = 0.12
MAX_CANDIDATES = 3
CAPABILITY_CANDIDATE_KEYS = (
    "dataset_id",
    "dataset_name",
    "reason",
    "confidence",
    "requires_confirmation",
)


def _settings_float(name: str, default: float) -> float:
    try:
        return float(getattr(get_settings(), name, default) or default)
    except (TypeError, ValueError):
        return default


def _settings_int(name: str, default: int) -> int:
    try:
        return int(getattr(get_settings(), name, default) or default)
    except (TypeError, ValueError):
        return default


def route_dataset_for_question(
    db: Session,
    question: str,
    *,
    dataset_id: int | None = None,
) -> dict[str, Any]:
    """返回聊天入口的数据集路由决策。

    已传 dataset_id 时不做自动改选，避免覆盖用户显式上下文；未传时仅在
    current Manifest 证据足够明确时自动选择。
    """

    if dataset_id is not None:
        return _locked_decision(db, dataset_id)

    manifests = (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.is_current.is_(True),
            models.DatasetSubAgentManifest.review_status == "current",
        )
        .order_by(models.DatasetSubAgentManifest.dataset_id)
        .all()
    )
    if not manifests:
        return {
            "decision": "no_match",
            "dataset_id": None,
            "manifest_version": None,
            "bound_schema_version": None,
            "score": 0,
            "candidates": [],
            "reason": "当前没有可用于自动路由的 current SubAgent Manifest。",
        }

    manifest_by_dataset_id = {manifest.dataset_id: manifest for manifest in manifests}
    summaries = [
        summary
        for summary in list_capability_manifest_summaries(db)
        if summary.dataset_id in manifest_by_dataset_id
    ]
    candidates = [
        _scored_candidate_from_summary(question, summary, manifest_by_dataset_id[summary.dataset_id])
        for summary in summaries
    ]
    if not candidates:
        return {
            "decision": "no_match",
            "dataset_id": None,
            "manifest_version": None,
            "bound_schema_version": None,
            "score": 0,
            "candidates": [],
            "reason": "当前没有可用于自动路由的 capability manifest 摘要。",
        }
    candidates.sort(key=lambda item: item["score"], reverse=True)  # 内部排序用分数，候选输出不暴露打分细节字段。
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    margin = top["score"] - (second["score"] if second else 0)
    auto_select_threshold = _settings_float(
        "DATASET_ROUTER_AUTO_SELECT_THRESHOLD", AUTO_SELECT_THRESHOLD
    )
    auto_select_margin = _settings_float(
        "DATASET_ROUTER_AUTO_SELECT_MARGIN", AUTO_SELECT_MARGIN
    )
    max_candidates = _settings_int("DATASET_ROUTER_MAX_CANDIDATES", MAX_CANDIDATES)
    visible_candidates = candidates[:max_candidates]

    if top["score"] >= auto_select_threshold and margin >= auto_select_margin:
        return {
            "decision": "selected",
            "dataset_id": top["dataset_id"],
            "manifest_version": top["manifest_version"],
            "bound_schema_version": top["bound_schema_version"],
            "score": top["score"],
            "candidates": _capability_candidates(visible_candidates, requires_confirmation=False),
            "reason": "Manifest 路由证据明确，自动选择得分最高的数据集。",
        }

    if top["score"] >= auto_select_threshold:
        return {
            "decision": "ambiguous",
            "dataset_id": None,
            "manifest_version": None,
            "bound_schema_version": None,
            "score": top["score"],
            "candidates": _capability_candidates(visible_candidates, requires_confirmation=True),
            "reason": "多个数据集的 Manifest 得分接近，需要用户确认。",
        }

    return {
        "decision": "no_match",
        "dataset_id": None,
        "manifest_version": None,
        "bound_schema_version": None,
        "score": top["score"],
        "candidates": _capability_candidates(visible_candidates, requires_confirmation=True),
        "reason": "没有 Manifest 达到自动路由阈值。",
    }


def _locked_decision(db: Session, dataset_id: int) -> dict[str, Any]:
    manifest = (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.dataset_id == dataset_id,
            models.DatasetSubAgentManifest.is_current.is_(True),
        )
        .order_by(models.DatasetSubAgentManifest.created_at.desc())
        .first()
    )
    dataset = db.get(models.SemanticDataset, dataset_id)
    summary = (
        CapabilityManifestSummary(**build_dataset_capability_manifest(db, dataset_id).model_dump())
        if manifest
        else None
    )
    candidate = _scored_candidate_from_summary("", summary, manifest) if summary and manifest else None
    return {
        "decision": "locked",
        "dataset_id": dataset_id,
        "manifest_version": manifest.manifest_version if manifest else None,
        "bound_schema_version": manifest.bound_schema_version if manifest else None,
        "score": 1 if manifest else 0,
        "candidates": _capability_candidates([candidate], requires_confirmation=False)
        if candidate
        else [],
        "reason": "用户已显式选择数据集，跳过自动改选。",
        "dataset_name": dataset.name if dataset else None,
    }


def _scored_candidate_from_summary(
    question: str,
    summary: CapabilityManifestSummary,
    manifest: models.DatasetSubAgentManifest,
) -> dict[str, Any]:
    """基于能力清单 summary 打分，禁止回读 schema/SQL/完整资产。"""

    score, reasons = _score_capability_summary(question, summary)
    return {
        "dataset_id": summary.dataset_id,
        "dataset_name": summary.business_name,
        "manifest_version": manifest.manifest_version,
        "bound_schema_version": manifest.bound_schema_version,
        "review_status": manifest.review_status,
        "score": round(score, 2),
        "reasons": reasons,
    }


def _score_capability_summary(
    question: str,
    summary: CapabilityManifestSummary,
) -> tuple[float, list[str]]:
    """只根据业务级能力摘要计算路由分，不能依赖字段、表或 SQL 细节。"""

    q_norm = _normalize_text(question)
    if not q_norm:
        return 1.0, ["用户已显式选择该数据集。"]

    reasons: list[str] = []
    score = 0.0

    negative_hits = _matched_labels(q_norm, summary.cannot_answer)
    if negative_hits:
        return 0.24, [f"命中不可回答范围：{negative_hits[0]}。"]

    typical_hits = _matched_labels(q_norm, summary.typical_questions)
    if typical_hits:
        # 典型问题是候选召回的强证据，但不能继续叠加指标/维度把同题多数据集误判成自动派发。
        return 0.72, [f"命中典型正例：{typical_hits[0]}。"]

    metric_hits = _matched_labels(q_norm, summary.metrics)
    if metric_hits:
        score += min(0.24, 0.12 * len(metric_hits))
        reasons.append(f"命中指标名称：{'、'.join(metric_hits[:2])}。")

    dimension_hits = _matched_labels(q_norm, summary.dimensions)
    if dimension_hits:
        score += min(0.16, 0.08 * len(dimension_hits))
        reasons.append(f"命中维度名称：{'、'.join(dimension_hits[:2])}。")

    hint_hits = _matched_labels(q_norm, summary.route_hints + summary.can_answer)
    if hint_hits:
        score += min(0.2, 0.1 * len(hint_hits))
        reasons.append(f"命中业务能力摘要：{hint_hits[0]}。")

    if not reasons:
        reasons.append("未命中 capability manifest 中的稳定路由证据。")
    return min(score, 1.0), reasons


def _normalize_text(text: str) -> str:
    return "".join(str(text or "").lower().split())


def _matched_labels(question_norm: str, labels: list[str]) -> list[str]:
    matched: list[str] = []
    for label in labels:
        label_text = str(label or "").strip()
        label_norm = _normalize_text(label_text)
        if not label_norm:
            continue
        if label_norm in question_norm or question_norm in label_norm:
            matched.append(label_text)
    return matched


def _capability_candidates(
    candidates: list[dict[str, Any]],
    *,
    requires_confirmation: bool,
) -> list[dict[str, Any]]:
    """把内部打分候选瘦身成 LeadAgent 可暴露的 capability manifest 摘要。"""

    visible: list[dict[str, Any]] = []
    for item in candidates:
        reason = "；".join((item.get("reasons") or [])[:2])
        visible.append(
            {
                "dataset_id": item.get("dataset_id"),
                "dataset_name": item.get("dataset_name"),
                "reason": reason,
                "confidence": item.get("score", 0),
                "requires_confirmation": requires_confirmation,
            }
        )
    return visible
