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
from app.services.subagent_planning.sql_context import build_sql_generation_context

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
        self.max_rounds = min(3, max(1, max_rounds))
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
                return self._build_result(
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
                return self._build_result(
                    query_plan=plan,
                    lightweight_catalog=lightweight_catalog,
                    asset_details=asset_details,
                    attempted_detail_requests=attempted_detail_requests,
                    warnings=warnings,
                    detail_rounds=detail_rounds,
                )

            if len(requests) > self.max_requests_per_round:
                warnings.append(
                    self._request_limit_warning(
                        requested_count=len(requests),
                        sampled_requests=[
                            request.to_dict()
                            for request in requests[: self.max_requests_per_round]
                        ],
                    )
                )
            scoped_requests = requests[: self.max_requests_per_round]
            attempted_detail_requests.extend(request.to_dict() for request in scoped_requests)
            validation = validate_asset_detail_requests(
                scoped_requests,
                allowed_scope=allowed_scope,
                max_requests=self.max_requests_per_round,
            )
            warnings.extend(
                self._warning_from_validation_error(error.to_dict())
                for error in validation.errors
            )
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
        return self._build_result(
            query_plan=plan,
            lightweight_catalog=lightweight_catalog,
            asset_details=asset_details,
            attempted_detail_requests=attempted_detail_requests,
            warnings=warnings,
            detail_rounds=detail_rounds,
        )

    def _build_result(
        self,
        *,
        query_plan: QueryPlan,
        lightweight_catalog: dict[str, Any],
        asset_details: list[AssetDetailResult],
        attempted_detail_requests: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        detail_rounds: int,
    ) -> PlannerLoopResult:
        return PlannerLoopResult(
            query_plan=query_plan,
            lightweight_catalog=lightweight_catalog,
            asset_details=asset_details,
            attempted_detail_requests=attempted_detail_requests,
            warnings=warnings,
            detail_rounds=detail_rounds,
            sql_generation_context=build_sql_generation_context(
                query_plan=query_plan,
                asset_details=asset_details,
                lightweight_catalog=lightweight_catalog,
            ),
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

    def _request_limit_warning(
        self,
        *,
        requested_count: int,
        sampled_requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "code": "asset_detail_request_limit_exceeded",
            "error_code": "asset_detail_request_limit_exceeded",
            "message": (
                f"资产详情请求数量超过单轮上限 {self.max_requests_per_round}，"
                f"仅保留前 {self.max_requests_per_round} 个请求。"
            ),
            "request": {"sampled_requests": sampled_requests},
            "requested_count": requested_count,
            "max_requests": self.max_requests_per_round,
        }

    def _warning_from_validation_error(self, warning: dict[str, Any]) -> dict[str, Any]:
        code = str(warning.get("code") or warning.get("error_code") or "asset_detail_warning")
        return {
            **warning,
            "code": code,
            "error_code": code,
            "message": str(warning.get("message") or ""),
            "request": warning.get("request") if isinstance(warning.get("request"), dict) else {},
        }

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
        plan.planner_warnings = [
            *(plan.planner_warnings or []),
            *[self._planner_warning_from_detail_warning(warning) for warning in warnings],
        ]

        risk_flags = set(plan.risk_flags or [])
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            code = warning.get("code") or warning.get("error_code")
            if code:
                risk_flags.add(str(code))
        for detail in asset_details:
            risk_flags.update(str(flag) for flag in detail.risk_flags)
        plan.risk_flags = sorted(risk_flags)

    def _planner_warning_from_detail_warning(self, warning: dict[str, Any]) -> dict[str, Any]:
        normalized = self._warning_from_validation_error(warning)
        return {
            "code": normalized["code"],
            "message": normalized["message"],
            "request": normalized["request"],
            **{
                key: value
                for key, value in normalized.items()
                if key not in {"code", "error_code", "message", "request"}
            },
        }
