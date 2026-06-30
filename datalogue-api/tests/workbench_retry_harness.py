# ============================================================
# File Name   : workbench_retry_harness.py
# Description:
#   C3 Workbench retry completed 的内部自动化验收 harness。
#
# Responsibilities:
#   - 复刻真实浏览器从 Workbench 点击 retry 到 Chat 主链 completed 的动作顺序。
#   - 固化 thread、checkpoint、event、artifact ref 和 Workbench View Model 的一致性断言入口。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app import models
from app.models.agentscope_workbench import AgentScopeEvent, AgentScopeRef
from app.schemas.bi_workbench import build_datalogue_event_envelope
from app.schemas.chat import ChatRequest
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_failed,
    record_agentscope_ref,
)
from app.services.artifact_store import ArtifactStore
from app.services.conversation_store import ConversationStore


@dataclass(frozen=True)
class WorkbenchRetryCompletedHarnessResult:
    """浏览器 retry completed 验收结果；字段只保留用户可见摘要和 refs。"""

    thread_id: str
    checkpoint_ref: str
    initial_view: dict[str, Any]
    retry_response: dict[str, Any]
    stream_events: list[dict[str, Any]]
    event_types: list[str]
    final_payload: dict[str, Any]
    completed_view: dict[str, Any]
    primary_artifact_ref: str
    persisted_event_types: list[str]
    refs: list[dict[str, str]]


class _MultiturnSettings:
    """强制开启多轮 checkpoint 恢复路径，避免 harness 退化成普通单轮查询。"""

    MULTITURN_ENABLED = True
    MULTITURN_LOCK_TTL_SECONDS = 300
    MULTITURN_LAST_SUCCESS_TASK_MAX_TOKENS = 2000
    MULTITURN_COMPACTION_ENABLED = False


def _sse(payload: dict[str, Any]) -> dict[str, str]:
    return {"data": json.dumps(payload, ensure_ascii=False)}


async def run_workbench_retry_completed_harness(
    *,
    client: TestClient,
    db_session: Session,
    monkeypatch,
    dataset_id: int,
) -> WorkbenchRetryCompletedHarnessResult:
    """执行内部-only retry completed 验收；动作顺序等价于真实浏览器点击 retry。"""

    from app.api import chat as chat_api

    monkeypatch.setattr("app.api.chat.get_settings", lambda: _MultiturnSettings())
    conversation = models.Conversation(
        title="C3-P2 browser retry completed harness",
        user_id=1,
        dataset_id=dataset_id,
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    session_id = f"conversation-{conversation.id}"
    store = ConversationStore(db_session)
    store.load_or_create(session_id=session_id, user_id="1")
    checkpoint_ref = store.register_retry_checkpoint(
        session_id=session_id,
        checkpoint_kind="query_context_ready",
        user_id="1",
        conversation_id=conversation.id,
        task_id=f"c3-p2-browser-harness-{uuid.uuid4().hex[:8]}",
        permission_scope=f"dataset:{dataset_id}",
        context={
            "question": "查询杨凯 2024 年工作日志",
            "dataset_id": dataset_id,
            "route_decision": {"dataset_id": dataset_id, "decision": "selected"},
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    thread_id = f"as_{uuid.uuid4()}"
    session = create_agentscope_session(
        db_session,
        thread_id=thread_id,
        title="C3-P2 浏览器 retry completed harness",
        legacy_conversation_id=conversation.id,
    )
    append_user_message(
        db_session,
        thread_id=session.thread_id,
        content_summary="查询杨凯 2024 年工作日志",
        payload={"checkpoint_ref": checkpoint_ref},
    )
    failed = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    mark_message_failed(
        db_session,
        message_id=failed.message_id,
        error_summary="浏览器 harness：查询执行中断，可基于检查点重试。",
        payload={"checkpoint_ref": checkpoint_ref},
    )
    record_agentscope_ref(
        db_session,
        thread_id=session.thread_id,
        message_id=failed.message_id,
        ref_type="checkpoint",
        ref_value=checkpoint_ref,
        relation="checkpoint",
    )

    initial_view = client.get(f"/api/workbench/thread/{session.thread_id}").json()
    retry_response = client.post(
        "/api/workbench/actions/retry",
        json={
            "thread_id": session.thread_id,
            "message_id": failed.message_id,
            "checkpoint_ref": checkpoint_ref,
            "selected_action": "retry_last_step",
        },
    )
    retry_payload = retry_response.json()
    run_request = retry_payload["run_request"]
    trace_id = f"trace-c3-p2-browser-harness-{uuid.uuid4().hex[:8]}"
    primary_artifact_ref = ArtifactStore(db_session).put_json(
        kind="sql_result",
        payload={"summary": "重试后返回 100 条工作日志"},
        dataset_id=dataset_id,
        conversation_id=conversation.id,
        trace_id=trace_id,
    )
    answer_completed = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={
            "summary": "已从 Workbench 检查点重试并完成查询",
            "primary_ref": {"ref_type": "artifact", "ref": primary_artifact_ref},
            "related_refs": [
                {"ref_type": "trace", "ref": f"trace:{trace_id}"},
                {"ref_type": "checkpoint", "ref": checkpoint_ref},
            ],
        },
        task_id="c3-p2-browser-harness-rerun",
        trace_id=trace_id,
    )

    async def successful_retry_singleturn(payload, *args, **kwargs):
        # 真实浏览器点击后也是由 run_request 白名单字段驱动 Chat 主链；这里固定成功产物以避免依赖外部数据源。
        assert payload.thread_id == session.thread_id
        assert payload.retry_checkpoint_ref == checkpoint_ref
        assert payload.dataset_id == dataset_id
        yield _sse(
            {
                "type": "final",
                "answer": "已从 Workbench 检查点重试并完成查询",
                "conversation_id": conversation.id,
                "result_ref": primary_artifact_ref,
                "task_id": "c3-p2-browser-harness-rerun",
                "trace_id": trace_id,
                "event_envelope": answer_completed.model_dump(mode="json"),
            }
        )

    with (
        patch("app.api.chat._stream_chat_singleturn", successful_retry_singleturn),
        patch("app.api.chat.resolve_term_clarification", return_value={"status": "none"}),
    ):
        stream_events = [
            json.loads(item["data"])
            async for item in chat_api._stream_chat(
                ChatRequest(
                    question=run_request["question"],
                    session_id=session_id,
                    conversation_id=run_request["conversation_id"],
                    thread_id=run_request["thread_id"],
                    dataset_id=run_request["dataset_id"],
                    retry_checkpoint_ref=run_request["retry_checkpoint_ref"],
                ),
                db_session,
            )
        ]

    completed_view = client.get(f"/api/workbench/thread/{session.thread_id}").json()
    event_types = [
        event.get("event_envelope", {}).get("event_type") or event.get("type")
        for event in stream_events
    ]
    final_payload = [event for event in stream_events if event.get("type") == "final"][-1]
    persisted_event_types = [
        event.event_type
        for event in (
            db_session.query(AgentScopeEvent)
            .filter_by(thread_id=session.thread_id)
            .order_by(AgentScopeEvent.id.asc())
            .all()
        )
    ]
    refs = [
        {"ref_type": ref.ref_type, "relation": ref.relation, "ref": ref.ref_value}
        for ref in (
            db_session.query(AgentScopeRef)
            .filter_by(thread_id=session.thread_id)
            .order_by(AgentScopeRef.id.asc())
            .all()
        )
    ]

    return WorkbenchRetryCompletedHarnessResult(
        thread_id=session.thread_id,
        checkpoint_ref=checkpoint_ref,
        initial_view=initial_view,
        retry_response=retry_payload,
        stream_events=stream_events,
        event_types=event_types,
        final_payload=final_payload,
        completed_view=completed_view,
        primary_artifact_ref=primary_artifact_ref,
        persisted_event_types=persisted_event_types,
        refs=refs,
    )
