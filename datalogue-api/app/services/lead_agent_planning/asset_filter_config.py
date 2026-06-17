# ============================================================
# File Name   : asset_filter_config.py
# Description:
#   LeadAgent 渐进式资产注入的过滤配置层。
#
# Responsibilities:
#   - 定义 AssetFilterConfig 配置模型，集中承载置信度阈值、Top-K、
#     元信息脱敏白名单等过滤策略。
#   - 提供 build_filter_config，按 Settings -> 数据集级覆盖 -> 显式覆盖
#     的优先级合并配置（数据集覆盖当前为兼容性占位，不阻塞主链路）。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings


class AssetFilterConfig(BaseModel):
    """资产过滤配置，从 Settings 派生或按运行时参数覆盖。"""

    # --- 按资产类型的 Top-K 限制 ---
    topk_blueprint: int = 3
    topk_metric: int = 5
    topk_dimension: int = 5
    topk_term: int = 5
    topk_field: int = 10
    topk_table: int = 8

    # --- 按资产类型的置信度阈值 ---
    min_confidence_blueprint: float = 0.60
    min_confidence_metric: float = 0.35
    min_confidence_dimension: float = 0.35
    min_confidence_term: float = 0.30
    min_confidence_field: float = 0.25
    min_confidence_table: float = 0.25

    # --- 全局兜底置信度 ---
    global_min_confidence: float = 0.20

    # --- 元信息脱敏白名单 ---
    metadata_whitelist: set[str] = Field(
        default_factory=lambda: {"table_name", "column_name", "parameters", "expr"}
    )

    # --- 单条资产保留的 match_signals 数量 ---
    max_signals_per_asset: int = 3

    def get_topk(self, asset_type: str) -> int:
        """按资产类型读取 Top-K 限制，未知类型返回宽松默认值。"""
        return getattr(self, f"topk_{asset_type}", 10)

    def get_min_confidence(self, asset_type: str) -> float:
        """按资产类型读取置信度阈值，未知类型返回宽松默认值。"""
        return getattr(self, f"min_confidence_{asset_type}", 0.25)


def _parse_metadata_whitelist(value: str) -> set[str]:
    """把逗号分隔的字符串解析为元信息白名单集合；空字符串表示全部脱敏。"""
    return {part.strip() for part in (value or "").split(",") if part.strip()}


def _load_dataset_filter_overrides(db: Session, dataset_id: int) -> dict[str, Any]:
    """尝试读取数据集级 asset_filter 覆盖配置。

    当前语义数据集模型尚未固化 ``planner_config`` 字段，因此本函数以
    兼容方式读取：字段存在则取 ``asset_filter`` 子对象，不存在或读取失败
    则返回空字典，避免阻塞 Phase 2 主链路。
    """
    try:
        from app import models

        dataset = db.query(models.SemanticDataset).filter_by(id=dataset_id).first()
        if dataset is None:
            return {}
        raw_config = getattr(dataset, "planner_config", None) or {}
        if not isinstance(raw_config, dict):
            return {}
        asset_filter = raw_config.get("asset_filter") or {}
        return asset_filter if isinstance(asset_filter, dict) else {}
    except Exception:
        # 数据库列缺失、模型未迁移或查询异常均降级为空覆盖。
        return {}


def build_filter_config(
    *,
    settings: Settings,
    dataset_id: int | None = None,
    db: Session | None = None,
    explicit_overrides: dict[str, Any] | None = None,
) -> AssetFilterConfig:
    """按优先级合并过滤配置。

    优先级：运行时显式覆盖 > 数据集级覆盖 > Settings 环境变量 > 代码默认值。
    """
    config = AssetFilterConfig(
        topk_blueprint=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_BLUEPRINT,
        topk_metric=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_METRIC,
        topk_dimension=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_DIMENSION,
        topk_term=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_TERM,
        topk_field=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_FIELD,
        topk_table=settings.LEAD_AGENT_PROGRESSIVE_ASSET_TOPK_TABLE,
        min_confidence_blueprint=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_BLUEPRINT,
        min_confidence_metric=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_METRIC,
        min_confidence_dimension=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_DIMENSION,
        min_confidence_term=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_TERM,
        min_confidence_field=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_FIELD,
        min_confidence_table=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MIN_CONFIDENCE_TABLE,
        global_min_confidence=settings.LEAD_AGENT_PROGRESSIVE_ASSET_GLOBAL_MIN_CONFIDENCE,
        metadata_whitelist=_parse_metadata_whitelist(
            settings.LEAD_AGENT_PROGRESSIVE_ASSET_METADATA_WHITELIST
        ),
        max_signals_per_asset=settings.LEAD_AGENT_PROGRESSIVE_ASSET_MAX_SIGNALS_PER_ASSET,
    )

    # 2. 数据集级覆盖（当前为兼容性占位，读取失败不抛异常）
    if dataset_id is not None and db is not None:
        dataset_overrides = _load_dataset_filter_overrides(db, dataset_id)
        for key, value in dataset_overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

    # 3. 运行时显式覆盖（最高优先级）
    if explicit_overrides:
        for key, value in explicit_overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

    return config
