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

from app.agentscope_service.client import AgentScopeServiceClient
from app.agentscope_service.projection import project_agentscope_service_event
from app.agentscope_service.registry import build_datalogue_leader_agent_spec
from app.middlewares.lifecycle import log_lifecycle
from app.models.agent_team_task import AgentTeamTask
from app.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
from app.schemas.bi_workbench import DatalogueEventEnvelope


DEFAULT_LEADER_AGENT_ID = None


class AgentScopeServiceTaskRunner:
    """Agent Team 默认 runner：只代理 AgentScope Service，不执行 Datalogue 自研 Agent loop。"""

    def __init__(
        self,
        *,
        base_url: str,
        client: AgentScopeServiceClient | None = None,
        leader_agent_id: str | None = DEFAULT_LEADER_AGENT_ID,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        session_name = (request.question or "Datalogue Agent Team")[:80]
        service_session_id = await self.client.create_session(
            agent_id=leader_agent_id,
            name=session_name,
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

        try:
            async for event in self.client.stream_session(
                service_session_id,
                agent_id=leader_agent_id,
            ):
                yield project_agentscope_service_event(
                    event,
                    task_id=task.task_id,
                    trace_id=task.trace_id,
                    thread_id=task.thread_id,
                    message_id=task.message_id,
                    selected_agent=task.selected_agent,
                )
        finally:
            if self._owns_client:
                await self.client.aclose()

    async def _resolve_leader_agent_id(self) -> str:
        """解析 AgentScope Service 中的 leader agent_id；缺失时走官方 /agent 创建。"""

        if self.leader_agent_id:
            return self.leader_agent_id
        spec = build_datalogue_leader_agent_spec()
        return await self.client.ensure_agent(**spec.to_agent_payload())


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
