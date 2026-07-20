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

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.api.deps import require_api_user
from app.core import models
from app.core.database import get_db
from app.core.middlewares.lifecycle import log_lifecycle
from app.domains.agent_team.contracts import AgentTeamTaskRequest, AgentTeamTaskStreamEvent
from app.domains.agent_team.task_runtime import AgentTeamTaskRuntime

router = APIRouter()


def _sse_data(payload: dict) -> dict:
    return {"data": json.dumps(payload, ensure_ascii=False)}


def build_agent_team_task_runner(*, base_url: str, db: Session):
    """生产默认 runner：Agent Team 主链交给 AgentScope Service leader session。"""

    from app.runtime.engine.runner import AgentTeamTaskRunner

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
    current_user: models.User = Depends(require_api_user),
):
    """Agent Team 主执行入口；worker 创建与协作由 AgentScope 官方 Team 工具接管。"""

    _validate_task_ownership(db, payload=payload, current_user=current_user)
    stream_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db.get_bind(),
    )
    db.close()  # FastAPI 结束响应时会再次安全 close；这里确保建流前立即归还鉴权/校验连接。

    async def event_generator():
        log_lifecycle(
            "agent_team.api.stream.accepted",
            task_source=payload.task_source,
            task_type=payload.task_type,
            dataset_id=payload.dataset_id,
            question_length=len(payload.question or ""),
        )
        # 流运行时使用独立 Session，并在断流、超时和异常路径统一关闭；请求鉴权连接已在返回 SSE 前释放。
        with stream_session_factory() as stream_db:
            runtime = AgentTeamTaskRuntime(
                db=stream_db,
                actor_user_id=current_user.id,
                runner=build_agent_team_task_runner(
                    base_url=_agentscope_service_base_url(request),
                    db=stream_db,
                ),
                task_timeout_seconds=get_settings().AGENT_TEAM_TASK_TIMEOUT_SECONDS,
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


def _validate_task_ownership(
    db: Session,
    *,
    payload: AgentTeamTaskRequest,
    current_user: models.User,
) -> None:
    """在建立 SSE 前校验会话归属，避免错误在流内才暴露并留下跨用户写入。"""

    if payload.conversation_id is not None:
        conversation = (
            db.query(models.Conversation.id)
            .filter(
                models.Conversation.id == payload.conversation_id,
                models.Conversation.user_id == current_user.id,
            )
            .one_or_none()
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="对话不存在")

    if payload.thread_id:
        session = (
            db.query(models.AgentScopeSession)
            .filter(models.AgentScopeSession.thread_id == payload.thread_id)
            .one_or_none()
        )
        if session is not None:
            metadata = session.metadata_json if isinstance(session.metadata_json, dict) else {}
            stored_user_id = metadata.get("user_id")
            if stored_user_id is not None and str(stored_user_id) != str(current_user.id):
                raise HTTPException(status_code=404, detail="会话不存在")
            if stored_user_id is None:
                legacy_owner = (
                    db.query(models.Conversation.id)
                    .filter(
                        models.Conversation.id == session.legacy_conversation_id,
                        models.Conversation.user_id == current_user.id,
                    )
                    .one_or_none()
                )
                if legacy_owner is None:
                    # 无显式 owner 且不能回溯到本人旧会话的 session 一律不可被认领。
                    raise HTTPException(status_code=404, detail="会话不存在")
