# ============================================================
# File Name   : capabilities.py
# Description:
#   BI Agent K1 能力清单与数据集能力摘要清洗服务。
#
# Responsibilities:
#   - 构建 LeadAgent 可见的最小工具能力清单。
#   - 将 DatasetAgent 或数据集侧原始能力信息清洗成路由级摘要 DTO。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.core.schemas.bi_agent import BIAgentCapability, DatasetCapabilitySummary

SAFE_MAPPING_LABEL_KEYS = ("display_name", "name", "title", "question")


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _safe_mapping_label(value: Mapping[str, Any]) -> str | None:
    for key in SAFE_MAPPING_LABEL_KEYS:
        label = value.get(key)
        if isinstance(label, str) and label.strip():
            return label.strip()
    return None


def _append_safe_text(items: list[str], value: Any) -> None:
    if value is None or isinstance(value, bytes):
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            items.append(text)
        return
    if isinstance(value, Mapping):
        # Mapping 只允许提取明确的安全显示字段，禁止把 schema/sql/result_rows 等内部上下文整体字符串化。
        label = _safe_mapping_label(value)
        if label:
            items.append(label)
        return
    if isinstance(value, Iterable):
        # 嵌套列表/集合只展开成员；复杂成员仍走同一白名单规则，避免内部结构通过 repr 泄露。
        for item in value:
            _append_safe_text(items, item)
        return
    if isinstance(value, (int, float, bool)):
        text = _optional_text(value)
        if text is not None:
            items.append(text)


def _string_list(value: Any) -> list[str]:
    items: list[str] = []
    _append_safe_text(items, value)
    return items


def build_bi_agent_capabilities() -> list[BIAgentCapability]:
    """返回 K1 阶段 LeadAgent 允许暴露的工具面；DatasetAgent 原子工具不得进入该清单。"""

    return [
        BIAgentCapability(name="list_dataset_capabilities", status="enabled"),
        BIAgentCapability(name="request_dataset_confirmation", status="enabled"),
        BIAgentCapability(name="query_dataset", status="enabled"),
        BIAgentCapability(
            name="query_multiple_datasets",
            status="disabled",
            disabled_reason="K1 阶段只允许用户确认后的单数据集查询。",
            replacement="query_dataset",
        ),
    ]


def sanitize_dataset_capability(raw: Mapping[str, Any]) -> DatasetCapabilitySummary:
    """只按白名单读取路由摘要字段，避免 raw 中的 schema、SQL、DSL、候选资产等内部上下文外泄。"""

    return DatasetCapabilitySummary(
        dataset_id=raw["dataset_id"],
        name=raw["name"],
        domain=_optional_text(raw.get("domain")),
        supported_questions=_string_list(raw.get("supported_questions")),  # 列表字段统一归一，缺失时为空列表。
        key_metrics=_string_list(raw.get("key_metrics")),
        key_dimensions=_string_list(raw.get("key_dimensions")),
        freshness=_optional_text(raw.get("freshness")),
        availability=_optional_text(raw.get("availability")),
    )
