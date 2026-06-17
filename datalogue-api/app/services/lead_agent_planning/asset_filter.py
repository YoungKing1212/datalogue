# ============================================================
# File Name   : asset_filter.py
# Description:
#   LeadAgent 候选资产过滤层。
#
# Responsibilities:
#   - 接收 asset_recall.py 召回的原始候选资产。
#   - 执行去重、类型白名单、置信度截断、Top-K 截断、元信息脱敏、
#     match_signals 截断，输出可供投影层消费的轻量资产列表。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from typing import Any

from app.services.subagent_planning.contracts import CANDIDATE_ASSET_TYPES

from .asset_filter_config import AssetFilterConfig

# 投影输出时单条资产保留的信号字段，避免把内部上下文泄漏给 LeadAgent。
_PROJECTED_SIGNAL_KEYS = {"type", "value", "score"}


def filter_lead_planner_assets(
    candidate_assets: dict[str, Any] | list[dict[str, Any]],
    *,
    config: AssetFilterConfig | None = None,
) -> list[dict[str, Any]]:
    """过滤候选资产，按置信度阈值和 Top-K 限制截断。

    Args:
        candidate_assets: recall_candidate_assets 的原始输出（含 ``assets`` 列表），
            或直接传入资产列表。
        config: 过滤配置；None 时使用默认配置。

    Returns:
        过滤后的资产列表，按 confidence 全局降序排列。
    """
    config = config or AssetFilterConfig()
    raw_assets = _extract_assets(candidate_assets)

    # Step 1: 按 (asset_type, asset_id) 去重，保留置信度最高的一条
    deduped = _deduplicate_assets(raw_assets)

    # Step 2/3: 类型白名单 + 全局置信度硬截断
    globally_valid: list[dict[str, Any]] = []
    for asset in deduped:
        asset_type = str(asset.get("asset_type") or "").strip()
        if asset_type not in CANDIDATE_ASSET_TYPES:
            continue
        confidence = _confidence(asset)
        if confidence < config.global_min_confidence:
            continue
        globally_valid.append(asset)

    # Step 4: 按类型分组，应用类型级阈值与 Top-K 截断
    by_type: dict[str, list[dict[str, Any]]] = {}
    for asset in globally_valid:
        asset_type = str(asset.get("asset_type") or "").strip()
        confidence = _confidence(asset)
        if confidence < config.get_min_confidence(asset_type):
            continue
        by_type.setdefault(asset_type, []).append(asset)

    filtered: list[dict[str, Any]] = []
    # 使用 CANDIDATE_ASSET_TYPES 保证输出类型顺序稳定
    for asset_type in CANDIDATE_ASSET_TYPES:
        group = by_type.get(asset_type, [])
        group.sort(key=_confidence, reverse=True)
        topk = config.get_topk(asset_type)
        for asset in group[:topk]:
            # 复制一份，避免修改原始资产对象
            filtered.append(dict(asset))

    # Step 5: 元信息脱敏 + match_signals 截断
    for asset in filtered:
        metadata = dict(asset.get("metadata") or {})
        asset["metadata"] = _sanitize_metadata(metadata, config.metadata_whitelist)
        signals = list(asset.get("match_signals") or [])
        asset["match_signals"] = _sanitize_signals(signals, config.max_signals_per_asset)

    # Step 6: 合并输出并按置信度全局降序
    filtered.sort(key=_confidence, reverse=True)
    return filtered


def _extract_assets(
    candidate_assets: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从召回输出或裸列表中安全提取资产字典列表。"""
    if isinstance(candidate_assets, dict):
        assets = candidate_assets.get("assets")
    elif isinstance(candidate_assets, list):
        assets = candidate_assets
    else:
        assets = None

    if not isinstance(assets, list):
        return []

    return [dict(asset) for asset in assets if isinstance(asset, dict)]


def _deduplicate_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (asset_type, asset_id) 去重，保留置信度最高的一条。"""
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for asset in assets:
        asset_type = str(asset.get("asset_type") or "").strip()
        asset_id = str(asset.get("asset_id") or "").strip()
        if not asset_type or not asset_id:
            continue
        key = (asset_type, asset_id)
        existing = best_by_key.get(key)
        if existing is None or _confidence(asset) > _confidence(existing):
            best_by_key[key] = dict(asset)
    return list(best_by_key.values())


def _confidence(asset: dict[str, Any]) -> float:
    """安全读取资产置信度，异常值返回 0。"""
    try:
        return float(asset.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def _sanitize_metadata(
    metadata: dict[str, Any],
    whitelist: set[str],
) -> dict[str, Any]:
    """只保留白名单内的元信息字段，防止 QueryGraph 内部上下文泄漏。"""
    if not whitelist:
        return {}
    return {key: value for key, value in metadata.items() if key in whitelist}


def _sanitize_signals(
    signals: list[dict[str, Any]],
    max_signals: int,
) -> list[dict[str, Any]]:
    """保留得分最高的前 N 条信号，并只输出 type/value/score 三个字段。"""
    valid = [signal for signal in signals if isinstance(signal, dict)]
    valid.sort(
        key=lambda signal: float(signal.get("score") or 0),
        reverse=True,
    )
    trimmed = valid[:max_signals] if max_signals > 0 else []

    projected: list[dict[str, Any]] = []
    for signal in trimmed:
        projected.append({key: signal[key] for key in _PROJECTED_SIGNAL_KEYS if key in signal})
    return projected
