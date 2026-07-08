# ============================================================
# File Name   : bi_worker_validator.py
# Description:
#   BI Worker Query Plan 的 L4 渐进式上下文支持度校验器。
#
# Responsibilities:
#   - 基于已加载的资产、关系、字段和 lookup 依赖判断 Query Plan 是否可安全执行。
#   - 对缺失上下文返回安全 ref 级别的补充建议，避免暴露 SQL、原始行或数据库错误。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Iterator

from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
    FieldTarget,
    QuerySupportValidation,
)


MAX_MORE_CONTEXT_ROUNDS = 2


@dataclass
class ProgressiveContextState:
    """记录 BI Worker 渐进式上下文已覆盖的安全引用集合。"""

    asset_refs: set[str] = field(default_factory=set)
    relationship_refs: set[str] = field(default_factory=set)
    field_refs: set[str] = field(default_factory=set)
    lookup_dependencies: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_context_history: list[str] = field(default_factory=list)
    l2_request_count: int = 0
    l3_profile_count: int = 0
    validation_more_context_count: int = 0
    suggested_filters: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def field_names(cls) -> set[str]:
        """返回所有已知字段名，供 tools 层过滤未知 key 时使用。"""
        return {f.name for f in fields(cls)}


class BIWorkerQueryValidator:
    """校验 Query Plan 是否被当前渐进式上下文支持。"""

    def validate(
        self,
        plan: BIWorkerQueryPlan,
        context_state: ProgressiveContextState,
    ) -> QuerySupportValidation:
        missing_context = self._collect_missing_context(plan, context_state)
        if not missing_context:
            return QuerySupportValidation(
                support_status="supported",
                safe_reason="当前上下文已覆盖查询所需资产、关系、字段和解码依赖。",
            )

        repeated_or_limited = self._should_stop_auto_expansion(missing_context, context_state)
        if repeated_or_limited:
            return QuerySupportValidation(
                support_status="needs_clarification",
                safe_reason="缺失上下文已重复或达到自动补充上限，需要用户澄清查询范围。",
                missing_context=missing_context,
            )

        next_tool = self._recommended_tool(missing_context[0])
        return QuerySupportValidation(
            support_status="needs_more_context",
            safe_reason="当前上下文不足，需要补充安全元数据后再执行查询。",
            missing_context=missing_context,
            auto_context_expansions=[
                {
                    "type": item["type"],
                    "ref": item["ref"],
                    "recommended_next_tool": item["recommended_next_tool"],
                    "focus": item["focus"],
                }
                for item in missing_context
            ],
            recommended_next_tool=next_tool,
        )

    def _collect_missing_context(
        self,
        plan: BIWorkerQueryPlan,
        context_state: ProgressiveContextState,
    ) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for asset_ref in self._entity_asset_refs(plan):
            if asset_ref not in context_state.asset_refs:
                self._append_missing(missing, seen, "missing_asset", asset_ref)

        for join in plan.join_requirements:
            if join.relationship_ref not in context_state.relationship_refs:
                self._append_missing(missing, seen, "missing_relationship", join.relationship_ref)

        for target in self._all_targets(plan):
            # 优先规范化字段级 ref 命中;若 LLM 传表级 ref + field 分离,能拼出字段级 ref 命中。
            # 兼容 target.asset_ref 已是字段级或直接命中资产集合的情况。
            normalized = target.normalized_field_ref
            if (
                normalized not in context_state.field_refs
                and target.asset_ref not in context_state.field_refs
                and target.asset_ref not in context_state.asset_refs
            ):
                self._append_missing(missing, seen, "missing_field", target.asset_ref)

        for select in plan.selects:
            # display_semantic 只是展示层业务含义，不代表字段需要字典/枚举解码；
            # 只有明确 requires_decoding=true 时才强制要求 lookup dependency。
            if (
                select.requires_decoding
                and select.target.asset_ref not in context_state.lookup_dependencies
            ):
                self._append_missing(missing, seen, "lookup_dependency", select.target.asset_ref)

        return missing

    def _append_missing(
        self,
        missing: list[dict[str, Any]],
        seen: set[tuple[str, str]],
        missing_type: str,
        ref: str,
    ) -> None:
        key = (missing_type, ref)
        if key in seen:
            return
        seen.add(key)
        missing.append(
            {
                "type": missing_type,
                "ref": ref,
                "recommended_next_tool": self._recommended_tool({"type": missing_type}),
                "focus": self._focus_for_type(missing_type),
            }
        )

    def _should_stop_auto_expansion(
        self,
        missing_context: list[dict[str, Any]],
        context_state: ProgressiveContextState,
    ) -> bool:
        if context_state.validation_more_context_count >= MAX_MORE_CONTEXT_ROUNDS:
            return True

        missing_signatures = {f"{item['type']}:{item['ref']}" for item in missing_context}
        return any(
            signature in context_state.missing_context_history for signature in missing_signatures
        )

    def _recommended_tool(self, missing_item: dict[str, Any]) -> str:
        if missing_item["type"] == "lookup_dependency":
            return "datalogue_request_schema_slice"
        return "datalogue_request_schema_slice"

    def _focus_for_type(self, missing_type: str) -> str:
        return {
            "missing_asset": "asset",
            "missing_relationship": "relationship",
            "missing_field": "field",
            "lookup_dependency": "lookup_dependency",
        }[missing_type]

    def _entity_asset_refs(self, plan: BIWorkerQueryPlan) -> Iterator[str]:
        yield plan.data_graph.primary_entity.asset_ref
        for entity in plan.data_graph.supporting_entities:
            yield entity.asset_ref

    def _all_targets(self, plan: BIWorkerQueryPlan) -> Iterator[FieldTarget]:
        for item in plan.filters:
            yield item.target
        for item in plan.selects:
            yield item.target
        for item in plan.metrics:
            yield item.target
        yield from plan.group_by
        for item in plan.ordering:
            yield item.target
