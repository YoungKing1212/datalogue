# ============================================================
# File Name   : capability_manifest.py
# Description:
#   构建数据集能力清单的后端服务。
#
# Responsibilities:
#   - 从数据集、指标、维度和 Manifest 摘要生成业务能力广告。
#   - 对输出执行防泄露扫描，确保 LeadAgent 只看到业务摘要。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.schemas.capability_manifest import CapabilityManifest, CapabilityManifestSummary

FORBIDDEN_VISIBLE_KEYS = {
    "raw_sql",
    "sql",
    "table",
    "table_name",
    "field",
    "fields",
    "column",
    "column_name",
    "schema",
    "blueprint",
    "asset_detail",
    "raw_result",
    "ddl",
    "expr",
}


def _compact_text(value: Any, *, limit: int = 80) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _unique_texts(values: Iterable[Any], *, limit: int = 8) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def _quality_status(dataset: models.SemanticDataset) -> str:
    if dataset.status == "active":
        return "published"
    if dataset.status in {"reviewed", "published"}:
        return str(dataset.status)
    return "draft"


def _manifest_for_dataset(db: Session, dataset_id: int) -> models.DatasetSubAgentManifest | None:
    return (
        db.query(models.DatasetSubAgentManifest)
        .filter(
            models.DatasetSubAgentManifest.dataset_id == dataset_id,
            models.DatasetSubAgentManifest.is_current.is_(True),
        )
        .order_by(models.DatasetSubAgentManifest.created_at.desc())
        .first()
    )


def _manifest_business_summary(manifest: models.DatasetSubAgentManifest | None) -> dict[str, Any]:
    payload = manifest.manifest_json if manifest is not None else {}
    manual = dict((payload or {}).get("manual_fields") or {})
    auto_fields = dict((payload or {}).get("auto_fields") or {})
    permission = manual.get("permission_scope") or auto_fields.get("permission_scope") or {}
    if isinstance(permission, dict):
        permission_scope = _compact_text(permission.get("description") or permission.get("status")) or "dataset"
    else:
        permission_scope = _compact_text(permission) or "dataset"
    return {
        "description": manual.get("description"),
        "business_domain": manual.get("business_domain") or [],
        "sample_questions": manual.get("sample_questions") or [],
        "routing_negative_examples": manual.get("routing_negative_examples") or [],
        "permission_scope": permission_scope,
    }


def _detect_forbidden(value: Any, *, path: str = "") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in FORBIDDEN_VISIBLE_KEYS:
                return f"{path}.{key_text}".strip(".")
            found = _detect_forbidden(item, path=f"{path}.{key_text}".strip("."))
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _detect_forbidden(item, path=f"{path}[{index}]")
            if found:
                return found
    return None


def assert_manifest_payload_safe(payload: dict[str, Any]) -> None:
    """输出防泄露门禁：字段名命中内部资产关键词时直接阻断。"""

    found = _detect_forbidden(payload)
    if found:
        raise ValueError(f"capability_manifest contains forbidden internal details: {found}")


def assert_manifest_safe(manifest: CapabilityManifest | CapabilityManifestSummary) -> None:
    """扫描已成型的 manifest，确保输出面只有业务级能力摘要。"""

    assert_manifest_payload_safe(manifest.model_dump())


def build_dataset_capability_manifest(db: Session, dataset_id: int) -> CapabilityManifest:
    """根据真实数据集语义资产构建 LeadAgent 可见的能力清单。"""

    dataset = db.get(models.SemanticDataset, dataset_id)
    if dataset is None:
        raise ValueError(f"dataset not found: {dataset_id}")

    manifest_summary = _manifest_business_summary(_manifest_for_dataset(db, dataset_id))
    metrics = db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == dataset_id).all()
    dimensions = (
        db.query(models.SemanticDimension)
        .filter(models.SemanticDimension.dataset_id == dataset_id)
        .all()
    )
    metric_names = _unique_texts([m.display_name or m.name for m in metrics], limit=12)
    dimension_names = _unique_texts([d.display_name or d.name for d in dimensions], limit=12)
    domain_hints = _unique_texts(manifest_summary["business_domain"], limit=4)
    typical_questions = _unique_texts(manifest_summary["sample_questions"], limit=6)
    negative_examples = _unique_texts(manifest_summary["routing_negative_examples"], limit=6)
    can_answer = _unique_texts(
        [
            manifest_summary["description"],
            f"围绕{dataset.name}分析" if dataset.name else None,
            *(f"查询{item}" for item in metric_names[:4]),
            *(f"按{item}分析" for item in dimension_names[:4]),
        ],
        limit=8,
    )
    cannot_answer = negative_examples or ["超出该数据集业务范围的问题"]
    route_hints = _unique_texts([dataset.name, *(domain_hints or []), *metric_names, *dimension_names], limit=12)

    result = CapabilityManifest(
        dataset_id=dataset.id,
        business_name=dataset.name,
        can_answer=can_answer,
        cannot_answer=cannot_answer,
        metrics=metric_names,
        dimensions=dimension_names,
        typical_questions=typical_questions,
        route_hints=route_hints,
        permission_scope=manifest_summary["permission_scope"],
        quality_status=_quality_status(dataset),
    )
    assert_manifest_safe(result)
    return result


def list_capability_manifest_summaries(
    db: Session,
    user_context: dict[str, Any] | None = None,
) -> list[CapabilityManifestSummary]:
    """列出所有数据集能力摘要；user_context 预留给后续权限过滤。"""

    _ = user_context
    datasets = db.query(models.SemanticDataset).order_by(models.SemanticDataset.id.desc()).all()
    summaries: list[CapabilityManifestSummary] = []
    for dataset in datasets:
        manifest = build_dataset_capability_manifest(db, dataset.id)
        summary = CapabilityManifestSummary(**manifest.model_dump())
        assert_manifest_safe(summary)
        summaries.append(summary)
    return summaries
