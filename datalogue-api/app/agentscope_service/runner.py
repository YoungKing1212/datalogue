# ============================================================
# File Name   : runner.py
# Description:
#   Agent Team 网关到 AgentScope Agent Service 的运行适配器。
#
# Responsibilities:
#   - 创建或使用 leader session，并通过 AgentScope 官方 Service chat/stream 驱动主链。
#   - 不预注册固定 worker Agent，不实现 TeamCreate/AgentCreate/TeamSay 的替代编排。
#   - 将 AgentScope Service 原始事件投影成 Datalogue 统一事件 envelope。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agentscope.message import UserMsg
from sqlalchemy.orm import Session

from app.agentscope_service.client import AgentScopeServiceClient
from app.agentscope_service.projection import project_agentscope_service_event
from app.agentscope_service.registry import build_datalogue_leader_agent_spec
from app.core.config import Settings, get_settings
from app.middlewares.lifecycle import log_lifecycle
from app.models.agent_team_task import AgentTeamTask
from app.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
from app.schemas.bi_workbench import DatalogueEventEnvelope
from app.services.llm_config import resolve_llm_config


DEFAULT_LEADER_AGENT_ID = None


class AgentScopeServiceTaskRunner:
    """Agent Team 默认 runner：只代理 AgentScope Service，不执行 Datalogue 自研 Agent loop。"""

    def __init__(
        self,
        *,
        base_url: str,
        db: Session | None = None,
        settings: Settings | None = None,
        client: AgentScopeServiceClient | None = None,
        leader_agent_id: str | None = DEFAULT_LEADER_AGENT_ID,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.db = db
        self.settings = settings or get_settings()
        self.client = client or AgentScopeServiceClient(base_url=self.base_url)
        self.leader_agent_id = leader_agent_id
        self._owns_client = client is None

    async def stream(
        self,
        *,
        request: AgentTeamTaskRequest,
        task: AgentTeamTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[DatalogueEventEnvelope]:
        """把一次 Agent Team 任务委托给 AgentScope Service session stream。"""

        leader_agent_id = await self._resolve_leader_agent_id()
        chat_model_config = await self._build_chat_model_config(request)
        session_name = (request.question or "Datalogue Agent Team")[:80]
        service_session_id = await self.client.create_session(
            agent_id=leader_agent_id,
            name=session_name,
            chat_model_config=chat_model_config,
        )
        log_lifecycle(
            "agentscope_agent_team.runner.session_created",
            task_id=task.task_id,
            trace_id=task.trace_id,
            agent_id=leader_agent_id,
            service_session_id=service_session_id,
        )

        await self.client.trigger_chat(
            agent_id=leader_agent_id,
            session_id=service_session_id,
            text=_build_agent_input_text(request=request, user_msg=user_msg),
        )
        log_lifecycle(
            "agentscope_agent_team.runner.chat_triggered",
            task_id=task.task_id,
            trace_id=task.trace_id,
            agent_id=leader_agent_id,
            service_session_id=service_session_id,
        )

        current_reply_spawned_worker = False
        current_reply_text = ""
        try:
            async for event in self.client.stream_session(
                service_session_id,
                agent_id=leader_agent_id,
            ):
                if _is_agent_create_event(event):
                    current_reply_spawned_worker = True
                current_reply_text += _event_text(event)
                envelope = project_agentscope_service_event(
                    event,
                    task_id=task.task_id,
                    trace_id=task.trace_id,
                    thread_id=task.thread_id,
                    message_id=task.message_id,
                    selected_agent=task.selected_agent,
                )
                if envelope.event_type == "message.completed" and _is_intermediate_team_reply(
                    spawned_worker=current_reply_spawned_worker,
                    reply_text=current_reply_text,
                    payload=envelope.payload,
                ):
                    # AgentCreate 只把 worker 的首次任务入队；worker 会在独立 session 中执行，
                    # 完成后通过 TeamSay 唤醒 leader。本次 ReplyEnd 只是“分派完成”，不能关闭 Datalogue SSE。
                    current_reply_spawned_worker = False
                    current_reply_text = ""
                    continue
                yield envelope
                if envelope.event_type == "message.completed":
                    # AgentScope session stream 是可跨多轮复用的长连接；Datalogue API 一次任务完成后要主动退出。
                    break
        finally:
            if self._owns_client:
                await self.client.aclose()

    async def _resolve_leader_agent_id(self) -> str:
        """解析 AgentScope Service 中的 leader agent_id；缺失时走官方 /agent 创建。"""

        if self.leader_agent_id:
            return self.leader_agent_id
        spec = build_datalogue_leader_agent_spec()
        return await self.client.ensure_agent(**spec.to_agent_payload())

    async def _build_chat_model_config(self, request: AgentTeamTaskRequest) -> dict[str, Any]:
        """把 Datalogue LLM 配置转换成 AgentScope Service session 可运行的模型配置。"""

        config = resolve_llm_config(
            self.settings,
            role="lead_agent",
            db=self.db,
            model_config_id=request.model_config_id,
        )
        credential_id = _credential_id_for_request(request)
        synced_credential_id = await self.client.upsert_openai_credential(
            credential_id=credential_id,
            name=f"Datalogue {config.name}",
            api_key=config.api_key,
            base_url=config.base_url,
        )
        # AgentScope ChatService 只从 session.config.chat_model_config 取模型；这里不能省略 credential_id。
        return {
            "type": "openai_credential",
            "credential_id": synced_credential_id,
            "model": config.model,
            "parameters": {
                "thinking_enable": config.thinking_enabled,
            },
        }


def _build_agent_input_text(*, request: AgentTeamTaskRequest, user_msg: UserMsg) -> str:
    """生成给 Agent Team leader 的最小上下文，不夹带 schema/raw rows 等敏感载荷。"""

    context: dict[str, Any] = {
        "task_source": request.task_source,
        "task_type": request.task_type,
        "dataset_id": request.dataset_id,
        "conversation_id": request.conversation_id,
        "model_config_id": request.model_config_id,
        "artifact_ref": request.artifact_ref,
        "retry_checkpoint_ref": request.retry_checkpoint_ref,
        "clarification_response": request.clarification_response,
        # 该提示让 leader 使用官方 Team 工具选择 worker；Datalogue 不在这里手写 worker 路由。
        "available_worker_types": ["bi", "report", "python", "audit"],
    }
    compact_context = {key: value for key, value in context.items() if value is not None}
    if not compact_context:
        return str(user_msg.content or request.question or "")
    return "\n".join(
        [
            str(user_msg.content or request.question or ""),
            "",
            "Agent Team 任务上下文(JSON):",
            json.dumps(compact_context, ensure_ascii=False, separators=(",", ":")),
        ]
    )


def _credential_id_for_request(request: AgentTeamTaskRequest) -> str:
    if request.model_config_id is not None:
        return f"datalogue-openai-compatible-model-{request.model_config_id}"
    return "datalogue-openai-compatible-lead-agent"


def _is_agent_create_event(event: dict[str, Any]) -> bool:
    raw_type = str(event.get("event_type") or event.get("type") or "").lower()
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    tool_name = str(
        event.get("tool_call_name")
        or event.get("name")
        or payload.get("tool_call_name")
        or payload.get("name")
        or "",
    )
    return "tool_call" in raw_type and tool_name == "AgentCreate"


def _event_text(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if isinstance(payload, dict):
        content = payload.get("content") or payload.get("summary") or payload.get("text")
        if content is not None:
            return str(content)
    content = event.get("content") or event.get("delta") or event.get("text")
    return str(content) if content is not None else ""


def _is_intermediate_team_reply(
    *,
    spawned_worker: bool,
    reply_text: str,
    payload: dict[str, Any],
) -> bool:
    if spawned_worker:
        return True
    summary = str(payload.get("summary") or payload.get("content") or "")
    text = f"{reply_text}\n{summary}".lower()
    has_worker = any(marker in text for marker in ("worker", "成员", "子agent", "bi-worker", "bi worker"))
    is_waiting = any(marker in text for marker in ("等待", "wait", "report back", "返回结果", "汇报"))
    return has_worker and is_waiting
