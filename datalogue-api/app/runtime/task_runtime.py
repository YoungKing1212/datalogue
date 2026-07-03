# ============================================================
# File Name   : task_runtime.py
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
from app.schemas.bi_agent import ConfirmBIAgentRunRequest, DatasetCapabilitySummary
from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.agents.bi_agent import BIAgentConfirmationService, BIAgentRunService
from app.agents.agentic_lead_agent import AgenticLeadAgent
from app.agents.agentic_lead_agent.direct_query_runner import AgenticDirectQueryRunner
from app.events.projection import build_task_envelope, project_agentscope_event
from app.middlewares.lifecycle import log_lifecycle, log_output, log_raw
from app.services.dataset_router import route_dataset_for_question
from app.services.agentscope_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
    record_agentscope_ref,
)
from app.runtime.thread_resolver import new_agentscope_thread_id


class AgentScopeTaskRunner(Protocol):
    async def stream(
        self,
        *,
        request: AgenticShellTaskRequest,
        task: AgenticShellTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]:
        ...


class BIAgentTaskRunner:
    """Agentic Shell 的 BI 执行 runner；由 BI Agent 直接驱动 Dataset 查询工具链。"""

    def __init__(
        self,
        *,
        db: Session,
        run_service_factory: Callable[[Session], BIAgentRunService] = BIAgentRunService,
        confirmation_service_factory: Callable[[Session], BIAgentConfirmationService] = BIAgentConfirmationService,
        direct_query_runner_factory: Callable[..., AgenticDirectQueryRunner] = AgenticDirectQueryRunner,
    ) -> None:
        self.db = db
        self.run_service_factory = run_service_factory
        self.confirmation_service_factory = confirmation_service_factory
        self.direct_query_runner_factory = direct_query_runner_factory

    async def stream(
        self,
        *,
        request: AgenticShellTaskRequest,
        task: AgenticShellTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]:
        log_lifecycle(
            "bi_agent.io.input",
            task_id=task.task_id,
            trace_id=task.trace_id,
            selected_agent=task.selected_agent,
            dataset_id=request.dataset_id,
            question_length=len(request.question or ""),
        )
        # 调试开关打开时打印 Runtime 收到的原始请求，便于确认 Dataset Query Skill 的真实入参。
        log_raw(
            "bi_agent.raw.input",
            task_id=task.task_id,
            trace_id=task.trace_id,
            selected_agent=task.selected_agent,
            request=request.model_dump(),
        )
        log_lifecycle(
            "bi_agent.runner.started",
            task_id=task.task_id,
            trace_id=task.trace_id,
            dataset_id=request.dataset_id,
        )
        route_decision = route_dataset_for_question(
            self.db,
            request.question,
            dataset_id=request.dataset_id,
        )
        effective_dataset_id = _selected_dataset_id_from_route(route_decision) or request.dataset_id
        log_lifecycle(
            "bi_agent.runner.dataset_route_decision",
            task_id=task.task_id,
            trace_id=task.trace_id,
            decision=route_decision.get("decision"),
            dataset_id=effective_dataset_id,
            candidate_count=len(route_decision.get("candidates") or []),
            score=route_decision.get("score"),
        )

        if effective_dataset_id is None:
            summary = _dataset_selection_summary(route_decision)
            clarification = _dataset_selection_clarification(task.task_id, route_decision)
            log_lifecycle(
                "bi_agent.reasoning.decision",
                task_id=task.task_id,
                trace_id=task.trace_id,
                selected_subagent=None,
                decision=route_decision.get("decision") or "dataset_required",
            )
            log_lifecycle(
                "bi_agent.runner.dataset_selection_required",
                task_id=task.task_id,
                trace_id=task.trace_id,
                candidate_count=len(route_decision.get("candidates") or []),
            )
            yield build_task_envelope(
                event_type="clarification.required",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={
                    "summary": summary,
                    "reason": route_decision.get("reason") or "dataset_required",
                    "route_decision": route_decision,
                    "clarification": clarification,
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
                    "route_decision": route_decision,
                    "clarification": clarification,
                },
                legacy_payload={
                    "type": "final",
                    "answer": summary,
                    "route_decision": route_decision,
                    "clarification": clarification,
                },
            )
            return

        if request.dataset_id is None or request.clarification_response:
            yield build_task_envelope(
                event_type="dataset.selected",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={
                    "summary": _dataset_selected_summary(route_decision, effective_dataset_id),
                    "route_decision": route_decision,
                },
            )

        run_service = self.run_service_factory(self.db)
        confirmation_service = self.confirmation_service_factory(self.db)
        direct_query_runner = self.direct_query_runner_factory(db=self.db)

        bi_run = run_service.create_run(
            question=request.question,
            trace_id=task.trace_id,
            task_id=task.task_id,
        )
        capability_snapshot = _dataset_capability_snapshot(route_decision, effective_dataset_id)
        log_lifecycle(
            "bi_agent.runner.run_created",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=effective_dataset_id,
        )
        confirmation_service.confirm(
            bi_run.id,
            ConfirmBIAgentRunRequest(
                dataset_id=effective_dataset_id,
                confirmed_question=request.question,
                task_goal="执行单数据集问数",
                capability_snapshot=capability_snapshot,
                routing_rationale=_routing_rationale(request=request, route_decision=route_decision),
                risk_notice="本次只执行已确认数据集上的只读查询。",
                user_decision="approved",
            ),
        )
        log_lifecycle(
            "bi_agent.runner.confirmed",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=effective_dataset_id,
        )

        log_lifecycle(
            "bi_agent.reasoning.decision",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=effective_dataset_id,
            selected_subagent=None,
            decision="confirmed_dataset_query_direct",
        )
        log_lifecycle(
            "bi_agent.runner.query.started",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=effective_dataset_id,
        )
        yield build_task_envelope(
            event_type="dataset.query.started",
            task_id=task.task_id,
            trace_id=task.trace_id,
            thread_id=task.thread_id,
            message_id=task.message_id,
            selected_agent=task.selected_agent,
            payload={
                "summary": "BI Agent 已确认数据集，正在执行 Dataset 查询工具链。",
                "parent_agent": "bi_agent",
                "query_executor": "bi_agent_direct_query",
                "dataset_id": effective_dataset_id,
                "route_decision": route_decision,
            },
        )

        direct_query_kwargs = {
            "question": request.question,
            "dataset_id": effective_dataset_id,
            "conversation_id": request.conversation_id,
            "trace_id": task.trace_id,
        }
        if request.model_config_id is not None:
            # Shell 路径复用 direct-query runner；模型选择必须跟随本轮用户请求传入内层执行链路。
            direct_query_kwargs["model_config_id"] = request.model_config_id
        result = await direct_query_runner.run(**direct_query_kwargs)
        query_status = _direct_query_status(result)
        _mark_bi_run_from_direct_result(run_service=run_service, run=bi_run, result=result)
        log_lifecycle(
            "bi_agent.runner.query.completed",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=effective_dataset_id,
            query_status=query_status,
            error_code=result.get("code"),
            has_artifact=bool(result.get("artifact_ref")),
            row_count=result.get("row_count"),
            column_count=result.get("column_count"),
        )
        summary = (
            _safe_result_text(result.get("summary"))
            or _safe_result_text(result.get("error_summary"))
            or ("BI Agent 查询已完成。" if query_status == "completed" else "BI Agent 查询已结束。")
        )
        log_lifecycle(
            "bi_agent.io.output",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=effective_dataset_id,
            query_status=query_status,
            error_code=result.get("code"),
            artifact_ref=result.get("artifact_ref"),
            checkpoint_ref=result.get("checkpoint_ref"),
            row_count=result.get("row_count"),
            column_count=result.get("column_count"),
        )
        # 调试阶段需要看真实 Skill 输出；默认关闭，避免生产日志长期持有查询细节。
        log_raw(
            "bi_agent.raw.output",
            task_id=task.task_id,
            trace_id=task.trace_id,
            bi_run_id=bi_run.id,
            dataset_id=request.dataset_id,
            query_status=query_status,
            result=_safe_direct_result(result),
        )
        if result.get("artifact_ref"):
            yield build_task_envelope(
                event_type="artifact.created",
                task_id=task.task_id,
                trace_id=task.trace_id,
                thread_id=task.thread_id,
                message_id=task.message_id,
                selected_agent=task.selected_agent,
                payload={
                    "summary": "BI 查询产物已生成。",
                    "artifact_ref": result.get("artifact_ref"),
                    "checkpoint_ref": result.get("checkpoint_ref"),
                    "row_count": result.get("row_count"),
                    "column_count": result.get("column_count"),
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
                "query_status": query_status,
                "artifact_ref": result.get("artifact_ref"),
                "checkpoint_ref": result.get("checkpoint_ref"),
                "route_decision": route_decision,
                "row_count": result.get("row_count"),
                "column_count": result.get("column_count"),
            },
            legacy_payload={"type": "final", "answer": summary},
        )


class AgenticShellTaskRuntime:
    """统一任务入口 runtime；调用方只消费 Datalogue envelope。"""

    def __init__(self, *, db: Session, runner: AgentScopeTaskRunner) -> None:
        self.db = db
        self.runner = runner

    async def stream(self, request: AgenticShellTaskRequest) -> AsyncIterator[DatalogueEventEnvelope]:
        shell = AgenticLeadAgent()
        contract = shell.prepare_turn(question=request.question, context=request.model_dump())
        selected_agent = contract.selected_agent
        thread_id = request.thread_id or new_agentscope_thread_id()
        trace_id = f"trace-agentic-{uuid.uuid4().hex}"
        log_lifecycle(
            "agentic_lead_agent.task.received",
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
        # 把 session/message 关联写回 task 后只做一次 commit，减少 DB 往返。
        task.agent_scope_session_id = session.thread_id
        task.thread_id = session.thread_id
        task.message_id = assistant_message.message_id
        self.db.add(task)
        self.db.flush()  # 发 SQL 但不提交事务，后续失败时整体回滚

        log_lifecycle(
            "agentic_lead_agent.task.started",
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
        primary_artifact_ref: str | None = None
        latest_checkpoint_ref: str | None = None
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
                    # refs 是 Workbench/历史回放的结果入口；事件流携带后必须同步沉淀为镜像引用。
                    primary_artifact_ref = str(envelope.payload.get("artifact_ref") or primary_artifact_ref or "").strip() or None
                    latest_checkpoint_ref = str(envelope.payload.get("checkpoint_ref") or latest_checkpoint_ref or "").strip() or None
                log_lifecycle(
                    "agentic_lead_agent.task.event",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    event_type=envelope.event_type,
                    selected_agent=selected_agent,
                )
                yield envelope

            mark_message_completed(
                self.db,
                message_id=assistant_message.message_id,
                content_summary=accumulated_text or "Agentic Shell 任务已完成。",
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
                "agentic_lead_agent.task.completed",
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
            log_output(
                event_type="task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                error_code="AGENTIC_SHELL_TASK_FAILED",
                error_summary="Agentic Shell 任务执行失败，内部细节已隐藏。",
            )
            log_lifecycle(
                "agentic_lead_agent.task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                error_code="AGENTIC_SHELL_TASK_FAILED",
            )
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


def _direct_query_status(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "").strip().lower()
    if status in {"completed", "blocked", "failed", "cancelled"}:
        return status
    if result.get("artifact_ref") and not result.get("code"):
        return "completed"
    return "blocked"


def _safe_result_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_direct_result(result: dict[str, Any]) -> dict[str, Any]:
    safe_keys = {
        "status",
        "selected_agent",
        "summary",
        "artifact_ref",
        "checkpoint_ref",
        "row_count",
        "column_count",
        "code",
    }
    return {key: result.get(key) for key in safe_keys if result.get(key) is not None}


def _mark_bi_run_from_direct_result(*, run_service: BIAgentRunService, run: Any, result: dict[str, Any]) -> None:
    if not hasattr(run_service, "mark_phase"):
        return
    status = _direct_query_status(result)
    status_reason = str(result.get("code") or f"direct_query_{status}")
    # BI run 现在只记录外层审计终态；查询明细仍由 direct-query artifact/checkpoint 引用承接。
    run_service.mark_phase(
        run,
        phase="summarize_run",
        status=status,
        status_reason=status_reason,
    )


def _selected_dataset_id_from_route(route_decision: dict[str, Any]) -> int | None:
    dataset_id = route_decision.get("dataset_id")
    if isinstance(dataset_id, bool) or dataset_id is None:
        return None
    try:
        parsed = int(dataset_id)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_route_candidates(route_decision: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in (route_decision.get("candidates") or [])[:3]:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "dataset_id": item.get("dataset_id"),
                "dataset_name": item.get("dataset_name"),
                "reason": item.get("reason"),
                "confidence": item.get("confidence"),
                "requires_confirmation": item.get("requires_confirmation") is True,
            }
        )  # 用户选择卡片只需要 capability 摘要，不能携带字段、SQL、资产详情。
    return candidates


def _dataset_selection_summary(route_decision: dict[str, Any]) -> str:
    candidates = _safe_route_candidates(route_decision)
    if candidates:
        return "BI Agent 已找到候选数据集，但证据不足以自动选择，请先确认要查询的数据集。"
    return "BI Agent 暂时没有找到可自动选择的数据集，请先选择一个数据集后再执行查询。"


def _dataset_selected_summary(route_decision: dict[str, Any], dataset_id: int) -> str:
    candidate = _route_candidate_for_dataset(route_decision, dataset_id)
    name = candidate.get("dataset_name") if candidate else None
    if route_decision.get("decision") == "selected":
        return f"BI Agent 已自动选择数据集「{name or dataset_id}」。"
    if route_decision.get("decision") == "locked":
        return f"BI Agent 已使用用户确认的数据集「{name or dataset_id}」。"
    return f"BI Agent 已确认数据集「{name or dataset_id}」。"


def _dataset_selection_clarification(task_id: str, route_decision: dict[str, Any]) -> dict[str, Any]:
    decision = str(route_decision.get("decision") or "")
    kind = "dataset_choice" if decision == "ambiguous" else "dataset_missing"
    return {
        "kind": kind,
        "clarificationId": f"{task_id}:dataset-selection",
        "candidates": _safe_route_candidates(route_decision),
    }


def _route_candidate_for_dataset(route_decision: dict[str, Any], dataset_id: int) -> dict[str, Any]:
    for item in _safe_route_candidates(route_decision):
        try:
            if int(item.get("dataset_id")) == int(dataset_id):
                return item
        except (TypeError, ValueError):
            continue
    return {}


def _dataset_capability_snapshot(route_decision: dict[str, Any], dataset_id: int) -> DatasetCapabilitySummary:
    candidate = _route_candidate_for_dataset(route_decision, dataset_id)
    return DatasetCapabilitySummary(
        dataset_id=dataset_id,
        name=str(candidate.get("dataset_name") or route_decision.get("dataset_name") or f"数据集 {dataset_id}"),
        availability="confirmed",
    )


def _routing_rationale(*, request: AgenticShellTaskRequest, route_decision: dict[str, Any]) -> str:
    if request.clarification_response:
        return "用户已通过 AgentScope 人机交互卡片确认数据集，交接给 BI Agent 的 Dataset 查询 Skill。"
    if request.dataset_id is not None:
        return "Agentic Shell 已收到显式数据集，直接交接给 BI Agent 的 Dataset 查询 Skill。"
    return route_decision.get("reason") or "BI Agent 基于 current Manifest 自动选择数据集。"


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
