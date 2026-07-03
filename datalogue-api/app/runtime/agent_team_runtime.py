# ============================================================
# File Name   : agent_team_runtime.py
# Description:
#   AgentScope Agent Team 任务入口运行时。
#
# Responsibilities:
#   - 创建 Datalogue task 真相源、AgentScope mirror session/message 和生命周期事件。
#   - 代理 AgentScope Service session stream，不执行 Datalogue 自研 Agent loop 或 handoff。
#   - 在异常路径写入安全失败状态，禁止回退到旧直接查询入口。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.events.projection import build_task_envelope, project_agentscope_event
from app.middlewares.lifecycle import log_lifecycle, log_output
from app.models.agent_team_task import AgentTeamTask
from app.runtime.thread_resolver import new_agentscope_thread_id
from app.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
    record_agentscope_ref,
)


class AgentTeamTaskRunner(Protocol):
    async def stream(
        self,
        *,
        request: AgentTeamTaskRequest,
        task: AgentTeamTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]:
        ...


class AgentTeamTaskRuntime:
    """Agent Team 任务入口 runtime；调用方只消费 Datalogue envelope。"""

    def __init__(self, *, db: Session, runner: AgentTeamTaskRunner) -> None:
        self.db = db
        self.runner = runner

    async def stream(self, request: AgentTeamTaskRequest) -> AsyncIterator[DatalogueEventEnvelope]:
        selected_agent = "agent_team_leader"
        thread_id = request.thread_id or new_agentscope_thread_id()
        trace_id = f"trace-agent-team-{uuid.uuid4().hex}"
        log_lifecycle(
            "agent_team.task.received",
            trace_id=trace_id,
            task_source=request.task_source,
            task_type=request.task_type,
            dataset_id=request.dataset_id,
            selected_agent=selected_agent,
            question_length=len(request.question or ""),
        )
        task = self._create_task(
            request,
            selected_agent=selected_agent,
            thread_id=thread_id,
            trace_id=trace_id,
        )
        session = create_agentscope_session(
            self.db,
            thread_id=thread_id,
            title=request.question[:80],
            legacy_conversation_id=request.conversation_id,
            metadata={"task_id": task.task_id, "task_source": request.task_source},
        )
        append_user_message(
            self.db,
            thread_id=session.thread_id,
            content_summary=request.question,
            payload={"task_id": task.task_id, "question": request.question, "dataset_id": request.dataset_id},
        )
        assistant_message = create_running_assistant_message(
            self.db,
            thread_id=session.thread_id,
            lease_seconds=300,
        )
        # task 仍写入历史表；表名是兼容层，API/runtime 主语已迁到 Agent Team。
        task.agent_scope_session_id = session.thread_id
        task.thread_id = session.thread_id
        task.message_id = assistant_message.message_id
        self.db.add(task)
        self.db.flush()

        log_lifecycle(
            "agent_team.task.started",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            dataset_id=request.dataset_id,
        )
        yield build_task_envelope(
            event_type="task.started",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            payload={"summary": "Agent Team 任务已启动。"},
        )
        yield build_task_envelope(
            event_type="agent.selected",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            payload={
                "selected_agent": selected_agent,
                "task_type": request.task_type,
                "available_worker_types": ["bi", "report", "python", "audit"],
            },
        )

        accumulated_text = ""
        message_completed_emitted = False
        primary_artifact_ref: str | None = None
        latest_checkpoint_ref: str | None = None
        task_started_at = time.time()
        first_delta_at: float | None = None
        try:
            user_msg = UserMsg(name="user", content=request.question)
            async for event in self.runner.stream(request=request, task=task, user_msg=user_msg):
                envelope = project_agentscope_event(
                    event,
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                )
                if envelope.event_type in {"message.delta", "reasoning.delta"}:
                    if first_delta_at is None:
                        first_delta_at = time.time()
                    if envelope.event_type == "message.delta":
                        accumulated_text += str(envelope.payload.get("content") or "")
                if envelope.event_type == "message.completed":
                    message_completed_emitted = True
                    accumulated_text = str(envelope.payload.get("summary") or accumulated_text)
                    if first_delta_at is not None:
                        envelope.payload["timing"] = {
                            "ttft_ms": round((first_delta_at - task_started_at) * 1000),
                            "total_duration_ms": round((time.time() - task_started_at) * 1000),
                            "token_count": len(accumulated_text),
                        }
                    log_output(
                        event_type=envelope.event_type,
                        task_id=task.task_id,
                        trace_id=trace_id,
                        thread_id=session.thread_id,
                        message_id=assistant_message.message_id,
                        selected_agent=selected_agent,
                        summary=accumulated_text,
                        artifact_ref=envelope.payload.get("artifact_ref"),
                    )
                if envelope.event_type in {"artifact.created", "message.completed"}:
                    primary_artifact_ref = str(envelope.payload.get("artifact_ref") or primary_artifact_ref or "").strip() or None
                    latest_checkpoint_ref = str(envelope.payload.get("checkpoint_ref") or latest_checkpoint_ref or "").strip() or None
                log_lifecycle(
                    "agent_team.task.event",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    event_type=envelope.event_type,
                    selected_agent=selected_agent,
                )
                yield envelope

            mark_message_completed(
                self.db,
                message_id=assistant_message.message_id,
                content_summary=accumulated_text or "Agent Team 任务已完成。",
                payload={
                    "task_id": task.task_id,
                    "answer_summary": accumulated_text or "任务已完成。",
                    "artifact_ref": primary_artifact_ref,
                    "checkpoint_ref": latest_checkpoint_ref,
                },
            )
            self._record_completion_refs(
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                artifact_ref=primary_artifact_ref,
                checkpoint_ref=latest_checkpoint_ref,
            )
            task.status = "completed"
            task.final_payload_json = {
                "answer_summary": accumulated_text,
                "artifact_ref": primary_artifact_ref,
                "checkpoint_ref": latest_checkpoint_ref,
            }
            task.artifact_refs_json = _append_unique(task.artifact_refs_json, primary_artifact_ref)
            task.checkpoint_refs_json = _append_unique(task.checkpoint_refs_json, latest_checkpoint_ref)
            self.db.add(task)
            self.db.commit()
            log_lifecycle(
                "agent_team.task.completed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                emitted_message_completed=message_completed_emitted,
            )
            if not message_completed_emitted:
                log_output(
                    event_type="message.completed",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                    summary=accumulated_text or "任务已完成。",
                )
                yield build_task_envelope(
                    event_type="message.completed",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                    payload={
                        "summary": accumulated_text or "任务已完成。",
                        "timing": {
                            "ttft_ms": round((first_delta_at - task_started_at) * 1000) if first_delta_at else 0,
                            "total_duration_ms": round((time.time() - task_started_at) * 1000),
                            "token_count": len(accumulated_text),
                        },
                    },
                    legacy_payload={"type": "final", "answer": accumulated_text},
                )
            yield build_task_envelope(
                event_type="task.completed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                payload={"summary": "Agent Team 任务已完成。"},
            )
        except Exception:
            log_output(
                event_type="task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                error_code="AGENT_TEAM_TASK_FAILED",
                error_summary="Agent Team 任务执行失败，内部细节已隐藏。",
            )
            log_lifecycle(
                "agent_team.task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                error_code="AGENT_TEAM_TASK_FAILED",
            )
            mark_message_failed(
                self.db,
                message_id=assistant_message.message_id,
                error_summary="Agent Team 任务执行失败，内部细节已隐藏。",
                payload={"task_id": task.task_id, "error_code": "AGENT_TEAM_TASK_FAILED"},
            )
            task.status = "failed"
            task.error_payload_json = {"error_code": "AGENT_TEAM_TASK_FAILED"}
            self.db.add(task)
            self.db.commit()
            yield build_task_envelope(
                event_type="task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                payload={
                    "error_code": "AGENT_TEAM_TASK_FAILED",
                    "error_summary": "Agent Team 任务执行失败，内部细节已隐藏。",
                    "retryable": True,
                },
            )

    def _create_task(
        self,
        request: AgentTeamTaskRequest,
        *,
        selected_agent: str,
        thread_id: str,
        trace_id: str,
    ) -> AgentTeamTask:
        task = AgentTeamTask(
            task_id=f"task-agent-team-{uuid.uuid4().hex}",
            task_source=request.task_source,
            task_type=request.task_type,
            status="running",
            selected_agent=selected_agent,
            thread_id=thread_id,
            trace_id=trace_id,
            artifact_refs_json=[request.artifact_ref] if request.artifact_ref else [],
            checkpoint_refs_json=[request.retry_checkpoint_ref] if request.retry_checkpoint_ref else [],
            request_payload_json=request.model_dump(),
        )
        self.db.add(task)
        self.db.flush()
        return task

    def _record_completion_refs(
        self,
        *,
        thread_id: str,
        message_id: str,
        artifact_ref: str | None,
        checkpoint_ref: str | None,
    ) -> None:
        if artifact_ref:
            _record_agentscope_ref_once(
                self.db,
                thread_id=thread_id,
                message_id=message_id,
                ref_type="artifact",
                ref_value=artifact_ref,
                relation="primary",
            )
        if checkpoint_ref:
            _record_agentscope_ref_once(
                self.db,
                thread_id=thread_id,
                message_id=message_id,
                ref_type="checkpoint",
                ref_value=checkpoint_ref,
                relation="latest",
            )


def _append_unique(values: list[str] | None, value: str | None) -> list[str]:
    existing = list(values or [])
    if value and value not in existing:
        existing.append(value)
    return existing


def _record_agentscope_ref_once(
    db: Session,
    *,
    thread_id: str,
    message_id: str,
    ref_type: str,
    ref_value: str,
    relation: str,
) -> None:
    try:
        record_agentscope_ref(
            db,
            thread_id=thread_id,
            message_id=message_id,
            ref_type=ref_type,
            ref_value=ref_value,
            relation=relation,
        )
    except ValueError as exc:
        if str(exc) != "AGENTSCOPE_REF_ALREADY_EXISTS":
            raise
