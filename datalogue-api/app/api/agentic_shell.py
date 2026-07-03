# ============================================================
# File Name   : agentic_shell.py
# Description:
#   Agentic Shell 统一任务入口 API。
#
# Responsibilities:
#   - 暴露 /tasks/stream SSE 主入口。
#   - 将 AgenticShellTaskRequest 交给 AgenticShellTaskRuntime。
#   - 保证 Chat UI 和 Workbench 不再从旧 chat stream 入口执行。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.agentic_shell_task import AgenticShellTaskRequest, AgenticShellTaskStreamEvent
from app.middlewares.lifecycle import log_lifecycle
from app.runtime import AgenticShellTaskRuntime

router = APIRouter()


def _sse_data(payload: dict) -> dict:
    return {"data": json.dumps(payload, ensure_ascii=False)}


def build_agentic_shell_task_runner(*, base_url: str):
    """生产默认 runner：Shell 主链交给 AgentScope Service 固定智能体团队。"""

    from app.agentscope_service.runner import AgentScopeServiceTaskRunner

    return AgentScopeServiceTaskRunner(base_url=base_url)


def _agentscope_service_base_url(request: Request) -> str:
    settings = get_settings()
    if settings.AGENTSCOPE_SERVICE_BASE_URL:
        return settings.AGENTSCOPE_SERVICE_BASE_URL.rstrip("/")
    return f"{str(request.base_url).rstrip('/')}{settings.AGENTSCOPE_MOUNT_PATH}"


@router.post("/tasks/stream")
def stream_agentic_shell_task(
    payload: AgenticShellTaskRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """唯一主执行入口；所有 Chat/Workbench 执行都从 AgenticShellTask 开始。"""

    async def event_generator():
        log_lifecycle(
            "agentic_shell.api.stream.accepted",
            task_source=payload.task_source,
            task_type=payload.task_type,
            dataset_id=payload.dataset_id,
            question_length=len(payload.question or ""),
        )
        runtime = AgenticShellTaskRuntime(
            db=db,
            runner=build_agentic_shell_task_runner(
                base_url=_agentscope_service_base_url(request),
            ),
        )
        async for envelope in runtime.stream(payload):
            log_lifecycle(
                "agentic_shell.api.stream.event",
                task_id=envelope.task_id,
                trace_id=envelope.trace_id,
                event_type=envelope.event_type,
                selected_agent=envelope.selected_agent,
            )
            event = AgenticShellTaskStreamEvent(
                task_id=envelope.task_id or "",
                event_envelope=envelope,
                legacy_payload=envelope.legacy_payload,
            )
            yield _sse_data(event.model_dump(mode="json"))
        log_lifecycle(
            "agentic_shell.api.stream.closed",
            task_source=payload.task_source,
            task_type=payload.task_type,
            dataset_id=payload.dataset_id,
        )

    return EventSourceResponse(event_generator())
