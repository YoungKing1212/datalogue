# ============================================================
# File Name   : bi_worker_runtime.py
# Description:
#   BI Worker Query Plan 的 L5 受控查询 Runtime。
#
# Responsibilities:
#   - 在执行前强制通过 L4 Query Support Validator，缺上下文时不触发查询。
#   - 复用 AgentScope Dataset bridge 和 BI atomic toolkit 执行受控查询。
#   - 把执行异常转换成安全 Repair Request，避免 SQL、raw rows 或数据库错误进入 Agent Team。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.bi_agent.runtime_context import build_bi_runtime_context
from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
    BIWorkerQueryResult,
    RepairRequest,
)
from app.agentscope_service.bi_worker_validator import (
    BIWorkerQueryValidator,
    ProgressiveContextState,
)
from app.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.bi.toolkit import build_bi_atomic_toolkit


class BIWorkerQueryRuntime:
    """BI Worker L5 Runtime：只执行已被 L4 渐进式上下文支持的查询计划。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.validator = BIWorkerQueryValidator()

    async def execute_query_plan(
        self,
        dataset_id: int,
        confirmed_question: str,
        query_plan: BIWorkerQueryPlan,
        context_state: ProgressiveContextState,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        validation = self.validator.validate(query_plan, context_state)
        if validation.support_status != "supported":
            # L4 未确认支持时必须停在安全校验 payload，避免 Runtime 读取私有数据。
            return validation.model_dump()

        try:
            result = await self._execute_supported_plan(
                dataset_id=dataset_id,
                confirmed_question=confirmed_question,
                query_plan=query_plan,
                trace_id=trace_id,
            )
        except Exception as exc:
            return self._safe_repair_request(exc, failure_stage="execute").model_dump()
        return result.to_tool_payload()

    async def _execute_supported_plan(
        self,
        *,
        dataset_id: int,
        confirmed_question: str,
        query_plan: BIWorkerQueryPlan,
        trace_id: str | None,
    ) -> BIWorkerQueryResult:
        toolkit = build_bi_atomic_toolkit(self.db)
        bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
        runtime_context = build_bi_runtime_context(
            self.db,
            dataset_id=dataset_id,
            question=confirmed_question,
            bridge=bridge,
        )
        session = bridge.start_session(
            dataset_id=dataset_id,
            question=confirmed_question,
            agent_name="bi_worker",
            trace_id=trace_id,
            **(runtime_context.get("session_kwargs") or {}),
        )
        # QueryPlan 只以安全业务引用进入 bridge；SQL/schema/raw rows 继续由私有 session 和工具链托管。
        dsl = self._query_plan_to_legacy_query_plan(query_plan)
        result = await bridge.run_direct_query(session=session, dsl=dsl)
        artifact_ref = _optional_str(result.get("artifact_ref"))
        checkpoint_ref = _optional_str(result.get("checkpoint_ref"))
        row_count = _optional_int(result.get("row_count"))
        column_count = _optional_int(result.get("column_count"))
        return BIWorkerQueryResult(
            answer_summary=_answer_summary(
                status=_optional_str(result.get("status")),
                artifact_ref=artifact_ref,
                row_count=row_count,
                column_count=column_count,
            ),
            artifact_ref=artifact_ref,
            checkpoint_ref=checkpoint_ref,
            row_count=row_count,
            column_count=column_count,
        )

    def _query_plan_to_legacy_query_plan(self, query_plan: BIWorkerQueryPlan) -> dict[str, Any]:
        selected_assets = [
            {
                "asset_type": "field",
                "asset_id": item.target.asset_ref,
                "name": item.target.field,
                "display_name": item.display_name,
                "source": "bi_worker_query_plan",
                "confidence": 0.9,
                "usage": "selected",
            }
            for item in query_plan.selects
        ]
        return {
            "query_type": query_plan.intent,
            "execution_strategy": "query_graph",
            "confidence": 0.9,
            "selected_assets": selected_assets,
            "reference_assets": [],
            "rejected_assets": [],
            "required_inputs": [],
            "planner_source": "bi_worker_query_plan",
            "execution_source": "bi_worker_query_runtime",
            "explanation": {
                "summary": "BI Worker 已基于渐进式上下文生成受控查询计划。",
                "assumptions": list(query_plan.assumptions),
            },
        }

    def _safe_repair_request(
        self,
        exc: Exception,
        *,
        failure_stage: str,
    ) -> RepairRequest:
        del exc
        return RepairRequest(
            repair_status="needs_plan_revision",
            failure_stage=failure_stage,
            failure_class="controlled_query_runtime_error",
            safe_reason="受控查询执行失败，需要调整查询计划或补充上下文后重试。",
            recommended_action="重新生成查询计划，并仅使用已确认的资产、字段和关系引用。",
            missing_context=[],
        )


def _answer_summary(
    *,
    status: str | None,
    artifact_ref: str | None,
    row_count: int | None,
    column_count: int | None,
) -> str:
    if status != "completed" or not artifact_ref:
        return "查询未完成，未生成可展示结果。"
    return f"查询已完成，结果已生成 artifact_ref={artifact_ref}，共 {row_count or 0} 行、{column_count or 0} 列。"


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
