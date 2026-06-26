# ============================================================
# File Name   : bi_workbench_tool.py
# Description:
#   ask_bi / BIWorkbenchTool 最小稳定入口。
#
# Responsibilities:
#   - 为外层 Agentic Shell、ReportAgent、PythonAgent、AuditAgent 提供唯一 BI 调用入口。
#   - 第一阶段复用现有 Chat / LeadAgent / DatasetAgent 主链，只做协议收敛和防泄露适配。
#   - 将 SQL、schema、capsule、control_plane 留在后端内部，不进入用户可见响应。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.bi_workbench import (
    ArtifactCard,
    ArtifactRef,
    AskBIRequest,
    AskBIResponse,
    DatalogueEventEnvelope,
)
from app.schemas.chat import ChatRequest

ChatStreamCallable = Callable[[ChatRequest, Session | None], AsyncIterator[dict[str, Any]]]


_SAFE_CANDIDATE_DATASET_KEYS = {
    "dataset_id",
    "id",
    "name",
    "display_name",
    "business_name",
    "description",
    "reason",
    "score",
}
_WAITING_ROUTES = {
    "clarify",
    "clarification",
    "dataset_select",
    "turn_pending",
}


class BIWorkbenchTool:
    """外层 BI 工具适配器；不重写问数主链，只消费主链已产生的安全摘要。"""

    def __init__(
        self,
        db: Session | None = None,
        *,
        stream_chat: ChatStreamCallable | None = None,
    ) -> None:
        self.db = db
        self._stream_chat = stream_chat

    async def ask(self, request: AskBIRequest) -> AskBIResponse:
        """执行 ask_bi，并把 Chat SSE 收敛为稳定的 BI 工作台响应。"""

        task_id = f"task-{uuid.uuid4().hex}"
        chat_payload = self._build_chat_request(request)
        stream_chat = self._resolve_stream_chat()
        final_payload: dict[str, Any] | None = None
        candidate_datasets: list[dict[str, Any]] = []

        try:
            async for event in stream_chat(chat_payload, self.db):
                parsed = self._parse_sse_event(event)
                if not parsed:
                    continue
                if parsed.get("candidate_datasets"):
                    candidate_datasets = self._safe_candidate_datasets(
                        parsed.get("candidate_datasets")
                    )
                if parsed.get("type") == "final":
                    final_payload = parsed  # final 仍是内部 payload，后续只投影安全字段。
                    if parsed.get("candidate_datasets"):
                        candidate_datasets = self._safe_candidate_datasets(
                            parsed.get("candidate_datasets")
                        )
        except Exception as exc:  # noqa: BLE001
            # ask_bi 是外层唯一入口，主链异常不能泄露栈和 SQL，只返回阻塞状态供调用方降级。
            return self._blocked_response(
                task_id=task_id,
                conversation_id=request.conversation_id,
                error=str(exc),
            )

        if final_payload is None:
            return self._blocked_response(
                task_id=task_id,
                conversation_id=request.conversation_id,
                error="BI 主链未返回 final 事件",
            )

        return self._response_from_final_payload(
            task_id=task_id,
            request=request,
            final_payload=final_payload,
            candidate_datasets=candidate_datasets,
        )

    def _resolve_stream_chat(self) -> ChatStreamCallable:
        if self._stream_chat is not None:
            return self._stream_chat
        from app.api.chat import _stream_chat

        return _stream_chat

    def _build_chat_request(self, request: AskBIRequest) -> ChatRequest:
        options = request.request_options if isinstance(request.request_options, dict) else {}
        # confirmed_dataset_id 是外层确认后的唯一数据集输入，转给现有 Chat 主链 dataset_id。
        return ChatRequest(
            question=request.question,
            session_id=self._optional_str(options.get("session_id")),
            conversation_id=request.conversation_id,
            dataset_id=request.confirmed_dataset_id,
        )

    def _response_from_final_payload(
        self,
        *,
        task_id: str,
        request: AskBIRequest,
        final_payload: dict[str, Any],
        candidate_datasets: list[dict[str, Any]],
    ) -> AskBIResponse:
        answer = self._optional_str(final_payload.get("answer"))
        status = self._status_from_final_payload(final_payload)
        event_type = self._event_type_for_status(status)
        conversation_id = self._optional_int(
            final_payload.get("conversation_id"),
            fallback=request.conversation_id,
        )
        primary_ref = self._artifact_ref(final_payload.get("result_ref"), default_type="result")
        related_refs = self._related_refs(final_payload, primary_ref=primary_ref)
        artifact_card = self._artifact_card(
            answer=answer,
            primary_ref=primary_ref,
            related_refs=related_refs,
        )
        envelope = DatalogueEventEnvelope(
            event_type=event_type,
            task_id=task_id,
            conversation_id=conversation_id,
            visibility="user_visible",
            payload={
                # 事件 payload 只承载外层状态和引用，不回传 Chat final_state 原文。
                "status": status,
                "answer": answer,
                "primary_ref": primary_ref.model_dump() if primary_ref else None,
                "candidate_datasets": candidate_datasets,
            },
            trace_id=self._optional_str(final_payload.get("trace_id")),
        )
        return AskBIResponse(
            task_id=task_id,
            event_envelope=envelope,
            candidate_datasets=candidate_datasets,
            answer=answer,
            artifact_card=artifact_card,
            primary_ref=primary_ref,
            related_refs=related_refs,
            status=status,
            error=self._optional_str(final_payload.get("error")) if status == "blocked" else None,
        )

    def _blocked_response(
        self,
        *,
        task_id: str,
        conversation_id: int | None,
        error: str,
    ) -> AskBIResponse:
        safe_error = self._safe_error(error)
        envelope = DatalogueEventEnvelope(
            event_type="error.blocked",
            task_id=task_id,
            conversation_id=conversation_id,
            visibility="user_visible",
            payload={"status": "blocked", "error": safe_error},
        )
        return AskBIResponse(
            task_id=task_id,
            event_envelope=envelope,
            status="blocked",
            error=safe_error,
        )

    def _status_from_final_payload(
        self,
        final_payload: dict[str, Any],
    ) -> str:
        if final_payload.get("error"):
            return "blocked"
        route = self._optional_str(final_payload.get("entry_route")) or ""
        query_plan = final_payload.get("query_plan") if isinstance(final_payload.get("query_plan"), dict) else {}
        strategy = self._optional_str(query_plan.get("execution_strategy")) or ""
        if route in _WAITING_ROUTES or strategy == "clarify":
            return "waiting_user"
        return "completed"

    def _event_type_for_status(self, status: str) -> str:
        if status == "waiting_user":
            return "clarification.required"
        if status == "blocked":
            return "error.blocked"
        return "answer.completed"

    def _artifact_card(
        self,
        *,
        answer: str | None,
        primary_ref: ArtifactRef | None,
        related_refs: list[ArtifactRef],
    ) -> ArtifactCard | None:
        refs = [ref for ref in [primary_ref, *related_refs] if ref is not None]
        if not answer and not refs:
            return None
        return ArtifactCard(
            summary=answer or "查询已完成，结果请通过引用查看。",
            preview_payload={"answer": answer} if answer else {},
            refs=refs,
        )

    def _related_refs(
        self,
        final_payload: dict[str, Any],
        *,
        primary_ref: ArtifactRef | None,
    ) -> list[ArtifactRef]:
        refs: list[ArtifactRef] = []
        report_ref = self._artifact_ref(final_payload.get("report_ref"), default_type="report")
        if report_ref and (primary_ref is None or report_ref.ref_id != primary_ref.ref_id):
            refs.append(report_ref)
        return refs

    def _artifact_ref(self, value: Any, *, default_type: str) -> ArtifactRef | None:
        ref_id = self._optional_str(value)
        if not ref_id:
            return None
        ref_type = default_type if default_type in {"result", "report", "artifact", "checkpoint"} else "unknown"
        return ArtifactRef(ref_id=self._public_ref_id(ref_id), ref_type=ref_type)

    def _public_ref_id(self, ref_id: str) -> str:
        # Chat 主链内部 result_ref 可能带 sql_result 语义，ask_bi 对外只暴露不含执行类型的句柄。
        return ref_id.replace("sql_result", "result")

    def _safe_error(self, error: str) -> str:
        lowered = error.lower()
        if any(
            token in lowered
            for token in ("raw_sql", "sql_result", "schema_context", "control_plane", "capsule")
        ):
            return "BI 主链执行失败，内部细节已隐藏。"
        return error

    def _safe_candidate_datasets(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        safe_items: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            safe = {key: item.get(key) for key in _SAFE_CANDIDATE_DATASET_KEYS if key in item}
            if safe:
                safe_items.append(safe)
        return safe_items

    def _parse_sse_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        data = event.get("data") if isinstance(event, dict) else None
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return data if isinstance(data, dict) else None

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_int(self, value: Any, *, fallback: int | None = None) -> int | None:
        try:
            if value is None:
                return fallback
            return int(value)
        except (TypeError, ValueError):
            return fallback


async def ask_bi(
    request: AskBIRequest,
    *,
    db: Session | None = None,
    stream_chat: ChatStreamCallable | None = None,
) -> AskBIResponse:
    """模块级便捷入口，便于外层 Agent 只依赖 ask_bi 这个工具名。"""

    return await BIWorkbenchTool(db=db, stream_chat=stream_chat).ask(request)
