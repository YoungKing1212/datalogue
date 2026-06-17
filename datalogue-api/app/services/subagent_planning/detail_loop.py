# ============================================================
# File Name   : detail_loop.py
# Description:
#   SubAgent Planner 资产详情请求循环服务。
#
# Responsibilities:
#   - 在轻量资产目录和可访问资产范围内驱动 planner 逐轮请求详情。
#   - 校验并补全 planner 请求的资产详情，避免越界访问未召回资产。
#   - 将详情循环审计摘要写入 QueryPlan，不把完整资产详情塞进计划。
#
# Author      : yangkai
# Created On  : 2026-06-18
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.subagent_planning.asset_catalog import (
    build_allowed_asset_scope,
    project_lightweight_asset_catalog,
)
from app.services.subagent_planning.asset_detail import (
    AssetDetailResult,
    AssetDetailService,
    validate_asset_detail_requests,
)
from app.services.subagent_planning.contracts import QueryPlan
from app.services.subagent_planning.planner import parse_asset_detail_requests

PlannerCall = Callable[..., QueryPlan | dict[str, Any]]


@dataclass
class PlannerLoopResult:
    query_plan: QueryPlan
    lightweight_catalog: dict[str, Any]
    asset_details: list[AssetDetailResult] = field(default_factory=list)
    attempted_detail_requests: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    detail_rounds: int = 0
    sql_generation_context: dict[str, Any] = field(default_factory=dict)


class PlannerDetailLoop:
    def __init__(
        self,
        *,
        max_rounds: int = 3,
        max_requests_per_round: int = 5,
        planner_call: PlannerCall,
        detail_service: Any = None,
    ) -> None:
        self.max_rounds = max(1, max_rounds)
        self.max_requests_per_round = max(1, max_requests_per_round)
        self.planner_call = planner_call
        self.detail_service = detail_service

    def run(
        self,
        *,
        db: Any,
        question: str,
        routing: Any,
        candidate_assets: dict[str, Any] | None,
        multiturn_context: Any = None,
        lead_agent_context: Any = None,
    ) -> PlannerLoopResult:
        lightweight_catalog = project_lightweight_asset_catalog(candidate_assets)
        allowed_scope = build_allowed_asset_scope(lightweight_catalog)
        detail_service = self.detail_service or AssetDetailService(candidate_assets=candidate_assets)
        asset_details: list[AssetDetailResult] = []
        attempted_detail_requests: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        detail_rounds = 0

        for _ in range(1, self.max_rounds + 1):
            response = self.planner_call(
                db=db,
                question=question,
                routing=routing,
                lightweight_catalog=lightweight_catalog,
                asset_details=[detail.to_dict() for detail in asset_details],
                previous_detail_requests=list(attempted_detail_requests),
                warnings=list(warnings),
                multiturn_context=multiturn_context,
                lead_agent_context=lead_agent_context,
            )
            if isinstance(response, QueryPlan):
                self._attach_detail_audit(
                    response,
                    detail_rounds=detail_rounds,
                    attempted_detail_requests=attempted_detail_requests,
                    asset_details=asset_details,
                    warnings=warnings,
                )
                return PlannerLoopResult(
                    query_plan=response,
                    lightweight_catalog=lightweight_catalog,
                    asset_details=asset_details,
                    attempted_detail_requests=attempted_detail_requests,
                    warnings=warnings,
                    detail_rounds=detail_rounds,
                )

            requests = parse_asset_detail_requests(response)
            if not requests:
                plan = self._invalid_response_plan()
                self._attach_detail_audit(
                    plan,
                    detail_rounds=detail_rounds,
                    attempted_detail_requests=attempted_detail_requests,
                    asset_details=asset_details,
                    warnings=warnings,
                )
                return PlannerLoopResult(
                    query_plan=plan,
                    lightweight_catalog=lightweight_catalog,
                    asset_details=asset_details,
                    attempted_detail_requests=attempted_detail_requests,
                    warnings=warnings,
                    detail_rounds=detail_rounds,
                )

            attempted_detail_requests.extend(request.to_dict() for request in requests)
            validation = validate_asset_detail_requests(
                requests,
                allowed_scope=allowed_scope,
                max_requests=self.max_requests_per_round,
            )
            warnings.extend(error.to_dict() for error in validation.errors)
            for request in validation.valid_requests:
                asset_details.append(detail_service.get_detail(request))
            detail_rounds += 1

        plan = QueryPlan(
            query_type="unsupported",
            execution_strategy="reject",
            confidence=0.0,
            fallback_reason="max_detail_rounds_exceeded",
            planner_source="fallback",
            explanation={"summary": "资产详情请求轮次已达到上限，未形成可执行计划。"},
            missing_context=["资产详情循环未收敛"],
            why_not_generate_sql=f"达到 {self.max_rounds} 轮资产详情请求后仍未形成可执行计划。",
            risk_flags=["max_detail_rounds_exceeded"],
        )
        self._attach_detail_audit(
            plan,
            detail_rounds=detail_rounds,
            attempted_detail_requests=attempted_detail_requests,
            asset_details=asset_details,
            warnings=warnings,
        )
        return PlannerLoopResult(
            query_plan=plan,
            lightweight_catalog=lightweight_catalog,
            asset_details=asset_details,
            attempted_detail_requests=attempted_detail_requests,
            warnings=warnings,
            detail_rounds=detail_rounds,
        )

    def _invalid_response_plan(self) -> QueryPlan:
        return QueryPlan(
            query_type="unsupported",
            execution_strategy="reject",
            confidence=0.0,
            fallback_reason="planner_detail_loop_invalid_response",
            planner_source="fallback",
            explanation={"summary": "规划器没有返回可执行计划或合法资产详情请求。"},
            missing_context=["缺少合法资产详情请求"],
            why_not_generate_sql="规划器未返回可执行计划或可补全的资产详情请求。",
            risk_flags=["planner_detail_loop_invalid_response"],
        )

    def _attach_detail_audit(
        self,
        plan: QueryPlan,
        *,
        detail_rounds: int,
        attempted_detail_requests: list[dict[str, Any]],
        asset_details: list[AssetDetailResult],
        warnings: list[dict[str, Any]],
    ) -> None:
        plan.detail_rounds = detail_rounds
        plan.attempted_detail_requests = list(attempted_detail_requests)
        plan.asset_detail_coverage = {
            str(detail.request.asset_id): detail.coverage for detail in asset_details
        }

        risk_flags = set(plan.risk_flags or [])
        for warning in warnings:
            error_code = warning.get("error_code") if isinstance(warning, dict) else None
            if error_code:
                risk_flags.add(str(error_code))
        for detail in asset_details:
            risk_flags.update(str(flag) for flag in detail.risk_flags)
        plan.risk_flags = sorted(risk_flags)
