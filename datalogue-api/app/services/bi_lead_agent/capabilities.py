# ============================================================
# File Name   : capabilities.py
# Description:
#   BI LeadAgent K1 能力清单与数据集能力摘要清洗服务。
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

from app.schemas.bi_lead_agent import BILeadAgentCapability, DatasetCapabilitySummary


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values: Iterable[Any]
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, Mapping):
        values = value
    else:
        values = [value]

    items: list[str] = []
    for item in values:
        text = _optional_text(item)
        if text is None:
            continue
        items.append(text)
    return items


def build_bi_lead_agent_capabilities() -> list[BILeadAgentCapability]:
    """返回 K1 阶段 LeadAgent 允许暴露的工具面；DatasetAgent 原子工具不得进入该清单。"""

    return [
        BILeadAgentCapability(name="list_dataset_capabilities", status="enabled"),
        BILeadAgentCapability(name="request_dataset_confirmation", status="enabled"),
        BILeadAgentCapability(name="query_dataset", status="enabled"),
        BILeadAgentCapability(
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
