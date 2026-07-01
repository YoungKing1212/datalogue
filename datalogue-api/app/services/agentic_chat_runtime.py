# ============================================================
# File Name   : agentic_chat_runtime.py
# Description:
#   /chat/stream 的 Agentic Shell-first 回合运行时适配层。
#
# Responsibilities:
#   - 承接 Chat SSE wrapper 中的单轮/多轮回合生命周期。
#   - 通过 hooks 复用既有 chat.py helper，避免 P2.1 提前重写 BI 主链。
#   - 让 chat.py 收缩为 transport adapter 和兼容 hook 装配层。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app import schemas
from app.services.conversation_store import ConversationStore, session_key


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatalogueChatStreamRuntimeHooks:
    """P2.1 迁移期 hook 集合；Runtime 负责生命周期，底层业务能力仍复用现有实现。"""

    log_chat_stream_checkpoint: Callable[..., None]
    build_agentic_runtime_shadow_boundary: Callable[..., dict[str, Any] | None]
    begin_agentscope_chat_bridge: Callable[..., Any]
    stream_singleturn_via_agentic_runtime: Callable[..., AsyncIterator[dict[str, Any]]]
    mirror_agentscope_stream_event: Callable[..., tuple[dict[str, Any], bool, bool]]
    interrupt_agentscope_chat_bridge: Callable[..., bool]
    fail_agentscope_chat_bridge: Callable[..., bool]
    complete_agentscope_chat_bridge: Callable[..., bool]
    record_agentscope_event_from_sse: Callable[..., None]
    attach_artifact_card_refs_to_final_payload: Callable[..., None]
    sse_data: Callable[[dict[str, Any]], dict[str, Any]]
    with_event_envelope: Callable[..., dict[str, Any]]
    retry_sse_event: Callable[..., dict[str, Any]]
    summarize_conversation_state: Callable[..., dict[str, Any]]
    chat_stream_log_summary: Callable[[dict[str, Any]], dict[str, Any]]
    persist_completed_turn: Callable[..., bool]
    get_observability_tracer: Callable[[], Any]


class DatalogueChatStreamRuntime:
    """把 `/chat/stream` 回合生命周期从 FastAPI route 层迁出；不改变底层问数执行链。"""

    def __init__(
        self,
        *,
        db: Session,
        settings: Any,
        hooks: DatalogueChatStreamRuntimeHooks,
    ) -> None:
        self.db = db
        self.settings = settings
        self.hooks = hooks

    async def stream(self, payload: schemas.ChatRequest) -> AsyncIterator[dict[str, Any]]:
        """执行一次 chat turn；调用方只负责把返回事件交给 SSE transport。"""

        self.hooks.log_chat_stream_checkpoint(
            "wrapper_start",
            question_preview=payload.question[:80],
            payload_dataset_id=payload.dataset_id,
            conversation_id=payload.conversation_id,
            session_id=payload.session_id,
            multiturn_enabled=bool(self.settings.MULTITURN_ENABLED),
        )
        agentic_runtime_boundary = self.hooks.build_agentic_runtime_shadow_boundary(
            payload,
            settings=self.settings,
        )
        agentscope_context = self.hooks.begin_agentscope_chat_bridge(
            payload,
            self.db,
            agentic_runtime_boundary=agentic_runtime_boundary,
        )
        if not self.settings.MULTITURN_ENABLED:
            async for event in self._stream_singleturn(payload, agentscope_context):
                yield event
            return

        async for event in self._stream_multiturn(payload, agentscope_context):
            yield event

    async def _stream_singleturn(
        self,
        payload: schemas.ChatRequest,
        agentscope_context: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        self.hooks.log_chat_stream_checkpoint(
            "multiturn_disabled",
            conversation_id=payload.conversation_id,
            payload_dataset_id=payload.dataset_id,
        )
        final_seen = False
        bridge_closed = False
        try:
            async for event in self.hooks.stream_singleturn_via_agentic_runtime(
                payload,
                self.db,
                settings=self.settings,
            ):
                event, final_seen, bridge_closed = self.hooks.mirror_agentscope_stream_event(
                    db=self.db,
                    context=agentscope_context,
                    event=event,
                    final_seen=final_seen,
                    bridge_closed=bridge_closed,
                )
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            if not bridge_closed:
                bridge_closed = self.hooks.interrupt_agentscope_chat_bridge(
                    self.db,
                    context=agentscope_context,
                    reason="问数链路已中断，已保留可恢复状态。",
                )
            raise
        except Exception as exc:
            if not bridge_closed:
                bridge_closed = self.hooks.fail_agentscope_chat_bridge(
                    self.db,
                    context=agentscope_context,
                    error_summary=f"问数链路异常：{exc}",
                    payload={"checkpoint_ref": payload.retry_checkpoint_ref},
                )
            raise
        finally:
            if not bridge_closed:
                self.hooks.fail_agentscope_chat_bridge(
                    self.db,
                    context=agentscope_context,
                    error_summary=(
                        "问数链路未完成 AgentScope 收口。"
                        if final_seen
                        else "问数链路未返回完成事件。"
                    ),
                    payload={"checkpoint_ref": payload.retry_checkpoint_ref},
                )

    async def _stream_multiturn(
        self,
        payload: schemas.ChatRequest,
        agentscope_context: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        store = ConversationStore(self.db)
        business_session_id = session_key(payload.session_id, payload.conversation_id)
        if business_session_id == "conversation-new":
            business_session_id = f"request-{uuid.uuid4().hex[:16]}"
        user_id = "1"
        lock_owner = f"chat-{uuid.uuid4().hex[:12]}"
        state = store.load_or_create(session_id=business_session_id, user_id=user_id)
        lead_multiturn_context = store.lead_multiturn_context(state)
        logger.info(
            "[ConversationState] 读取会话状态: session_id=%s, summary=%s",
            business_session_id,
            json.dumps(
                self.hooks.summarize_conversation_state(state, lead_context=lead_multiturn_context),
                ensure_ascii=False,
                default=str,
            ),
        )
        if not store.acquire_turn_lock(
            session_id=business_session_id,
            lock_owner=lock_owner,
            ttl_seconds=self.settings.MULTITURN_LOCK_TTL_SECONDS,
        ):
            async for event in self._stream_lock_rejected(payload, agentscope_context, business_session_id, lock_owner):
                yield event
            return

        self.hooks.log_chat_stream_checkpoint(
            "turn_lock_acquired",
            business_session_id=business_session_id,
            lock_owner=lock_owner,
            ttl_seconds=self.settings.MULTITURN_LOCK_TTL_SECONDS,
        )

        final_payload: dict[str, Any] | None = None
        conversation_state_persisted = False
        bridge_closed = False
        trace_context_sink: list[Any] = []
        subagent_control_plane_sink: list[Any] = []
        effective_payload = payload
        retry_restore = None
        try:
            if payload.retry_checkpoint_ref:
                async for retry_event in self._stream_retry_restore_start(
                    payload,
                    agentscope_context,
                    store,
                    user_id,
                    lead_multiturn_context,
                    business_session_id,
                ):
                    if isinstance(retry_event, tuple):
                        retry_restore, lead_multiturn_context, effective_payload = retry_event
                    else:
                        yield retry_event
            pending_resolution = self._resolve_pending_resolution(
                payload=payload,
                state=state,
                store=store,
                retry_restore=retry_restore,
            )
            logger.info(
                "[ConversationState] 澄清解析结果: session_id=%s, pending_resolution=%s",
                business_session_id,
                json.dumps(pending_resolution, ensure_ascii=False, default=str),
            )
            effective_payload = self._effective_payload_for_pending_resolution(
                payload=payload,
                effective_payload=effective_payload,
                pending_resolution=pending_resolution,
            )
            async for event in self.hooks.stream_singleturn_via_agentic_runtime(
                effective_payload,
                self.db,
                settings=self.settings,
                multiturn_context=lead_multiturn_context,
                conversation_state=state,
                conversation_store=store,
                pending_resolution=pending_resolution,
                observability_session_id=business_session_id,
                trace_context_sink=trace_context_sink,
                subagent_control_plane_sink=subagent_control_plane_sink,
                defer_trace_close=True,
            ):
                (
                    outbound_events,
                    event_final_payload,
                    conversation_state_persisted,
                    bridge_closed,
                ) = self._handle_multiturn_event(
                    event=event,
                    payload=payload,
                    effective_payload=effective_payload,
                    agentscope_context=agentscope_context,
                    store=store,
                    state=state,
                    user_id=user_id,
                    business_session_id=business_session_id,
                    pending_resolution=pending_resolution,
                    trace_context_sink=trace_context_sink,
                    subagent_control_plane_sink=subagent_control_plane_sink,
                    conversation_state_persisted=conversation_state_persisted,
                    bridge_closed=bridge_closed,
                )
                final_payload = event_final_payload or final_payload
                for outbound_event in outbound_events:
                    yield outbound_event
        finally:
            self._finalize_multiturn(
                store=store,
                agentscope_context=agentscope_context,
                business_session_id=business_session_id,
                lock_owner=lock_owner,
                final_payload=final_payload,
                conversation_state_persisted=conversation_state_persisted,
                bridge_closed=bridge_closed,
                trace_context_sink=trace_context_sink,
            )

    async def _stream_lock_rejected(
        self,
        payload: schemas.ChatRequest,
        agentscope_context: Any,
        business_session_id: str,
        lock_owner: str,
    ) -> AsyncIterator[dict[str, Any]]:
        self.hooks.log_chat_stream_checkpoint(
            "turn_lock_rejected",
            business_session_id=business_session_id,
            lock_owner=lock_owner,
            ttl_seconds=self.settings.MULTITURN_LOCK_TTL_SECONDS,
        )
        lock_payload = {
            "type": "final",
            "sql": None,
            "sql_list": [],
            "answer": "同一会话已有一轮问数正在处理中，请稍后再试。",
            "entry_intent": "multiturn_lock",
            "entry_route": "turn_pending",
            "conversation_id": payload.conversation_id,
        }
        self.hooks.attach_artifact_card_refs_to_final_payload(lock_payload, include_card=False)
        self.hooks.fail_agentscope_chat_bridge(
            self.db,
            context=agentscope_context,
            error_summary=str(lock_payload["answer"]),
            payload=lock_payload,
        )
        lock_payload["thread_id"] = agentscope_context.thread_id
        lock_event = self.hooks.sse_data(
            self.hooks.with_event_envelope(
                lock_payload,
                event_type="error.blocked",
                visibility="user_visible",
                payload_fields=("answer", "entry_route", "primary_ref", "related_refs", "task_id", "trace_id"),
            )
        )
        self.hooks.record_agentscope_event_from_sse(self.db, agentscope_context, lock_event)
        yield lock_event

    async def _stream_retry_restore_start(
        self,
        payload: schemas.ChatRequest,
        agentscope_context: Any,
        store: ConversationStore,
        user_id: str,
        lead_multiturn_context: dict[str, Any],
        business_session_id: str,
    ) -> AsyncIterator[dict[str, Any] | tuple[Any, dict[str, Any], schemas.ChatRequest]]:
        retry_event = self.hooks.retry_sse_event(
            "retry.started",
            checkpoint_ref=payload.retry_checkpoint_ref,
        )
        self.hooks.record_agentscope_event_from_sse(self.db, agentscope_context, retry_event)
        yield retry_event
        retry_restore = store.restore_retry_checkpoint(
            payload.retry_checkpoint_ref,
            user_id=user_id,
            conversation_id=payload.conversation_id,
        )
        effective_payload = payload
        if retry_restore.retry_scope == "last_safe_checkpoint":
            restored_context = retry_restore.context or {}
            lead_multiturn_context = dict(lead_multiturn_context or {})
            lead_multiturn_context["retry_checkpoint"] = {
                "checkpoint_ref": retry_restore.checkpoint_ref,
                "checkpoint_kind": retry_restore.checkpoint_kind,
                "task_id": retry_restore.task_id,
                "retry_scope": retry_restore.retry_scope,
            }
            effective_payload = payload.model_copy(
                update={
                    "question": retry_restore.question or payload.question,
                    "dataset_id": retry_restore.dataset_id or payload.dataset_id,
                    "clarification_response": None,
                }
            )
            self.hooks.log_chat_stream_checkpoint(
                "retry_checkpoint_restored",
                business_session_id=business_session_id,
                checkpoint_ref=retry_restore.checkpoint_ref,
                checkpoint_kind=retry_restore.checkpoint_kind,
                restored_dataset_id=retry_restore.dataset_id,
                restored_context_keys=sorted(restored_context.keys()),
            )
            retry_event = self.hooks.retry_sse_event(
                "retry.checkpoint_restored",
                checkpoint_ref=payload.retry_checkpoint_ref,
                retry_scope=retry_restore.retry_scope,
            )
            self.hooks.record_agentscope_event_from_sse(self.db, agentscope_context, retry_event)
            yield retry_event
        else:
            self.hooks.log_chat_stream_checkpoint(
                "retry_fallback_to_whole_task",
                business_session_id=business_session_id,
                checkpoint_ref=payload.retry_checkpoint_ref,
                reason=retry_restore.fallback_reason,
            )
            retry_event = self.hooks.retry_sse_event(
                "retry.fallback_to_whole_task",
                checkpoint_ref=payload.retry_checkpoint_ref,
                retry_scope=retry_restore.retry_scope,
                reason=retry_restore.fallback_reason,
            )
            self.hooks.record_agentscope_event_from_sse(self.db, agentscope_context, retry_event)
            yield retry_event
        yield retry_restore, lead_multiturn_context, effective_payload

    @staticmethod
    def _resolve_pending_resolution(
        *,
        payload: schemas.ChatRequest,
        state: Any,
        store: ConversationStore,
        retry_restore: Any,
    ) -> dict[str, Any]:
        if retry_restore and retry_restore.retry_scope == "last_safe_checkpoint":
            return {"status": "none", "reason": "retry_checkpoint_restored"}
        return store.resolve_pending_clarification(
            state,
            question=payload.question,
            clarification_response=payload.clarification_response,
        )

    @staticmethod
    def _effective_payload_for_pending_resolution(
        *,
        payload: schemas.ChatRequest,
        effective_payload: schemas.ChatRequest,
        pending_resolution: dict[str, Any],
    ) -> schemas.ChatRequest:
        if (
            pending_resolution.get("status") == "resolved"
            and pending_resolution.get("type") == "dataset"
        ):
            return payload.model_copy(
                update={
                    "dataset_id": int(pending_resolution["dataset_id"]),
                    "clarification_response": None,
                }
            )
        if pending_resolution.get("status") == "inject" and pending_resolution.get("type") == "term":
            updates: dict[str, Any] = {
                "clarification_response": pending_resolution.get("clarification_response") or {},
            }
            if pending_resolution.get("conversation_id") and payload.conversation_id is None:
                updates["conversation_id"] = int(pending_resolution["conversation_id"])
            if pending_resolution.get("dataset_id") and payload.dataset_id is None:
                updates["dataset_id"] = int(pending_resolution["dataset_id"])
            return payload.model_copy(update=updates)
        return effective_payload

    def _handle_multiturn_event(
        self,
        *,
        event: dict[str, Any],
        payload: schemas.ChatRequest,
        effective_payload: schemas.ChatRequest,
        agentscope_context: Any,
        store: ConversationStore,
        state: Any,
        user_id: str,
        business_session_id: str,
        pending_resolution: dict[str, Any],
        trace_context_sink: list[Any],
        subagent_control_plane_sink: list[Any],
        conversation_state_persisted: bool,
        bridge_closed: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool, bool]:
        final_payload: dict[str, Any] | None = None
        outbound_events = [event]
        data = event.get("data") if isinstance(event, dict) else None
        if data:
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "final":
                    final_payload = parsed
                    outbound_events = []
                    self.hooks.log_chat_stream_checkpoint(
                        "wrapper_final_seen",
                        business_session_id=business_session_id,
                        summary=self.hooks.chat_stream_log_summary(final_payload),
                    )
                    try:
                        conversation_state_persisted = self.hooks.persist_completed_turn(
                            store=store,
                            state=state,
                            user_id=user_id,
                            business_session_id=business_session_id,
                            effective_payload=effective_payload,
                            final_payload=final_payload,
                            pending_resolution=pending_resolution,
                            payload_question=payload.question,
                            trace_context_sink=trace_context_sink,
                            subagent_control_plane=(
                                subagent_control_plane_sink[0]
                                if subagent_control_plane_sink
                                else None
                            ),
                        )
                    except Exception as persist_exc:  # noqa: BLE001
                        logger.exception("[DatalogueChatStreamRuntime] 写入多轮状态失败: %s", persist_exc)
                    if payload.retry_checkpoint_ref:
                        if parsed.get("error"):
                            retry_event = self.hooks.retry_sse_event(
                                "retry.failed",
                                checkpoint_ref=payload.retry_checkpoint_ref,
                                reason=str(parsed.get("error")),
                            )
                        else:
                            retry_event = self.hooks.retry_sse_event(
                                "retry.completed",
                                checkpoint_ref=payload.retry_checkpoint_ref,
                            )
                        self.hooks.record_agentscope_event_from_sse(self.db, agentscope_context, retry_event)
                        outbound_events = [retry_event]
                    bridge_closed = self.hooks.complete_agentscope_chat_bridge(
                        self.db,
                        context=agentscope_context,
                        final_payload=parsed,
                    )
                    parsed["thread_id"] = agentscope_context.thread_id
                    event = self.hooks.sse_data(parsed)
                    outbound_events.append(event)
            except json.JSONDecodeError:
                pass
            except Exception as bridge_exc:  # noqa: BLE001
                logger.warning("[AgentScopeBridge] 事件投影失败，不中断主链: %s", bridge_exc)
        self.hooks.record_agentscope_event_from_sse(self.db, agentscope_context, event)
        return outbound_events, final_payload, conversation_state_persisted, bridge_closed

    def _finalize_multiturn(
        self,
        *,
        store: ConversationStore,
        agentscope_context: Any,
        business_session_id: str,
        lock_owner: str,
        final_payload: dict[str, Any] | None,
        conversation_state_persisted: bool,
        bridge_closed: bool,
        trace_context_sink: list[Any],
    ) -> None:
        if conversation_state_persisted and trace_context_sink:
            tracer = self.hooks.get_observability_tracer()
            tracer.close_trace(trace_context_sink[0])
        if not conversation_state_persisted:
            self.hooks.log_chat_stream_checkpoint(
                "wrapper_incomplete",
                business_session_id=business_session_id,
                final_seen=final_payload is not None,
            )
        if not bridge_closed:
            self.hooks.interrupt_agentscope_chat_bridge(
                self.db,
                context=agentscope_context,
                reason="问数链路已中断，已保留可恢复状态。",
            )
        self.hooks.log_chat_stream_checkpoint(
            "turn_lock_released",
            business_session_id=business_session_id,
            lock_owner=lock_owner,
            completed=conversation_state_persisted,
        )
        store.release_turn_lock(session_id=business_session_id, lock_owner=lock_owner)
