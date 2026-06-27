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
from app.services.dataset_manifest import score_manifest_question


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

    candidates = [_scored_candidate_from_manifest(question, manifest) for manifest in manifests]
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
    candidate = _scored_candidate_from_manifest("", manifest) if manifest else None
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


def _scored_candidate_from_manifest(
    question: str,
    manifest: models.DatasetSubAgentManifest,
) -> dict[str, Any]:
    """基于 Manifest capability 摘要生成内部候选，不读取 schema/SQL/资产详情。"""

    score, reasons, negative_hit = score_manifest_question(question, manifest)
    payload = manifest.manifest_json or {}
    auto_fields = payload.get("auto_fields") or {}
    if negative_hit:
        reasons = [*reasons, "命中负例，降低自动路由优先级。"]
    return {
        "dataset_id": manifest.dataset_id,
        "dataset_name": auto_fields.get("name"),
        "manifest_version": manifest.manifest_version,
        "bound_schema_version": manifest.bound_schema_version,
        "review_status": manifest.review_status,
        "score": round(score, 2),
        "reasons": reasons,
    }


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
