# ============================================================
# File Name   : asset_catalog.py
# Description:
#   SubAgent Planner 使用的候选资产轻量目录投影。
#
# Responsibilities:
#   - 将召回层原始 candidate_assets 裁剪为规划器可见的轻量资产目录。
#   - 保留资产类型、标识、描述、置信度和版本信息，移除字段明细、SQL 与原始元数据。
#   - 构建后续资产详情校验可复用的允许资产范围。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from typing import Any


ALLOWED_CATALOG_ASSET_TYPES = {"metric", "dimension", "table", "blueprint"}
DESCRIPTION_KEYS = ("description", "comment", "semantic", "business_desc", "expr", "when_to_use")


def project_lightweight_asset_catalog(
    candidate_assets: dict[str, Any] | None,
    max_signals_per_asset: int = 3,
) -> dict[str, Any]:
    source = candidate_assets if isinstance(candidate_assets, dict) else {}
    recall_debug = source.get("recall_debug")
    recall_debug = recall_debug if isinstance(recall_debug, dict) else {}
    schema_version = recall_debug.get("bound_schema_version") or source.get("bound_schema_version")
    manifest_version = recall_debug.get("manifest_version") or source.get("manifest_version")

    projected_assets = []
    raw_assets = source.get("assets")
    if not isinstance(raw_assets, list):
        raw_assets = []

    for asset in raw_assets:
        if not isinstance(asset, dict):
            continue

        asset_type = asset.get("asset_type")
        asset_id = asset.get("asset_id")
        if asset_type not in ALLOWED_CATALOG_ASSET_TYPES or _is_blank_asset_id(asset_id):
            continue

        projected_assets.append(
            {
                "asset_type": asset_type,
                "asset_id": asset_id,
                "name": asset.get("name"),
                "display_name": asset.get("display_name"),
                "description": _asset_description(asset),
                "confidence": _round_confidence(asset.get("confidence")),
                "match_signals": _match_signals(asset.get("match_signals"), max_signals_per_asset),
                "schema_version": schema_version,
                "manifest_version": manifest_version,
            }
        )

    projected_assets.sort(key=lambda item: item["confidence"], reverse=True)
    return {
        "dataset_id": source.get("dataset_id"),
        "question": source.get("question"),
        "assets": projected_assets,
        "summary": {
            "raw_asset_count": len(raw_assets),
            "projected_asset_count": len(projected_assets),
            "allowed_asset_types": sorted(ALLOWED_CATALOG_ASSET_TYPES),
            "schema_version": schema_version,
            "manifest_version": manifest_version,
        },
    }


def build_allowed_asset_scope(lightweight_catalog: dict[str, Any] | None) -> set[tuple[str, str]]:
    if not isinstance(lightweight_catalog, dict):
        return set()

    scope = set()
    assets = lightweight_catalog.get("assets")
    if not isinstance(assets, list):
        return scope

    for asset in assets:
        if not isinstance(asset, dict):
            continue

        asset_type = asset.get("asset_type")
        asset_id = asset.get("asset_id")
        if asset_type in ALLOWED_CATALOG_ASSET_TYPES and not _is_blank_asset_id(asset_id):
            scope.add((asset_type, str(asset_id)))

    return scope


def _asset_description(asset: dict[str, Any]) -> Any:
    metadata = asset.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    for key in DESCRIPTION_KEYS:
        value = metadata.get(key)
        if value:
            return value
        value = asset.get(key)
        if value:
            return value
    return None


def _round_confidence(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _match_signals(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[: max(0, limit)]


def _is_blank_asset_id(value: Any) -> bool:
    return value is None or str(value).strip() == ""
