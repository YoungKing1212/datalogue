# ============================================================
# File Name   : agentic_lead_agent.py
# Description:
#   AgenticLeadAgent 直连问数 API。
#
# Responsibilities:
#   - 提供不经过 AgenticShellTask/Message/Handoff 的最小直连入口。
#   - 通过安全 DTO 返回业务摘要和 artifact/checkpoint 引用。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.agentic_lead_agent.direct_query_runner import AgenticDirectQueryRunner
from app.core.database import get_db
from app.models.conversation import Conversation, Message
from app.schemas.agentic_direct_query import (
    AgenticDirectQueryRequest,
    AgenticDirectQueryResponse,
    sanitize_public_summary,
)

router = APIRouter()


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _markdown_completed_summary(
    *,
    summary: str | None,
    artifact_ref: str | None,
    row_count: int | None,
    column_count: int | None,
) -> str | None:
    if summary:
        return summary
    if not artifact_ref and row_count is None and column_count is None:
        return None
    row_text = f"{row_count} 行" if row_count is not None else "行数未返回"
    column_text = f"{column_count} 列" if column_count is not None else "列数未返回"
    lines = [
        "## 查询结果",
        "",
        "- **结论**：查询结果已生成。",
        f"- **数据规模**：返回 {row_text}，{column_text}",
    ]
    if artifact_ref:
        lines.append(f"- **结果入口**：`{artifact_ref}`")
    return "\n".join(lines)


def _project_direct_query_response(result: dict[str, Any]) -> AgenticDirectQueryResponse:
    """API 边界只投影公开字段，丢弃 code/expected_tool/session/message 等内部执行态。"""

    status = str(result.get("status") or "blocked")
    artifact_ref = _optional_str(result.get("artifact_ref"))
    row_count = _optional_int(result.get("row_count"))
    column_count = _optional_int(result.get("column_count"))
    safe_summary = sanitize_public_summary(result.get("summary"))
    if status == "completed":
        # API 是前端最后一道安全投影；上游 summary 缺失时也不能把“查询已完成”这种泛化话术发给用户。
        safe_summary = _markdown_completed_summary(
            summary=safe_summary,
            artifact_ref=artifact_ref,
            row_count=row_count,
            column_count=column_count,
        )
    return AgenticDirectQueryResponse(
        status=status,
        selected_agent=str(result.get("selected_agent") or ""),
        summary=safe_summary,
        artifact_ref=artifact_ref,
        checkpoint_ref=_optional_str(result.get("checkpoint_ref")),
        row_count=row_count,
        column_count=column_count,
    )


def _sse_line(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _project_direct_query_stream_event(event: dict[str, Any]) -> dict[str, Any]:
    """把 runner 内部事件投影为前端可见事件，final 继续复用安全 DTO。"""

    if event.get("type") != "final":
        allowed = {
            "type",
            "event_type",
            "agent",
            "role",
            "phase",
            "title",
            "content",
            "trace_id",
            "payload",
        }
        return {key: value for key, value in event.items() if key in allowed}

    response = _project_direct_query_response(event.get("result") or {})
    public = response.model_dump()
    return {
        "type": "final",
        "event_type": "message.completed",
        "agent": event.get("agent") or "bi_agent",
        "trace_id": event.get("trace_id"),
        "answer": public.get("summary") or ("查询已完成。" if public.get("status") == "completed" else "查询未完成。"),
        "status": public.get("status"),
        "selected_agent": public.get("selected_agent"),
        "result_ref": public.get("artifact_ref"),
        "artifact_ref": public.get("artifact_ref"),
        "checkpoint_ref": public.get("checkpoint_ref"),
        "row_count": public.get("row_count"),
        "column_count": public.get("column_count"),
    }


def _conversation_exists(db: Session, conversation_id: int | None) -> bool:
    if not isinstance(conversation_id, int):
        return False
    return db.get(Conversation, conversation_id) is not None


def _persist_direct_user_message(db: Session, payload: AgenticDirectQueryRequest) -> bool:
    if not _conversation_exists(db, payload.conversation_id):
        return False
    # direct-query 是当前前端主入口；先写入用户可见问题，让后续同会话追问能被 runner 摘要回放。
    db.add(
        Message(
            conversation_id=payload.conversation_id,
            role="user",
            content=payload.question,
            response_metadata={
                "type": "agentic_direct_query",
                "trace_id": payload.trace_id,
                "dataset_id": payload.dataset_id,
            },
        )
    )
    db.flush()
    return True


def _persist_direct_assistant_message(
    db: Session,
    *,
    payload: AgenticDirectQueryRequest,
    public_event: dict[str, Any],
) -> bool:
    if not _conversation_exists(db, payload.conversation_id):
        return False
    answer = sanitize_public_summary(public_event.get("answer")) or "查询未完成。"
    # 只沉淀用户可见摘要和安全引用；SQL、schema、raw rows 等内部执行态不能进入历史摘要来源。
    db.add(
        Message(
            conversation_id=payload.conversation_id,
            role="assistant",
            content=answer,
            response_metadata={
                "type": "agentic_direct_query",
                "trace_id": public_event.get("trace_id") or payload.trace_id,
                "status": public_event.get("status"),
                "selected_agent": public_event.get("selected_agent"),
                "artifact_ref": public_event.get("artifact_ref"),
                "checkpoint_ref": public_event.get("checkpoint_ref"),
                "row_count": public_event.get("row_count"),
                "column_count": public_event.get("column_count"),
            },
        )
    )
    db.flush()
    return True


def _runner_kwargs(payload: AgenticDirectQueryRequest) -> dict[str, Any]:
    kwargs = {
        "question": payload.question,
        "dataset_id": payload.dataset_id,
        "conversation_id": payload.conversation_id,
        "trace_id": payload.trace_id,
    }
    if payload.model_config_id is not None:
        # 未选择模型时保持旧入参；选择后才覆盖本轮 AgentScope 模型配置。
        kwargs["model_config_id"] = payload.model_config_id
    return kwargs


@router.post("/direct-query", response_model=AgenticDirectQueryResponse)
async def run_agentic_direct_query(
    payload: AgenticDirectQueryRequest,
    db: Session = Depends(get_db),
) -> AgenticDirectQueryResponse:
    """执行 AgenticLeadAgent -> BI Agent 直连问数链路。"""

    runner = AgenticDirectQueryRunner(db=db)
    result = await runner.run(**_runner_kwargs(payload))
    response = _project_direct_query_response(result)
    if response.artifact_ref:
        # ArtifactStore 在请求事务内 flush 产物；API 成功返回 ref 前必须提交，否则后续 GET 看不到该产物。
        db.commit()
    return response


@router.post("/direct-query/stream")
async def stream_agentic_direct_query(
    payload: AgenticDirectQueryRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """以 SSE 输出 AgentScope 消息/事件，前端逐步渲染思考路径和最终回复。"""

    async def event_stream():
        should_commit = False
        user_message_persisted = False
        runner = AgenticDirectQueryRunner(db=db)
        async for event in runner.stream(**_runner_kwargs(payload)):
            public_event = _project_direct_query_stream_event(event)
            if not user_message_persisted:
                # runner 已经完成历史摘要读取后再写本轮问题，避免重复追问同一句时误跳过历史里的同文本问题。
                user_message_persisted = True
                if _persist_direct_user_message(db, payload):
                    should_commit = True
            if public_event.get("type") == "final":
                if _persist_direct_assistant_message(db, payload=payload, public_event=public_event):
                    should_commit = True
                if public_event.get("artifact_ref"):
                    # 直连流式接口也必须在 final 前确保 artifact 事务可见。
                    should_commit = True
            yield _sse_line(public_event)
        if should_commit:
            db.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
