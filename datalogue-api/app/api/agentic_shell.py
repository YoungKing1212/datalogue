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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.chat import chat_stream_runtime_hooks
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.agentic_shell_task import AgenticShellTaskRequest, AgenticShellTaskStreamEvent
from app.services.agentic_chat_runtime import DatalogueChatStreamRuntime
from app.services.agentic_shell_task_runtime import AgenticShellTaskRuntime, LegacyWorkflowTaskRunner

router = APIRouter()


def _sse_data(payload: dict) -> dict:
    return {"data": json.dumps(payload, ensure_ascii=False)}


def build_agentic_shell_task_runner(db: Session) -> LegacyWorkflowTaskRunner:
    """生产默认 runner：新入口创建 task，BI 执行体通过 LegacyWorkflowAdapter 复用现有 service runtime。

    TODO(AS-R0): 迁移期结束后，LegacyWorkflowTaskRunner 和 DatalogueChatStreamRuntime
    应替换为 AgentScope 原生 runner，不再每次请求 new Runtime 实例。
    """

    async def legacy_stream_factory(chat_payload):
        runtime = DatalogueChatStreamRuntime(
            db=db,
            settings=get_settings(),
            hooks=chat_stream_runtime_hooks(),
        )
        async for event in runtime.stream(chat_payload):
            yield event

    return LegacyWorkflowTaskRunner(legacy_stream_factory=legacy_stream_factory)


@router.post("/tasks/stream")
def stream_agentic_shell_task(payload: AgenticShellTaskRequest, db: Session = Depends(get_db)):
    """唯一主执行入口；所有 Chat/Workbench 执行都从 AgenticShellTask 开始。"""

    async def event_generator():
        runtime = AgenticShellTaskRuntime(db=db, runner=build_agentic_shell_task_runner(db))
        async for envelope in runtime.stream(payload):
            event = AgenticShellTaskStreamEvent(
                task_id=envelope.task_id or "",
                event_envelope=envelope,
                legacy_payload=envelope.legacy_payload,
            )
            yield _sse_data(event.model_dump(mode="json"))

    return EventSourceResponse(event_generator())
