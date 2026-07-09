# ============================================================
# File Name   : agent_team.py
# Description:
#   AgentScope Agent Team 统一任务入口 API。
#
# Responsibilities:
#   - 暴露 /tasks/stream SSE 主入口。
#   - 将 AgentTeamTaskRequest 交给 AgentTeamTaskRuntime。
#   - 保证新主链命名为 Agent Team，不再挂载历史任务入口。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.database import get_db
from app.core.middlewares.lifecycle import log_lifecycle
from app.domains.agent_team.contracts import AgentTeamTaskRequest, AgentTeamTaskStreamEvent
from app.domains.agent_team.task_runtime import AgentTeamTaskRuntime

router = APIRouter()


def _sse_data(payload: dict) -> dict:
    return {"data": json.dumps(payload, ensure_ascii=False)}


def build_agent_team_task_runner(*, base_url: str, db: Session):
    """生产默认 runner：Agent Team 主链交给 AgentScope Service leader session。"""

    from app.agentscope_runtime.runner import AgentTeamTaskRunner

    return AgentTeamTaskRunner(base_url=base_url, db=db, settings=get_settings())


def _agentscope_service_base_url(request: Request) -> str:
    settings = get_settings()
    if settings.AGENTSCOPE_SERVICE_BASE_URL:
        return settings.AGENTSCOPE_SERVICE_BASE_URL.rstrip("/")
    return f"{str(request.base_url).rstrip('/')}{settings.AGENTSCOPE_MOUNT_PATH}"


@router.post("/tasks/stream")
def stream_agent_team_task(
    payload: AgentTeamTaskRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Agent Team 主执行入口；worker 创建与协作由 AgentScope 官方 Team 工具接管。"""

    async def event_generator():
        log_lifecycle(
            "agent_team.api.stream.accepted",
            task_source=payload.task_source,
            task_type=payload.task_type,
            dataset_id=payload.dataset_id,
            question_length=len(payload.question or ""),
        )
        runtime = AgentTeamTaskRuntime(
            db=db,
            runner=build_agent_team_task_runner(
                base_url=_agentscope_service_base_url(request),
                db=db,
            ),
        )
        async for envelope in runtime.stream(payload):
            log_lifecycle(
                "agent_team.api.stream.event",
                task_id=envelope.task_id,
                trace_id=envelope.trace_id,
                event_type=envelope.event_type,
                selected_agent=envelope.selected_agent,
            )
            event = AgentTeamTaskStreamEvent(
                task_id=envelope.task_id or "",
                event_envelope=envelope,
                legacy_payload=envelope.legacy_payload,
            )
            yield _sse_data(event.model_dump(mode="json"))
        log_lifecycle(
            "agent_team.api.stream.closed",
            task_source=payload.task_source,
            task_type=payload.task_type,
            dataset_id=payload.dataset_id,
        )

    return EventSourceResponse(event_generator())
