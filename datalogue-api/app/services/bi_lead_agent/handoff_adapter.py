# ============================================================
# File Name   : handoff_adapter.py
# Description:
#   BI LeadAgent 到 DatasetAgent Runtime 的 Host Handoff Adapter。
#
# Responsibilities:
#   - 将已确认的数据集任务交给 AgentScope DatasetAgent Runtime 执行。
#   - 从 AgentScope 事件中抽取安全 handoff 摘要，禁止 SQL/schema/raw rows/DSL 等内部字段外泄。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from agentscope.message import TextBlock, ToolResultBlock

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest, BILeadAgentHandoffResult
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentscope_dataset_runtime import AgentScopeDatasetRuntimeBridge
from app.services.bi_lead_agent.dataset_agent_factory import AgentScopeDatasetAgentFactory
from app.services.bi_tools import build_bi_atomic_toolkit


_ALLOWED_EVENT_FIELDS = {
    "answer_summary",
    "artifact_ref",
    "checkpoint_ref",
    "row_count",
    "column_count",
    "status",
    "status_reason",
    "code",
    "error_code",
    "error_summary",
}
_COMPLETED_STATUSES = {"completed", "ready"}
_BLOCKED_STATUSES = {"blocked", "failed", "cancelled"}


def _new_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class DatalogueBIHandoffAdapter:
    """Host 侧 handoff adapter；只调用 AgentScope run_reply_stream，不走 direct query 旁路。"""

    def __init__(
        self,
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        dataset_agent_factory: AgentScopeDatasetAgentFactory,
    ) -> None:
        self.bridge = bridge
        self.dataset_agent_factory = dataset_agent_factory
        self._sanitizer = DatalogueAgenticShell()

    @classmethod
    def from_db(cls, db: Session) -> "DatalogueBIHandoffAdapter":
        toolkit = build_bi_atomic_toolkit(db)
        return cls(
            bridge=AgentScopeDatasetRuntimeBridge(toolkit=toolkit),
            dataset_agent_factory=AgentScopeDatasetAgentFactory(db),
        )

    async def query_dataset(
        self,
        request: BILeadAgentHandoffRequest,
        task_id: str | None = None,
    ) -> BILeadAgentHandoffResult:
        handoff_id = _new_prefixed_id("handoff")
        child_run_id = _new_prefixed_id("dataset-run")
        session = self.bridge.start_session(
            dataset_id=request.dataset_id,
            question=request.confirmed_question,
            agent_name="bi_lead_agent",
            trace_id=request.trace_id,
        )  # session 是 DatasetAgent Runtime 的私有执行态，返回结果只暴露 refs 和摘要。

        try:
            agent = self.dataset_agent_factory.create(session)
            events = await self.bridge.run_reply_stream(
                agent,
                msg=self._build_agent_message(request=request, handoff_id=handoff_id, child_run_id=child_run_id),
                session=session,
            )
            safe_payload = self._extract_safe_payload(events=events, session=session)
            handoff_status = self._handoff_status_from_payload(safe_payload=safe_payload, session=session)
            return BILeadAgentHandoffResult(
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                dataset_id=request.dataset_id,
                task_id=task_id,
                trace_id=request.trace_id,
                handoff_status=handoff_status,
                answer_summary=self._safe_str(safe_payload.get("answer_summary")),
                artifact_ref=self._safe_str(safe_payload.get("artifact_ref") or getattr(session, "artifact_ref", None)),
                checkpoint_ref=self._safe_str(safe_payload.get("checkpoint_ref")),
                row_count=self._safe_int(safe_payload.get("row_count")),
                column_count=self._safe_int(safe_payload.get("column_count")),
                status_reason=self._safe_str(safe_payload.get("status_reason")),
                error_code=self._safe_str(safe_payload.get("error_code")),
                error_summary=self._safe_str(safe_payload.get("error_summary")),
            )
        except Exception as exc:
            return BILeadAgentHandoffResult(
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                dataset_id=request.dataset_id,
                task_id=task_id,
                trace_id=request.trace_id,
                handoff_status="failed",
                status_reason="agentscope_dataset_agent_failed",
                error_code="AGENTSCOPE_DATASET_AGENT_FAILED",
                error_summary=str(exc),
            )

    @staticmethod
    def _build_agent_message(
        *,
        request: BILeadAgentHandoffRequest,
        handoff_id: str,
        child_run_id: str,
    ) -> dict[str, str]:
        content = (
            "请执行 BI LeadAgent 已确认的数据集任务。\n"
            f"handoff_id: {handoff_id}\n"
            f"child_run_id: {child_run_id}\n"
            f"dataset_id: {request.dataset_id}\n"
            f"task_goal: {request.task_goal}\n"
            f"confirmed_question: {request.confirmed_question}\n"
            f"routing_rationale: {request.routing_rationale}\n"
            "只能通过 external tools 完成查询，最终只返回安全摘要和引用字段。"
        )
        return {"role": "user", "content": content}

    def _extract_safe_payload(self, *, events: list[Any], session: Any) -> dict[str, Any]:
        safe_payload: dict[str, Any] = {}
        for payload in self._payload_candidates(events):
            sanitized = self._sanitize_payload(payload)
            for key in _ALLOWED_EVENT_FIELDS:
                value = sanitized.get(key)
                if value is not None:
                    safe_payload[key] = value  # 白名单字段以后者为准，便于最终 summary 覆盖中间 tool 状态。

        if getattr(session, "artifact_ref", None):
            safe_payload["artifact_ref"] = getattr(session, "artifact_ref")
        if getattr(session, "last_error", None):
            last_error = self._sanitize_payload(getattr(session, "last_error"))
            safe_payload.setdefault("status", "blocked")
            safe_payload.setdefault("error_code", last_error.get("code"))
            safe_payload.setdefault("error_summary", last_error.get("error_summary"))
        return safe_payload

    def _payload_candidates(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from self._payload_candidates(nested)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from self._payload_candidates(item)
            return
        if isinstance(value, ToolResultBlock):
            for block in value.output or []:
                yield from self._payload_candidates(block)
            return
        if isinstance(value, TextBlock):
            yield from self._payload_from_text(value.text)
            return
        execution_results = getattr(value, "execution_results", None)
        if execution_results is not None:
            yield from self._payload_candidates(execution_results)
            return
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                yield from self._payload_candidates(dumped)

    @staticmethod
    def _payload_from_text(text: str | None) -> Iterable[dict[str, Any]]:
        if not text:
            return []
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return [{"answer_summary": text}]
        return [loaded] if isinstance(loaded, dict) else []

    def _sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized = self._sanitizer.sanitize_output(payload)
        return sanitized if isinstance(sanitized, dict) else {}

    @staticmethod
    def _handoff_status_from_payload(*, safe_payload: dict[str, Any], session: Any) -> str:
        status = str(safe_payload.get("status") or "").strip().lower()
        if status == "cancelled":
            return "cancelled"
        if status == "failed":
            return "failed"
        if status == "blocked":
            return "blocked"
        if status in _COMPLETED_STATUSES and (safe_payload.get("artifact_ref") or getattr(session, "artifact_ref", None)):
            return "completed"
        if safe_payload.get("artifact_ref") or getattr(session, "artifact_ref", None):
            return "completed"
        if status in _BLOCKED_STATUSES:
            return status
        return "blocked"

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
