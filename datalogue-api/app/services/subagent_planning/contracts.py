# ============================================================
# File Name   : contracts.py
# Description:
#   DatasetSubAgent 查询规划的数据契约。
#
# Responsibilities:
#   - 定义候选资产、查询计划、流式事件和最终结果结构。
#   - 提供 JSON 安全序列化和查询计划枚举校验。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder

CandidateAssetType = Literal["blueprint", "metric", "dimension", "term", "field", "table"]
QueryType = Literal[
    "detail_query",
    "metric_query",
    "blueprint_query",
    "knowledge_qa",
    "ambiguous",
    "unsupported",
]
ExecutionStrategy = Literal[
    "blueprint_execute",
    "blueprint_as_reference",
    "query_graph",
    "clarify",
    "reject",
]
AssetUsage = Literal["selected", "reference", "rejected", "candidate"]
PlannerSource = Literal["llm", "fallback", "rules"]

CANDIDATE_ASSET_TYPES = {"blueprint", "metric", "dimension", "term", "field", "table"}
QUERY_TYPES = {
    "detail_query",
    "metric_query",
    "blueprint_query",
    "knowledge_qa",
    "ambiguous",
    "unsupported",
}
EXECUTION_STRATEGIES = {
    "blueprint_execute",
    "blueprint_as_reference",
    "query_graph",
    "clarify",
    "reject",
}
ASSET_USAGES = {"selected", "reference", "rejected", "candidate"}
PLANNER_SOURCES = {"llm", "fallback", "rules"}


class QueryPlanValidationError(ValueError):
    """查询计划结构不合法时抛出，调用方应进入规则 fallback。"""


@dataclass
class CandidateAsset:
    asset_type: str
    asset_id: str | int
    name: str
    display_name: str | None
    source: str
    confidence: float
    match_signals: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: str = "candidate"
    match_reason: str | None = None
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return jsonable_encoder(
            {
                "asset_type": self.asset_type,
                "asset_id": self.asset_id,
                "name": self.name,
                "display_name": self.display_name,
                "source": self.source,
                "confidence": round(float(self.confidence), 4),
                "match_signals": self.match_signals,
                "metadata": self.metadata,
                "usage": self.usage,
                "match_reason": self.match_reason,
                "reject_reason": self.reject_reason,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateAsset":
        asset_type = str(payload.get("asset_type") or "")
        usage = str(payload.get("usage") or "candidate")
        if asset_type not in CANDIDATE_ASSET_TYPES:
            raise QueryPlanValidationError(f"asset_type invalid: {asset_type}")
        if usage not in ASSET_USAGES:
            raise QueryPlanValidationError(f"asset usage invalid: {usage}")
        return cls(
            asset_type=asset_type,
            asset_id=payload.get("asset_id") or payload.get("id") or "",
            name=str(payload.get("name") or ""),
            display_name=payload.get("display_name"),
            source=str(payload.get("source") or ""),
            confidence=float(payload.get("confidence") or 0),
            match_signals=list(payload.get("match_signals") or []),
            metadata=dict(payload.get("metadata") or {}),
            usage=usage,
            match_reason=payload.get("match_reason"),
            reject_reason=payload.get("reject_reason"),
        )


@dataclass
class QueryPlan:
    query_type: str
    execution_strategy: str
    confidence: float
    selected_assets: list[CandidateAsset] = field(default_factory=list)
    reference_assets: list[CandidateAsset] = field(default_factory=list)
    rejected_assets: list[CandidateAsset] = field(default_factory=list)
    required_inputs: list[dict[str, Any]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    fallback_reason: str | None = None
    planner_source: str = "rules"
    explanation: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.query_type not in QUERY_TYPES:
            raise QueryPlanValidationError(f"query_type invalid: {self.query_type}")
        if self.execution_strategy not in EXECUTION_STRATEGIES:
            raise QueryPlanValidationError(f"execution_strategy invalid: {self.execution_strategy}")
        if self.planner_source not in PLANNER_SOURCES:
            raise QueryPlanValidationError(f"planner_source invalid: {self.planner_source}")

    def to_dict(self) -> dict[str, Any]:
        return jsonable_encoder(
            {
                "query_type": self.query_type,
                "execution_strategy": self.execution_strategy,
                "confidence": round(float(self.confidence), 4),
                "selected_assets": [asset.to_dict() for asset in self.selected_assets],
                "reference_assets": [asset.to_dict() for asset in self.reference_assets],
                "rejected_assets": [asset.to_dict() for asset in self.rejected_assets],
                "required_inputs": self.required_inputs,
                "clarification": self.clarification,
                "fallback_reason": self.fallback_reason,
                "planner_source": self.planner_source,
                "explanation": self.explanation,
                "debug": self.debug,
            }
        )


@dataclass
class SubAgentEvent:
    event_type: str
    payload: dict[str, Any]

    def to_sse_payload(self) -> dict[str, Any]:
        return jsonable_encoder({**self.payload, "type": self.event_type})


@dataclass
class SubAgentResult:
    final_state: dict[str, Any]
    query_plan: QueryPlan
    candidate_assets: dict[str, Any]
    step_traces: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return jsonable_encoder(
            {
                "final_state": self.final_state,
                "query_plan": self.query_plan.to_dict(),
                "candidate_assets": self.candidate_assets,
                "step_traces": self.step_traces,
            }
        )


def _asset_payload_items(items: Any, usage: str) -> list[Any]:
    if items is None:
        return []
    if isinstance(items, dict):
        if "assets" not in items:
            raise QueryPlanValidationError(f"{usage} assets wrapper must include assets")
        wrapped = items.get("assets")
        if not isinstance(wrapped, list):
            raise QueryPlanValidationError(f"{usage} assets must be list")
        return wrapped
    if isinstance(items, list):
        return items
    raise QueryPlanValidationError(f"{usage} assets must be list")


def _assets_from_payload(items: Any, usage: str) -> list[CandidateAsset]:
    assets: list[CandidateAsset] = []
    for item in _asset_payload_items(items, usage):
        if not isinstance(item, dict):
            raise QueryPlanValidationError(f"{usage} asset must be object")
        normalized = dict(item)
        normalized["usage"] = normalized.get("usage") or usage
        assets.append(CandidateAsset.from_dict(normalized))
    return assets


def _required_inputs_from_payload(items: Any) -> list[dict[str, Any]]:
    if items in (None, "", []):
        return []
    if isinstance(items, list):
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                raise QueryPlanValidationError("required_inputs item must be object")
            normalized.append(dict(item))
        return normalized
    if isinstance(items, dict):
        normalized = []
        for name, spec in items.items():
            if isinstance(spec, dict):
                item = dict(spec)
            elif isinstance(spec, bool):
                item = {"required": spec}
            else:
                raise QueryPlanValidationError("required_inputs dict value must be object")
            item.setdefault("name", str(name))
            normalized.append(item)
        return normalized
    raise QueryPlanValidationError("required_inputs must be list[object] or object map")


def normalize_query_plan(payload: dict[str, Any]) -> QueryPlan:
    query_type = str(payload.get("query_type") or "")
    execution_strategy = str(payload.get("execution_strategy") or "")
    planner_source = str(payload.get("planner_source") or "rules")
    if query_type not in QUERY_TYPES:
        raise QueryPlanValidationError(f"query_type invalid: {query_type}")
    if execution_strategy not in EXECUTION_STRATEGIES:
        raise QueryPlanValidationError(f"execution_strategy invalid: {execution_strategy}")
    if planner_source not in PLANNER_SOURCES:
        raise QueryPlanValidationError(f"planner_source invalid: {planner_source}")
    return QueryPlan(
        query_type=query_type,
        execution_strategy=execution_strategy,
        confidence=float(payload.get("confidence") or 0),
        selected_assets=_assets_from_payload(payload.get("selected_assets"), "selected"),
        reference_assets=_assets_from_payload(payload.get("reference_assets"), "reference"),
        rejected_assets=_assets_from_payload(payload.get("rejected_assets"), "rejected"),
        required_inputs=_required_inputs_from_payload(payload.get("required_inputs")),
        clarification=payload.get("clarification") if isinstance(payload.get("clarification"), dict) else None,
        fallback_reason=payload.get("fallback_reason"),
        planner_source=planner_source,
        explanation=dict(payload.get("explanation") or {}),
        debug=dict(payload.get("debug") or {}),
    )
