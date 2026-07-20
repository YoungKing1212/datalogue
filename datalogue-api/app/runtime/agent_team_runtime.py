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

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

from agentscope.message import UserMsg
from opentelemetry.trace import Status, StatusCode
from sqlalchemy.orm import Session

from app.core.observability import observation_span, set_span_attributes
from app.core.config import get_settings
from app.core.middlewares.lifecycle import log_lifecycle, log_output
from app.runtime.thread_resolver import new_runtime_thread_id
from app.domains.agent_team.contracts import AgentTeamTask, AgentTeamTaskRequest
from app.domains.agent_team.event_projection import (
    DatalogueEventEnvelope,
    build_task_envelope,
    project_agentscope_event,
)
from app.runtime.engine.registry import available_datalogue_worker_types
from app.domains.agent_team.report_execution import (
    ReportExecutionState,
    ReportExecutionStatus,
    ReportWorkerRequiredNotCompletedError,
)
from app.services.runtime_mirror import (
    append_user_message,
    create_agentscope_session,
    create_running_assistant_message,
    mark_message_completed,
    mark_message_failed,
    mark_message_interrupted,
    record_agentscope_ref,
)

logger = logging.getLogger(__name__)

_INTERNAL_PLANNING_TEXT_RE = re.compile(
    r"\b(the\s+user\s+wants?\s+to|let\s+me\s+break|i\s+need\s+to\s+create|"
    r"worker\s+type\s+should\s+be|i\s+should\s+present|teamsay)\b",
    re.IGNORECASE,
)
_INTERNAL_PLANNING_COMPACT_MARKERS = (
    "theuserwantstoquery",
    "letmebreakthisdown",
    "ineedtocreate",
    "theworkertypeshouldbe",
    "bothhaveascore",
    "ishouldpresent",
    "taskcompletedteamdissolved",
)


def _looks_like_internal_planning_text(value: Any) -> bool:
    """识别误入 final answer 的 Agent 协调/规划文本，避免暴露到聊天栏。"""

    text = str(value or "").strip()
    if not text:
        return False
    compact = re.sub(r"[^a-z0-9]+", "", text.lower())
    return _INTERNAL_PLANNING_TEXT_RE.search(text) is not None or any(
        marker in compact for marker in _INTERNAL_PLANNING_COMPACT_MARKERS
    )


def _safe_summary_text(value: Any, *, limit: int = 180) -> str | None:
    """把 runtime 事件摘要收敛成用户可见短文本，避免把复杂对象直接放进聊天层。"""

    text = str(value or "").strip()
    if not text:
        return None
    if _looks_like_internal_planning_text(text):
        return None
    return text[:limit]


def _append_reasoning_summary_step(
    steps: list[dict[str, Any]],
    *,
    title: str,
    summary: Any,
    status: str = "completed",
    ref: str | None = None,
    row_count: Any = None,
    column_count: Any = None,
) -> None:
    """追加一条安全推理摘要；只保留业务解释、状态、引用和行列数。"""

    safe_summary = _safe_summary_text(summary)
    if not safe_summary:
        return
    step: dict[str, Any] = {
        "title": title,
        "summary": safe_summary,
        "status": status,
    }
    if ref:
        step["ref"] = str(ref).strip()
    if isinstance(row_count, int) and row_count >= 0:
        step["row_count"] = row_count
    if isinstance(column_count, int) and column_count >= 0:
        step["column_count"] = column_count
    steps.append(step)


def _seed_reasoning_summary(request: AgentTeamTaskRequest) -> list[dict[str, Any]]:
    """为每轮任务提供稳定的第一条业务推理摘要。"""

    task_type_label = {
        "bi_query": "BI 查询",
        "report": "报告生成",
        "python_analysis": "Python 分析",
        "audit": "审计检查",
        "unsupported": "暂不支持",
    }.get(request.task_type, "任务")
    return [
        {
            "title": "识别任务",
            "summary": f"已识别为「{task_type_label}」任务，问题为「{request.question[:80]}」。",
            "status": "completed",
        }
    ]


def _collect_reasoning_summary_step(
    steps: list[dict[str, Any]],
    *,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """从稳定事件协议里提取可公开的推理摘要，不读取内部执行体。"""

    if event_type == "dataset.selected":
        route_decision = (
            payload.get("route_decision") if isinstance(payload.get("route_decision"), dict) else {}
        )
        dataset_name = route_decision.get("dataset_name") or payload.get("dataset_name")
        dataset_id = route_decision.get("dataset_id") or payload.get("dataset_id")
        label = dataset_name or (f"数据集 {dataset_id}" if dataset_id else "候选数据集")
        _append_reasoning_summary_step(
            steps,
            title="选择数据集",
            summary=f"已选择「{label}」作为本轮查询数据集。",
        )
    elif event_type == "clarification.required":
        _append_reasoning_summary_step(
            steps,
            title="需要确认",
            summary=payload.get("summary") or "候选数据集不唯一，需要用户确认后继续。",
            status="requires_action",
        )
    elif event_type == "tool_call.completed":
        _append_reasoning_summary_step(
            steps,
            title="执行查询",
            summary=payload.get("summary") or "BI 工具已完成查询处理。",
            row_count=payload.get("row_count"),
        )
    elif event_type == "artifact.created":
        _append_reasoning_summary_step(
            steps,
            title="生成结果",
            summary=payload.get("summary") or "已生成可查看的查询结果。",
            ref=payload.get("artifact_ref") or payload.get("result_ref"),
            row_count=payload.get("row_count"),
            column_count=payload.get("column_count"),
        )


def _artifact_ref_from_final_payload(payload: dict[str, Any]) -> str | None:
    """从 final payload 或 ArtifactCard 中提取可见结果引用。"""

    direct_ref = payload.get("artifact_ref") or payload.get("result_ref")
    if direct_ref:
        return str(direct_ref).strip() or None
    artifact_card = payload.get("artifact_card")
    if not isinstance(artifact_card, dict):
        return None
    primary_ref = artifact_card.get("primary_ref") or artifact_card.get("primaryRef")
    if isinstance(primary_ref, str):
        return primary_ref.strip() or None
    if isinstance(primary_ref, dict):
        ref = primary_ref.get("ref_id") or primary_ref.get("ref") or primary_ref.get("artifact_ref")
        return str(ref).strip() if ref else None
    return None


def _has_reasoning_step(steps: list[dict[str, Any]], title: str) -> bool:
    return any(step.get("title") == title for step in steps)


def _iter_candidate_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """从候选数据集协议中提取最多 5 条可见候选项。"""

    route_decision = (
        payload.get("route_decision") if isinstance(payload.get("route_decision"), dict) else {}
    )
    clarification = (
        payload.get("clarification") if isinstance(payload.get("clarification"), dict) else {}
    )
    candidates = (
        route_decision.get("candidates")
        or clarification.get("candidates")
        or payload.get("candidates")
        or []
    )
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates[:5] if isinstance(candidate, dict)]


def _format_dataset_candidate(candidate: dict[str, Any], index: int) -> str:
    dataset_id = candidate.get("dataset_id")
    dataset_name = candidate.get("dataset_name") or candidate.get("name") or "未命名数据集"
    reason = str(candidate.get("reason") or "").strip()
    prefix = (
        f"{index}. 数据集 {dataset_id}：{dataset_name}"
        if dataset_id is not None
        else f"{index}. {dataset_name}"
    )
    return f"{prefix}（{reason}）" if reason else prefix


def _requires_dataset_confirmation(payload: dict[str, Any]) -> bool:
    route_decision = (
        payload.get("route_decision") if isinstance(payload.get("route_decision"), dict) else {}
    )
    clarification = (
        payload.get("clarification") if isinstance(payload.get("clarification"), dict) else {}
    )
    return (
        payload.get("datalogue_event_type") == "dataset_candidates"
        or route_decision.get("decision") in {"ambiguous", "no_match"}
        or clarification.get("kind") in {"dataset_choice", "dataset_confirmation"}
    )


def _dataset_confirmation_answer(payload: dict[str, Any]) -> str:
    candidates = _iter_candidate_items(payload)
    if not candidates:
        return "候选数据集不唯一，需要你确认后继续。请回复要查询的数据集编号，或补充查询范围。"
    candidate_lines = "\n".join(
        _format_dataset_candidate(candidate, index)
        for index, candidate in enumerate(candidates, start=1)
    )
    return (
        "已筛选出可能匹配的候选数据集，需要你确认后继续。\n\n"
        f"{candidate_lines}\n\n"
        "请回复要查询的数据集编号，或说明两个都需要查询。"
    )


def _artifact_completion_answer(payload: dict[str, Any], summary: str) -> str:
    artifact_card = (
        payload.get("artifact_card") if isinstance(payload.get("artifact_card"), dict) else {}
    )
    card_summary = str(
        artifact_card.get("summary_for_chat") or artifact_card.get("summary") or ""
    ).strip()
    for candidate in (card_summary, summary):
        if candidate and not _looks_like_internal_planning_text(candidate):
            return candidate
    row_count = payload.get("row_count")
    column_count = payload.get("column_count")
    if isinstance(row_count, int) and isinstance(column_count, int):
        return f"查询已完成，共 {row_count} 行、{column_count} 列。可通过查看详情打开完整结果。"
    if isinstance(row_count, int):
        return f"查询已完成，共 {row_count} 行。可通过查看详情打开完整结果。"
    return "查询已完成，已生成可查看的结果。"


def _visible_final_answer(payload: dict[str, Any], accumulated_text: str) -> str:
    """把 final payload 收敛成聊天栏可见正文；内部规划只能进入 trace，不能进入 answer。"""

    raw_summary = str(payload.get("summary") or accumulated_text or "").strip()
    if _requires_dataset_confirmation(payload):
        return _dataset_confirmation_answer(payload)
    if payload.get("datalogue_event_type") == "report_worker_result":
        report_markdown = str(payload.get("report_markdown") or "").strip()
        if report_markdown and not _looks_like_internal_planning_text(report_markdown):
            return report_markdown
        if raw_summary and not _looks_like_internal_planning_text(raw_summary):
            return raw_summary
        return "报告已生成，可通过查看详情打开完整内容。"
    if _artifact_ref_from_final_payload(payload):
        return _artifact_completion_answer(payload, raw_summary)
    if raw_summary and not _looks_like_internal_planning_text(raw_summary):
        return raw_summary
    return "任务已完成。"


def _is_runtime_query_artifact_payload(payload: dict[str, Any]) -> bool:
    """防御旧 Runner 把查询 Artifact 当作 final 的兼容判断。"""

    if payload.get("datalogue_event_type") == "report_worker_result":
        return False
    if _requires_dataset_confirmation(payload):
        return False
    return bool(_artifact_ref_from_final_payload(payload))


def _observe_runtime_report_event(
    state: ReportExecutionState,
    envelope: DatalogueEventEnvelope,
) -> None:
    """Runtime 仅依据公开 envelope 重建报告完成凭证，形成独立完成校验。"""

    payload = envelope.payload
    try:
        try:
            state.correction_count = max(
                state.correction_count,
                int(payload.get("report_correction_count") or 0),
            )
        except (TypeError, ValueError):
            pass
        if envelope.event_type == "artifact.created" and _is_runtime_query_artifact_payload(payload):
            source_ref = _artifact_ref_from_final_payload(payload)
            if source_ref:
                state.mark_required(source_ref)
        if payload.get("datalogue_event_type") != "report_worker_result":
            return
        if payload.get("status") != "completed":
            raise ReportWorkerRequiredNotCompletedError()
        source_ref = str(payload.get("source_artifact_ref") or "").strip()
        if not state.required:
            state.mark_required(source_ref)
        if state.status in {ReportExecutionStatus.PENDING, ReportExecutionStatus.FAILED}:
            state.mark_running(
                worker_agent_id=str(payload.get("report_worker_agent_id") or ""),
                worker_session_id=str(payload.get("report_worker_session_id") or ""),
            )
        state.mark_succeeded(
            source_artifact_ref=source_ref,
            report_ref=str(payload.get("report_ref") or ""),
            worker_agent_id=str(payload.get("report_worker_agent_id") or ""),
            worker_session_id=str(payload.get("report_worker_session_id") or ""),
        )
        try:
            state.attempt = max(state.attempt, int(payload.get("report_attempts") or 1))
        except (TypeError, ValueError):
            pass
    except (TypeError, ValueError) as exc:
        raise ReportWorkerRequiredNotCompletedError() from exc


def _report_completion_payload(state: ReportExecutionState) -> dict[str, Any]:
    if not state.required:
        return {}
    return {
        "report_required": state.required,
        "report_status": state.status.value,
        "report_ref": state.report_ref,
        "report_worker_agent_id": state.worker_agent_id,
        "report_worker_session_id": state.worker_session_id,
        "report_attempts": max(state.attempt, 1) if state.required else 0,
        "source_artifact_ref": state.source_artifact_ref,
    }


class AgentTeamTaskRunner(Protocol):
    async def stream(
        self,
        *,
        request: AgentTeamTaskRequest,
        task: AgentTeamTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[Any]: ...


async def _iterate_with_overall_timeout(
    events: AsyncIterator[Any],
    *,
    timeout_seconds: float,
) -> AsyncIterator[Any]:
    """按绝对截止时间消费流；每个事件不会重新获得一整段超时时间。"""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("agent team task deadline exceeded")
            try:
                yield await asyncio.wait_for(anext(events), timeout=remaining)
            except StopAsyncIteration:
                break
    finally:
        close = getattr(events, "aclose", None)
        if callable(close):
            await close()


class AgentTeamTaskRuntime:
    """Agent Team 任务入口 runtime；调用方只消费 Datalogue envelope。"""

    def __init__(
        self,
        *,
        db: Session,
        runner: AgentTeamTaskRunner,
        actor_user_id: int | None = None,
        task_timeout_seconds: float = 300.0,
    ) -> None:
        self.db = db
        self.runner = runner
        self.actor_user_id = actor_user_id
        self.task_timeout_seconds = max(float(task_timeout_seconds), 1.0)

    async def stream(self, request: AgentTeamTaskRequest) -> AsyncIterator[DatalogueEventEnvelope]:
        selected_agent = "agent_team_leader"
        thread_id = request.thread_id or new_runtime_thread_id()
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
            metadata={
                "task_id": task.task_id,
                "task_source": request.task_source,
                "user_id": self.actor_user_id,
            },
        )
        append_user_message(
            self.db,
            thread_id=session.thread_id,
            content_summary=request.question,
            payload={
                "task_id": task.task_id,
                "question": request.question,
                "dataset_id": request.dataset_id,
            },
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
        task_started_at = time.time()
        # 根 span 必须在首个 SSE 事件之前进入上下文，才能覆盖客户端断流等早期终止场景，
        # 并让后续 AgentScope HTTP/模型/工具调用都成为同一条链路的子 span。
        task_span_scope = observation_span(
            "datalogue.agent_team.task",
            {
                "datalogue.task_id": task.task_id,
                "datalogue.thread_id": session.thread_id,
                "datalogue.message_id": assistant_message.message_id,
                "datalogue.dataset_id": request.dataset_id,
                "datalogue.task_type": request.task_type,
                "datalogue.business_trace_id": trace_id,
            },
        )
        task_span = task_span_scope.__enter__()

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
                "available_worker_types": available_datalogue_worker_types(),
            },
        )
        accumulated_text = ""
        message_completed_emitted = False
        primary_artifact_ref: str | None = None
        report_ref: str | None = None
        latest_checkpoint_ref: str | None = None
        report_gate_enabled = bool(
            get_settings().DATALOGUE_REPORT_WORKER_ENABLED
            and request.task_type in {"bi_query", "report"}
        )
        report_state = ReportExecutionState()
        report_started_at: float | None = None
        if report_gate_enabled and request.task_type == "report" and request.artifact_ref:
            report_state.mark_required(request.artifact_ref)
        reasoning_summary_steps = _seed_reasoning_summary(request)
        first_delta_at: float | None = None
        try:
            user_msg = UserMsg(name="user", content=request.question)
            runner_events = self.runner.stream(request=request, task=task, user_msg=user_msg)
            async for event in _iterate_with_overall_timeout(
                runner_events,
                timeout_seconds=self.task_timeout_seconds,
            ):
                envelope = project_agentscope_event(
                    event,
                    task_id=task.task_id,
                    trace_id=trace_id,
                    thread_id=session.thread_id,
                    message_id=assistant_message.message_id,
                    selected_agent=selected_agent,
                )
                if (
                    report_gate_enabled
                    and envelope.event_type == "message.completed"
                    and _is_runtime_query_artifact_payload(envelope.payload)
                ):
                    # Runtime 是第二道独立闸门：即便自定义/旧 Runner 仍把查询 Artifact 投成 final，
                    # 这里也必须降为中间事件，禁止随后把 task 写成 completed。
                    envelope = envelope.model_copy(
                        update={"event_type": "artifact.created", "legacy_payload": {}}
                    )
                if report_gate_enabled:
                    _observe_runtime_report_event(report_state, envelope)
                    if report_state.required and report_started_at is None:
                        report_started_at = time.time()
                if envelope.event_type in {"message.delta", "reasoning.delta"}:
                    if first_delta_at is None:
                        first_delta_at = time.time()
                    if envelope.event_type == "message.delta":
                        accumulated_text += str(envelope.payload.get("content") or "")
                _collect_reasoning_summary_step(
                    reasoning_summary_steps,
                    event_type=envelope.event_type,
                    payload=envelope.payload,
                )
                if (
                    envelope.event_type == "message.completed"
                    and report_state.required
                    and not report_state.can_complete
                ):
                    # 不把非法 final 暴露给前端；流结束后由下方完成闸门统一收口为安全失败。
                    continue
                if envelope.event_type == "message.completed":
                    message_completed_emitted = True
                    accumulated_text = _visible_final_answer(envelope.payload, accumulated_text)
                    envelope.payload["summary"] = accumulated_text
                    if _requires_dataset_confirmation(
                        envelope.payload
                    ) and not envelope.payload.get("original_question"):
                        # 候选数据集确认后，前端需要用原始问题续跑；确认文案本身不能变成新的 BI 问题。
                        envelope.payload["original_question"] = request.question
                    envelope.legacy_payload = {"type": "final", "answer": accumulated_text}
                    final_artifact_ref = _artifact_ref_from_final_payload(envelope.payload)
                    if final_artifact_ref and not _has_reasoning_step(
                        reasoning_summary_steps, "生成结果"
                    ):
                        _append_reasoning_summary_step(
                            reasoning_summary_steps,
                            title="生成结果",
                            summary="已生成可查看的查询结果。",
                            ref=final_artifact_ref,
                            row_count=envelope.payload.get("row_count"),
                            column_count=envelope.payload.get("column_count"),
                        )
                    _append_reasoning_summary_step(
                        reasoning_summary_steps,
                        title="整理回答",
                        summary=accumulated_text or "任务已完成。",
                    )
                    if not envelope.payload.get("reasoning_summary"):
                        # message.completed 是聊天栏消费的最终协议，这里只注入安全业务摘要，不注入原始思维链。
                        envelope.payload["reasoning_summary"] = reasoning_summary_steps[:6]
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
                    event_artifact_ref = _artifact_ref_from_final_payload(envelope.payload)
                    if envelope.payload.get("datalogue_event_type") == "report_worker_result":
                        report_ref = str(envelope.payload.get("report_ref") or "").strip() or None
                    else:
                        primary_artifact_ref = event_artifact_ref or primary_artifact_ref
                    latest_checkpoint_ref = (
                        str(
                            envelope.payload.get("checkpoint_ref") or latest_checkpoint_ref or ""
                        ).strip()
                        or None
                    )
                log_lifecycle(
                    "agent_team.task.event",
                    task_id=task.task_id,
                    trace_id=trace_id,
                    event_type=envelope.event_type,
                    selected_agent=selected_agent,
                )
                yield envelope

            if report_gate_enabled and report_state.required and not report_state.can_complete:
                raise ReportWorkerRequiredNotCompletedError()
            if not message_completed_emitted:
                accumulated_text = _visible_final_answer({}, accumulated_text)
            final_answer = accumulated_text or "任务已完成。"
            mark_message_completed(
                self.db,
                message_id=assistant_message.message_id,
                content_summary=final_answer,
                payload={
                    "task_id": task.task_id,
                    "answer_summary": final_answer,
                    "reasoning_summary": [
                        {
                            "title": step["title"],
                            "summary": step["summary"],
                            "status": step["status"],
                            **({"ref": step["ref"]} if step.get("ref") else {}),
                        }
                        for step in reasoning_summary_steps[:6]
                    ],
                    "artifact_ref": primary_artifact_ref,
                    "checkpoint_ref": latest_checkpoint_ref,
                    **_report_completion_payload(report_state),
                },
            )
            # 自动生成会话标题（在后台线程执行，不阻塞主链路）
            if not getattr(task, "_title_generated", False):
                try:
                    from app.domains.agent_team.title_generator import maybe_auto_title_async

                    if get_settings().DATALOGUE_AUTO_TITLE_ENABLED:
                        maybe_auto_title_async(
                            session.thread_id,  # type: ignore[arg-type]
                            request.question,
                            final_answer,
                            legacy_conversation_id=request.conversation_id,
                        )
                        task._title_generated = True  # type: ignore[attr-defined]
                        self.db.add(task)
                        self.db.commit()
                except Exception:
                    pass
            self._record_completion_refs(
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                artifact_ref=primary_artifact_ref,
                report_ref=report_ref,
                checkpoint_ref=latest_checkpoint_ref,
            )
            task.status = "completed"
            task.final_payload_json = {
                "answer_summary": final_answer,
                "reasoning_summary": reasoning_summary_steps[:6],
                "artifact_ref": primary_artifact_ref,
                "checkpoint_ref": latest_checkpoint_ref,
                **_report_completion_payload(report_state),
            }
            task.artifact_refs_json = _append_unique(task.artifact_refs_json, primary_artifact_ref)
            task.artifact_refs_json = _append_unique(task.artifact_refs_json, report_ref)
            task.checkpoint_refs_json = _append_unique(
                task.checkpoint_refs_json, latest_checkpoint_ref
            )
            self.db.add(task)
            self.db.commit()
            set_span_attributes(
                task_span,
                {
                    "datalogue.task.status": "completed",
                    "datalogue.artifact_ref": primary_artifact_ref,
                    "datalogue.total_duration_ms": round((time.time() - task_started_at) * 1000),
                    "report.required": report_state.required,
                    "report.status": report_state.status.value,
                    "report.attempt": report_state.attempt,
                    "report.correction_count": report_state.correction_count,
                    "report.duration_ms": round(
                        (time.time() - (report_started_at or task_started_at)) * 1000
                    ),
                    "source_artifact_ref": report_state.source_artifact_ref,
                    "report_ref": report_state.report_ref,
                },
            )
            log_lifecycle(
                "agent_team.task.completed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                emitted_message_completed=message_completed_emitted,
                report_required=report_state.required,
                report_status=report_state.status.value,
                report_attempt=report_state.attempt,
                report_correction_count=report_state.correction_count,
                source_artifact_ref=report_state.source_artifact_ref,
                report_ref=report_state.report_ref,
            )
            if not message_completed_emitted:
                _append_reasoning_summary_step(
                    reasoning_summary_steps,
                    title="整理回答",
                    summary=accumulated_text or "任务已完成。",
                )
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
                        "reasoning_summary": reasoning_summary_steps[:6],
                        "timing": {
                            "ttft_ms": (
                                round((first_delta_at - task_started_at) * 1000)
                                if first_delta_at
                                else 0
                            ),
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
                payload={
                    "summary": "Agent Team 任务已完成。",
                    **_report_completion_payload(report_state),
                },
            )
        except asyncio.CancelledError:
            # 客户端断流或上层取消时立即收口 mirror/task，避免遗留永久 running 记录。
            set_span_attributes(task_span, {"datalogue.task.status": "cancelled"})
            task_span.set_status(Status(StatusCode.ERROR, "agent team task cancelled"))
            mark_message_interrupted(
                self.db,
                message_id=assistant_message.message_id,
                reason="任务已中断。",
            )
            task.status = "cancelled"
            task.error_payload_json = {"error_code": "AGENT_TEAM_TASK_CANCELLED"}
            self.db.add(task)
            self.db.commit()
            raise
        except Exception as exc:
            # 异常已转换为 SSE 失败事件，需显式标记 span 才能在 Phoenix 中检索失败链路。
            task_span.record_exception(exc)
            task_span.set_status(Status(StatusCode.ERROR, "agent team task failed"))
            set_span_attributes(task_span, {"datalogue.task.status": "failed"})
            logger.exception(
                "Agent Team 任务执行失败: task_id=%s trace_id=%s thread_id=%s message_id=%s "
                "selected_agent=%s error_type=%s error=%s",
                task.task_id,
                trace_id,
                session.thread_id,
                assistant_message.message_id,
                selected_agent,
                type(exc).__name__,
                exc,
            )
            is_timeout = isinstance(exc, TimeoutError)
            is_report_incomplete = isinstance(
                exc, ReportWorkerRequiredNotCompletedError
            ) or (is_timeout and report_state.required and not report_state.can_complete)
            error_code = (
                "REPORT_WORKER_REQUIRED_NOT_COMPLETED"
                if is_report_incomplete
                else ("AGENT_TEAM_TASK_TIMEOUT" if is_timeout else "AGENT_TEAM_TASK_FAILED")
            )
            error_summary = (
                "查询结果已保留，但报告整理未完成，请稍后重试。"
                if is_report_incomplete
                else (
                    "Agent Team 任务执行超时，请缩小问题范围后重试。"
                    if is_timeout
                    else "Agent Team 任务执行失败，内部细节已隐藏。"
                )
            )
            if is_report_incomplete and report_state.required and not report_state.can_complete:
                if report_state.status in {
                    ReportExecutionStatus.PENDING,
                    ReportExecutionStatus.RUNNING,
                }:
                    report_state.mark_failed(error_code)
            set_span_attributes(
                task_span,
                {
                    "report.required": report_state.required,
                    "report.status": report_state.status.value,
                    "report.attempt": report_state.attempt,
                    "report.correction_count": report_state.correction_count,
                    "report.duration_ms": round(
                        (time.time() - (report_started_at or task_started_at)) * 1000
                    ),
                    "source_artifact_ref": report_state.source_artifact_ref,
                    "report_ref": report_state.report_ref,
                },
            )
            log_output(
                event_type="task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                error_code=error_code,
                report_required=report_state.required,
                report_status=report_state.status.value,
                report_attempt=report_state.attempt,
                report_correction_count=report_state.correction_count,
                source_artifact_ref=report_state.source_artifact_ref,
                report_ref=report_state.report_ref,
                error_summary=error_summary,
            )
            log_lifecycle(
                "agent_team.task.failed",
                task_id=task.task_id,
                trace_id=trace_id,
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                selected_agent=selected_agent,
                error_code=error_code,
            )
            mark_message_failed(
                self.db,
                message_id=assistant_message.message_id,
                error_summary=error_summary,
                payload={
                    "task_id": task.task_id,
                    "error_code": error_code,
                    "artifact_ref": primary_artifact_ref,
                    **_report_completion_payload(report_state),
                },
            )
            self._record_completion_refs(
                thread_id=session.thread_id,
                message_id=assistant_message.message_id,
                artifact_ref=primary_artifact_ref,
                report_ref=report_ref,
                checkpoint_ref=latest_checkpoint_ref,
            )
            task.status = "failed"
            task.error_payload_json = {
                "error_code": error_code,
                "artifact_ref": primary_artifact_ref,
                **_report_completion_payload(report_state),
            }
            task.artifact_refs_json = _append_unique(task.artifact_refs_json, primary_artifact_ref)
            task.artifact_refs_json = _append_unique(task.artifact_refs_json, report_ref)
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
                    "error_code": error_code,
                    "error_summary": error_summary,
                    "retryable": True,
                    "artifact_ref": primary_artifact_ref,
                    **_report_completion_payload(report_state),
                },
            )
        finally:
            # 无论完成、失败还是客户端提前关闭 SSE，都必须结束根 span，避免产生悬挂链路。
            task_span_scope.__exit__(None, None, None)

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
            checkpoint_refs_json=(
                [request.retry_checkpoint_ref] if request.retry_checkpoint_ref else []
            ),
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
        report_ref: str | None,
        checkpoint_ref: str | None,
    ) -> None:
        if artifact_ref:
            _record_thread_ref_once(
                self.db,
                thread_id=thread_id,
                message_id=message_id,
                ref_type="artifact",
                ref_value=artifact_ref,
                relation="primary",
            )
        if checkpoint_ref:
            _record_thread_ref_once(
                self.db,
                thread_id=thread_id,
                message_id=message_id,
                ref_type="checkpoint",
                ref_value=checkpoint_ref,
                relation="latest",
            )
        if report_ref:
            _record_thread_ref_once(
                self.db,
                thread_id=thread_id,
                message_id=message_id,
                ref_type="report",
                ref_value=report_ref,
                relation="report",
            )


def _append_unique(values: list[str] | None, value: str | None) -> list[str]:
    existing = list(values or [])
    if value and value not in existing:
        existing.append(value)
    return existing


def _record_thread_ref_once(
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
