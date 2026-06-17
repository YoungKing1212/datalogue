# ============================================================
# File Name   : internal_subagent.py
# Description:
#   内部 SubAgent A2A 流式接口。
#
# Responsibilities:
#   - 接收 RemoteDatasetSubAgentRunner 的内部调用请求。
#   - 复用 DatasetSubAgent 门面执行单数据集查询链路。
#   - 以 NDJSON 事件流返回 SubAgentEvent wire payload。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.graph.workflow import build_workflow
from app.services.dataset_subagent import DatasetSubAgent
from app.services.runner import DatasetSubAgentRequest

router = APIRouter()


@router.post("/subagent/run")
async def run_internal_subagent(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    x_datalogue_internal_token: str | None = Header(default=None),
):
    settings = get_settings()
    expected_token = settings.SUBAGENT_REMOTE_API_KEY
    if expected_token and x_datalogue_internal_token != expected_token:
        raise HTTPException(status_code=401, detail="invalid internal token")

    request_payload = payload.get("request") if isinstance(payload, dict) else None
    if not isinstance(request_payload, dict):
        raise HTTPException(status_code=422, detail="request is required")
    try:
        request = DatasetSubAgentRequest(**request_payload)
    except TypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    initial_state = payload.get("initial_state") if isinstance(payload.get("initial_state"), dict) else {}
    graph_kwargs = payload.get("graph_kwargs") if isinstance(payload.get("graph_kwargs"), dict) else {}
    graph = build_workflow(db)
    subagent = DatasetSubAgent(db=db, dataset_id=request.dataset_id)

    async def _events():
        async for event in subagent.run(
            request,
            None,
            graph=graph,
            initial_state=initial_state,
            graph_kwargs=graph_kwargs,
        ):
            yield json.dumps(
                {
                    "event_type": event.event_type,
                    "payload": event.payload,
                },
                ensure_ascii=False,
                default=str,
            ) + "\n"

    return StreamingResponse(_events(), media_type="application/x-ndjson")
