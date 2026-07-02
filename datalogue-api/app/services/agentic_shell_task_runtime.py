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

from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.schemas.bi_lead_agent import ConfirmBILeadAgentRunRequest, DatasetCapabilitySummary
from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.services.bi_lead_agent.confirmation_service import BILeadAgentConfirmationService
from app.services.bi_lead_agent.handoff_service import BIHandoffService
from app.services.bi_lead_agent.run_service import BILeadAgentRunService
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


class BILeadAgentTaskRunner:
    """Agentic Shell 的 BI 执行 runner；只通过 BI LeadAgent handoff 契约进入 DatasetAgent。"""

    def __init__(
        self,
        *,
        db: Session,
        run_service_factory: Callable[[Session], BILeadAgentRunService] = BILeadAgentRunService,
        confirmation_service_factory: Callable[[Session], BILeadAgentConfirmationService] = BILeadAgentConfirmationService,
        handoff_service_factory: Callable[[Session], BIHandoffService] = BIHandoffService,
    ) -> None:
        self.db = db
        self.run_service_factory = run_service_factory
        self.confirmation_service_factory = confirmation_service_factory
        self.handoff_service_factory = handoff_service_factory

    async def stream(
        self,
        *,
        request: AgenticShellTaskRequest,
        task: AgenticShellTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]:
        if request.dataset_id is None:
            summary = "请选择一个数据集后再执行 BI 查询。"
            yield build_task_envelope(
                event_type="clarification.required",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={
                    "summary": summary,
                    "reason": "dataset_required",
                },
            )
            yield build_task_envelope(
                event_type="message.completed",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={"summary": summary},
                legacy_payload={"type": "final", "answer": summary},
            )
            return

        run_service = self.run_service_factory(self.db)
        confirmation_service = self.confirmation_service_factory(self.db)
        handoff_service = self.handoff_service_factory(self.db)

        bi_run = run_service.create_run(
            question=request.question,
            trace_id=task.trace_id,
            task_id=task.task_id,
        )
        confirmation_service.confirm(
            bi_run.id,
            ConfirmBILeadAgentRunRequest(
                dataset_id=request.dataset_id,
                confirmed_question=request.question,
                task_goal="执行单数据集问数",
                capability_snapshot=DatasetCapabilitySummary(
                    dataset_id=request.dataset_id,
                    name=f"数据集 {request.dataset_id}",
                    availability="confirmed",
                ),
                routing_rationale="Agentic Shell 已收到显式数据集，直接交接给 BI LeadAgent/DatasetAgent。",
                risk_notice="本次只执行已确认数据集上的只读查询。",
                user_decision="approved",
            ),
        )

        yield build_task_envelope(
            event_type="agent.handoff.started",
            task_id=task.task_id,
            trace_id=task.trace_id,
            thread_id=task.thread_id,
            message_id=task.message_id,
            selected_agent=task.selected_agent,
            payload={
                "summary": "BI LeadAgent 已确认数据集，正在交接 DatasetAgent。",
                "parent_agent": "bi_lead_agent",
                "child_agent": "dataset_agent",
                "dataset_id": request.dataset_id,
            },
        )

        result = await handoff_service.query_dataset(run_id=bi_run.id)
        summary = (
            result.answer_summary
            or result.error_summary
            or ("BI LeadAgent handoff 已完成。" if result.handoff_status == "completed" else "BI LeadAgent handoff 已结束。")
        )
        if result.artifact_ref:
            yield build_task_envelope(
                event_type="artifact.created",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={
                    "summary": "BI 查询产物已生成。",
                    "artifact_ref": result.artifact_ref,
                    "checkpoint_ref": result.checkpoint_ref,
                    "row_count": result.row_count,
                    "column_count": result.column_count,
                },
            )

        yield build_task_envelope(
            event_type="message.completed",
            task_id=task.task_id,
            trace_id=task.trace_id,
            thread_id=task.thread_id,
            message_id=task.message_id,
            selected_agent=task.selected_agent,
            payload={
                "summary": summary,
                "handoff_status": result.handoff_status,
                "artifact_ref": result.artifact_ref,
                "checkpoint_ref": result.checkpoint_ref,
                "row_count": result.row_count,
                "column_count": result.column_count,
            },
            legacy_payload={"type": "final", "answer": summary},
        )


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
