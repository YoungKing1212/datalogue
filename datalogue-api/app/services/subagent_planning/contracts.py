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

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)

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
PlannerSource = Literal["deterministic", "template", "llm", "fallback"]

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
PLANNER_SOURCES = {"deterministic", "template", "llm", "fallback"}


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
        asset_type = str(payload.get("asset_type") or "")  # 资产来自召回/LLM，错误需保留定位信息。
        usage = str(payload.get("usage") or "candidate")
        if asset_type not in CANDIDATE_ASSET_TYPES:
            raise QueryPlanValidationError(
                f"asset_type invalid: '{asset_type}' (valid: {sorted(CANDIDATE_ASSET_TYPES)}), "
                f"asset_id={payload.get('asset_id')}, name={payload.get('name')}"
            )
        if usage not in ASSET_USAGES:
            raise QueryPlanValidationError(
                f"asset usage invalid: '{usage}' (valid: {sorted(ASSET_USAGES)}), "
                f"asset_type={asset_type}, asset_id={payload.get('asset_id')}"
            )
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
    planner_source: str = "deterministic"
    explanation: dict[str, Any] = field(default_factory=dict)
    decision_factors: list[dict[str, Any]] = field(default_factory=list)
    planner_warnings: list[dict[str, Any]] = field(default_factory=list)
    governance_suggestions: list[dict[str, Any]] = field(default_factory=list)
    detail_rounds: int = 0
    attempted_detail_requests: list[dict[str, Any]] = field(default_factory=list)
    asset_detail_coverage: dict[str, Any] = field(default_factory=dict)
    missing_context: list[str] = field(default_factory=list)
    why_not_generate_sql: str | None = None
    risk_flags: list[str] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.query_type not in QUERY_TYPES:  # 非法枚举必须 fail-fast，让调用方进入 fallback。
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
                "decision_factors": self.decision_factors,
                "planner_warnings": self.planner_warnings,
                "governance_suggestions": self.governance_suggestions,
                "detail_rounds": self.detail_rounds,
                "attempted_detail_requests": self.attempted_detail_requests,
                "asset_detail_coverage": self.asset_detail_coverage,
                "missing_context": self.missing_context,
                "why_not_generate_sql": self.why_not_generate_sql,
                "risk_flags": self.risk_flags,
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


def _dict_list_from_payload(items: Any, field_name: str) -> list[dict[str, Any]]:
    if items in (None, "", []):
        return []
    if not isinstance(items, list):
        raise QueryPlanValidationError(f"{field_name} must be list[object]")
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise QueryPlanValidationError(f"{field_name} item must be object")
        normalized.append(dict(item))
    return normalized


def _int_from_payload(value: Any, field_name: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise QueryPlanValidationError(f"{field_name} must be int")
    if isinstance(value, int):
        return value
    raise QueryPlanValidationError(f"{field_name} must be int")


def _strict_dict_list_from_payload(items: Any, field_name: str) -> list[dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise QueryPlanValidationError(f"{field_name} must be list[object]")
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise QueryPlanValidationError(f"{field_name} item must be object")
        normalized.append(dict(item))
    return normalized


def _dict_from_payload(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise QueryPlanValidationError(f"{field_name} must be object")
    return dict(value)


def _string_list_from_payload(items: Any, field_name: str) -> list[str]:
    if items is None:
        return []
    if isinstance(items, str) or not isinstance(items, list):
        raise QueryPlanValidationError(f"{field_name} must be list[string]")
    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise QueryPlanValidationError(f"{field_name} item must be string")
        normalized.append(item)
    return normalized


def _optional_string_from_payload(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise QueryPlanValidationError(f"{field_name} must be string")


def normalize_query_plan(payload: dict[str, Any]) -> QueryPlan:
    query_type = str(payload.get("query_type") or "")  # LLM JSON 先校验顶层枚举，再逐字段归一化。
    execution_strategy = str(payload.get("execution_strategy") or "")
    planner_source = str(payload.get("planner_source") or "deterministic")
    if query_type not in QUERY_TYPES:
        raise QueryPlanValidationError(f"query_type invalid: {query_type}")
    if execution_strategy not in EXECUTION_STRATEGIES:
        raise QueryPlanValidationError(f"execution_strategy invalid: {execution_strategy}")
    if planner_source not in PLANNER_SOURCES:
        raise QueryPlanValidationError(f"planner_source invalid: {planner_source}")

    def _field(field_name: str, fn, *args):
        """包装字段提取，在校验失败时附加上下文字段名，方便排查。"""
        try:
            return fn(*args)
        except QueryPlanValidationError as e:
            raise QueryPlanValidationError(
                f"Field '{field_name}' validation failed: {e}"
            ) from e

    return QueryPlan(
        query_type=query_type,
        execution_strategy=execution_strategy,
        confidence=float(payload.get("confidence") or 0),
        selected_assets=_field(
            "selected_assets",
            _assets_from_payload, payload.get("selected_assets"), "selected",
        ),
        reference_assets=_field(
            "reference_assets",
            _assets_from_payload, payload.get("reference_assets"), "reference",
        ),
        rejected_assets=_field(
            "rejected_assets",
            _assets_from_payload, payload.get("rejected_assets"), "rejected",
        ),
        required_inputs=_field(
            "required_inputs",
            _required_inputs_from_payload, payload.get("required_inputs"),
        ),
        clarification=payload.get("clarification") if isinstance(payload.get("clarification"), dict) else None,
        fallback_reason=payload.get("fallback_reason"),
        planner_source=planner_source,
        explanation=dict(payload.get("explanation") or {}),
        decision_factors=_field(
            "decision_factors",
            _dict_list_from_payload, payload.get("decision_factors"), "decision_factors",
        ),
        planner_warnings=_field(
            "planner_warnings",
            _dict_list_from_payload, payload.get("planner_warnings"), "planner_warnings",
        ),
        governance_suggestions=_field(
            "governance_suggestions",
            _dict_list_from_payload, payload.get("governance_suggestions"), "governance_suggestions",
        ),
        detail_rounds=_field(
            "detail_rounds",
            _int_from_payload, payload.get("detail_rounds"), "detail_rounds",
        ),
        attempted_detail_requests=_field(
            "attempted_detail_requests",
            _strict_dict_list_from_payload, payload.get("attempted_detail_requests"), "attempted_detail_requests",
        ),
        asset_detail_coverage=_field(
            "asset_detail_coverage",
            _dict_from_payload, payload.get("asset_detail_coverage"), "asset_detail_coverage",
        ),
        missing_context=_field(
            "missing_context",
            _string_list_from_payload, payload.get("missing_context"), "missing_context",
        ),
        why_not_generate_sql=_field(
            "why_not_generate_sql",
            _optional_string_from_payload, payload.get("why_not_generate_sql"), "why_not_generate_sql",
        ),
        risk_flags=_field(
            "risk_flags",
            _string_list_from_payload, payload.get("risk_flags"), "risk_flags",
        ),
        debug=dict(payload.get("debug") or {}),
    )
