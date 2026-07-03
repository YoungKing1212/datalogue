# ============================================================
# File Name   : runner.py
# Description:
#   Agentic Shell 主链到 AgentScope Agent Service 的运行适配器。
#
# Responsibilities:
#   - 幂等准备 Datalogue 固定 Agent，并选择 agentic_lead_agent 作为主入口。
#   - 通过 AgentScope 官方 Service session/chat/stream 接口驱动智能体团队。
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

from app.agentscope_service.bootstrap import AgentScopeBootstrapService
from app.agentscope_service.client import AgentScopeServiceClient
from app.agentscope_service.projection import project_agentscope_service_event
from app.middlewares.lifecycle import log_lifecycle
from app.models.agentic_shell_task import AgenticShellTask
from app.schemas.agentic_shell_task import AgenticShellTaskRequest
from app.schemas.bi_workbench import DatalogueEventEnvelope


ENTRY_AGENT_KEY = "agentic_lead_agent"


class AgentScopeServiceTaskRunner:
    """Agentic Shell 默认 runner：只调用 AgentScope Service，不自建 Agent 循环。"""

    def __init__(
        self,
        *,
        base_url: str,
        bootstrap: AgentScopeBootstrapService | None = None,
        client: AgentScopeServiceClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bootstrap = bootstrap or AgentScopeBootstrapService(base_url=self.base_url)
        self.client = client or AgentScopeServiceClient(base_url=self.base_url)
        self._owns_bootstrap = bootstrap is None
        self._owns_client = client is None

    async def stream(
        self,
        *,
        request: AgenticShellTaskRequest,
        task: AgenticShellTask,
        user_msg: UserMsg,
    ) -> AsyncIterator[DatalogueEventEnvelope]:
        """把一次 Shell 任务委托给 AgentScope Service session stream。"""

        agent_ids = await self.bootstrap.ensure_static_agents()
        agent_id = agent_ids.get(ENTRY_AGENT_KEY)
        if not agent_id:
            raise RuntimeError("AGENTSCOPE_ENTRY_AGENT_MISSING")

        session_name = (request.question or "Datalogue Agentic Shell")[:80]
        service_session_id = await self.client.create_session(
            agent_id=agent_id,
            name=session_name,
        )
        log_lifecycle(
            "agentscope_service.runner.session_created",
            task_id=task.task_id,
            trace_id=task.trace_id,
            agent_key=ENTRY_AGENT_KEY,
            agent_id=agent_id,
            service_session_id=service_session_id,
        )

        await self.client.trigger_chat(
            agent_id=agent_id,
            session_id=service_session_id,
            text=_build_agent_input_text(request=request, user_msg=user_msg),
        )
        log_lifecycle(
            "agentscope_service.runner.chat_triggered",
            task_id=task.task_id,
            trace_id=task.trace_id,
            agent_key=ENTRY_AGENT_KEY,
            agent_id=agent_id,
            service_session_id=service_session_id,
        )

        try:
            async for event in self.client.stream_session(
                service_session_id,
                agent_id=agent_id,
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
            if self._owns_bootstrap:
                await self.bootstrap.aclose()


def _build_agent_input_text(*, request: AgenticShellTaskRequest, user_msg: UserMsg) -> str:
    """生成给固定 LeadAgent 的最小上下文，不夹带 schema/raw rows 等敏感载荷。"""

    context: dict[str, Any] = {
        "task_source": request.task_source,
        "task_type": request.task_type,
        "dataset_id": request.dataset_id,
        "conversation_id": request.conversation_id,
        "model_config_id": request.model_config_id,
        "artifact_ref": request.artifact_ref,
        "retry_checkpoint_ref": request.retry_checkpoint_ref,
        "clarification_response": request.clarification_response,
    }
    compact_context = {key: value for key, value in context.items() if value is not None}
    if not compact_context:
        return str(user_msg.content or request.question or "")
    return "\n".join(
        [
            str(user_msg.content or request.question or ""),
            "",
            "任务上下文(JSON):",
            json.dumps(compact_context, ensure_ascii=False, separators=(",", ":")),
        ]
    )
