# ============================================================
# File Name   : agentic_shell_task_runtime.py
# Description:
#   Agentic Shell 统一任务入口运行时。
#
# Responsibilities:
#   - 创建 AgenticShellTask 真相源、AgentScope mirror session/message 和 task 生命周期事件。
#   - 驱动 AgentScope runner，并将原生事件投影为 Datalogue envelope。
#   - 在异常路径写入安全失败状态，禁止回退到旧 chat stream 入口。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app import schemas
from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.agentic_shell_event_projection import build_task_envelope, project_agentscope_event
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
)
from app.services.agentscope_thread_resolver import new_agentscope_thread_id


class AgentScopeTaskRunner(Protocol):
    async def stream(
        self,
        *,
        request: AgenticShellTaskRequest,
        task: AgenticShellTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]:
        ...


class LegacyWorkflowTaskRunner:
    """迁移期执行适配器：入口 ownership 归 Agentic Shell，真实 BI 执行体临时复用现有 service runtime。"""

    def __init__(
        self,
        *,
        legacy_stream_factory: Callable[[schemas.ChatRequest], AsyncIterator[dict[str, Any]]],
    ) -> None:
        self.legacy_stream_factory = legacy_stream_factory

    async def stream(
        self,
        *,
        request: AgenticShellTaskRequest,
        task: AgenticShellTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]:
        chat_payload = schemas.ChatRequest(
            question=request.question,
            thread_id=request.thread_id,
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            dataset_id=request.dataset_id,
            clarification_response=request.clarification_response,
            retry_checkpoint_ref=request.retry_checkpoint_ref,
        )
        async for legacy_event in self.legacy_stream_factory(chat_payload):
            yield legacy_event


class AgenticShellTaskRuntime:
    """统一任务入口 runtime；调用方只消费 Datalogue envelope。"""

    def __init__(self, *, db: Session, runner: AgentScopeTaskRunner) -> None:
        self.db = db
        self.runner = runner

    async def stream(self, request: AgenticShellTaskRequest) -> AsyncIterator[DatalogueEventEnvelope]:
        shell = DatalogueAgenticShell()
        contract = shell.prepare_turn(question=request.question, context=request.model_dump())
        selected_agent = contract.selected_agent
        thread_id = request.thread_id or new_agentscope_thread_id()
        trace_id = f"trace-agentic-{uuid.uuid4().hex}"
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
        # 把 session/message 关联写回 task 后只做一次 commit，减少 DB 往返。
        task.agent_scope_session_id = session.thread_id
        task.thread_id = session.thread_id
        task.message_id = assistant_message.message_id
        self.db.add(task)
        self.db.flush()  # 发 SQL 但不提交事务，后续失败时整体回滚

        yield build_task_envelope(
            event_type="task.started",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            payload={"summary": "Agentic Shell 任务已启动。"},
        )
        yield build_task_envelope(
            event_type="agent.selected",
            task_id=task.task_id,
            trace_id=trace_id,
            thread_id=session.thread_id,
            message_id=assistant_message.message_id,
            selected_agent=selected_agent,
            payload={"selected_agent": selected_agent, "task_type": request.task_type},
        )

        accumulated_text = ""
        message_completed_emitted = False
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
                if envelope.event_type == "message.delta":
                    accumulated_text += str(envelope.payload.get("content") or "")
                if envelope.event_type == "message.completed":
                    message_completed_emitted = True
                    accumulated_text = str(envelope.payload.get("summary") or accumulated_text)
                yield envelope

            mark_message_completed(
                self.db,
                message_id=assistant_message.message_id,
                content_summary=accumulated_text or "Agentic Shell 任务已完成。",
                payload={"task_id": task.task_id, "answer_summary": accumulated_text or "任务已完成。"},
            )
            task.status = "completed"
            task.final_payload_json = {"answer_summary": accumulated_text}
            self.db.add(task)
            self.db.commit()
            if not message_completed_emitted:
                yield build_task_envelope(
                    event_type="message.completed",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                    payload={"summary": accumulated_text or "任务已完成。"},
                    legacy_payload={"type": "final", "answer": accumulated_text},
                )
            yield build_task_envelope(
                event_type="task.completed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                payload={"summary": "Agentic Shell 任务已完成。"},
            )
        except Exception:
            mark_message_failed(
                self.db,
                message_id=assistant_message.message_id,
                error_summary="Agentic Shell 任务执行失败，内部细节已隐藏。",
                payload={"task_id": task.task_id, "error_code": "AGENTIC_SHELL_TASK_FAILED"},
            )
            task.status = "failed"
            task.error_payload_json = {"error_code": "AGENTIC_SHELL_TASK_FAILED"}
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
                    "error_code": "AGENTIC_SHELL_TASK_FAILED",
                    "error_summary": "Agentic Shell 任务执行失败，内部细节已隐藏。",
                    "retryable": True,
                },
            )

    def _create_task(
        self,
        request: AgenticShellTaskRequest,
        *,
        selected_agent: str,
        thread_id: str,
        trace_id: str,
    ) -> AgenticShellTask:
        task = AgenticShellTask(
            task_id=f"task-agentic-{uuid.uuid4().hex}",
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
        self.db.flush()  # 取得 task_id，事务由外层控制
        return task
