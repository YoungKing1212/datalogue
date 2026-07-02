# ============================================================
# File Name   : native_handoff.py
# Description:
#   BI LeadAgent AgentScope native handoff 实现。
#
# Responsibilities:
#   - 以 AgentScope 2.0 DatasetAgent 子运行为内部 handoff 实现。
#   - 将 native child-run 事件投影成 Datalogue BILeadAgentHandoffResult 安全契约。
#   - 保持 Datalogue DB 为 run/confirmation/handoff 的业务状态真相源。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest, BILeadAgentHandoffResult
from app.services.agentscope_dataset_runtime import AgentScopeDatasetRuntimeBridge
from app.services.bi_lead_agent.dataset_agent_factory import AgentScopeDatasetAgentFactory
from app.services.bi_lead_agent.handoff_events import (
    collect_native_handoff_payload,
    native_status_or_default,
    safe_native_failure_result_payload,
)
from app.services.bi_tools import build_bi_atomic_toolkit


logger = logging.getLogger(__name__)


def _new_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class AgentScopeNativeBIHandoff:
    """AgentScope native handoff port；内部使用子 DatasetAgent run，外部只返回 D2 安全结果。"""

    def __init__(
        self,
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        dataset_agent_factory: AgentScopeDatasetAgentFactory,
    ) -> None:
        self.bridge = bridge
        self.dataset_agent_factory = dataset_agent_factory

    @classmethod
    def from_db(cls, db: Session) -> "AgentScopeNativeBIHandoff":
        toolkit = build_bi_atomic_toolkit(db)
        return cls(
            bridge=AgentScopeDatasetRuntimeBridge(toolkit=toolkit),
            dataset_agent_factory=AgentScopeDatasetAgentFactory(db),
        )

    async def query_dataset(
        self,
        request: BILeadAgentHandoffRequest,
        *,
        task_id: str | None,
    ) -> BILeadAgentHandoffResult:
        handoff_id = _new_prefixed_id("native-handoff")
        child_run_id = _new_prefixed_id("dataset-native-run")
        session = self.bridge.start_session(
            dataset_id=request.dataset_id,
            question=request.confirmed_question,
            agent_name="bi_lead_agent",
            trace_id=request.trace_id,
        )  # AgentScope session 是执行态；Datalogue handoff 表仍是业务审计真相源。

        try:
            agent = self.dataset_agent_factory.create(session)
            events = await self.bridge.run_reply_stream(
                agent,
                msg=self._build_native_child_message(
                    request=request,
                    handoff_id=handoff_id,
                    child_run_id=child_run_id,
                ),
                session=session,
            )
            payload = collect_native_handoff_payload(
                self._wrap_native_events(events, child_run_id=child_run_id),
                fallback_artifact_ref=getattr(session, "artifact_ref", None),
                fallback_error=getattr(session, "last_error", None),
            )
            return self._result_from_payload(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                payload=payload,
            )
        except Exception:
            logger.exception("BI LeadAgent native handoff failed while running AgentScope DatasetAgent.")
            return self._result_from_payload(
                request=request,
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                task_id=task_id,
                payload=safe_native_failure_result_payload(),
            )

    @staticmethod
    def _build_native_child_message(
        *,
        request: BILeadAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
    ) -> Any:
        content = (
            "AgentScope native handoff: 请作为 DatasetAgent 子运行执行已确认任务。\n"
            f"handoff_id: {handoff_id}\n"
            f"parent_agent: bi_lead_agent\n"
            f"child_agent: dataset_agent\n"
            f"child_run_id: {child_run_id}\n"
            f"dataset_id: {request.dataset_id}\n"
            f"task_goal: {request.task_goal}\n"
            f"confirmed_question: {request.confirmed_question}\n"
            f"routing_rationale: {request.routing_rationale}\n"
            "只能返回安全 JSON：event_type、child_run_id、artifact_ref、checkpoint_ref、answer_summary、row_count、column_count。"
        )
        return UserMsg(name="user", content=content)

    @staticmethod
    def _wrap_native_events(events: list[Any], *, child_run_id: str) -> list[Any]:
        wrapped: list[Any] = [
            {"event_type": "agent.child.accepted", "child_run_id": child_run_id},
            {"event_type": "agent.child.running", "child_run_id": child_run_id},
        ]
        wrapped.extend(events)
        return wrapped

    @staticmethod
    def _result_from_payload(
        *,
        request: BILeadAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
        task_id: str | None,
        payload: dict[str, Any],
    ) -> BILeadAgentHandoffResult:
        return BILeadAgentHandoffResult(
            handoff_id=handoff_id,
            child_run_id=_safe_str(payload.get("child_run_id")) or child_run_id,
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status=native_status_or_default(payload),
            answer_summary=_safe_str(payload.get("answer_summary")),
            artifact_ref=_safe_str(payload.get("artifact_ref")),
            checkpoint_ref=_safe_str(payload.get("checkpoint_ref")),
            row_count=_safe_int(payload.get("row_count")),
            column_count=_safe_int(payload.get("column_count")),
            status_reason=_safe_str(payload.get("status_reason")),
            error_code=_safe_str(payload.get("error_code")),
            error_summary=_safe_str(payload.get("error_summary")),
        )


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
