# ============================================================
# File Name   : agentscope_shell_adapter.py
# Description:
#   AgentScope Shell Adapter legacy compatibility 外壳。
#
# Responsibilities:
#   - 标记旧 AgentScopeShellAdapter 为 legacy compatibility，不再声明主 Runtime ownership。
#   - 固定兼容层 AgentScope 可见工具白名单，只允许 ask_bi。
#   - 通过 BIWorkbenchTool 获取安全外层契约，不访问 schema、SQL、数据库或 control_plane。
#   - 作为后端 service 内部验证线存在，不开放公开 API、不接前端入口、不启动 runner。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bi_workbench import AskBIRequest, AskBIResponse, ArtifactCard
from app.services.agentscope_event_adapter import AgentScopeEventAdapter, AgentScopeShellEvent
from app.services.bi_workbench_tool import ask_bi


ALLOWED_AGENTSCOPE_TOOLS = {"ask_bi"}
LEGACY_COMPATIBILITY_MODE = "legacy_compatibility"
AGENTIC_RUNTIME_OWNER = "datalogue_agentic_shell"


class AgentScopeLegacyCompatibilityContract(BaseModel):
    """P2.2 legacy adapter 标记；旧 ask_bi 外壳不再拥有业务 runtime。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compatibility_mode: str = LEGACY_COMPATIBILITY_MODE
    runtime_owner: str = AGENTIC_RUNTIME_OWNER
    owns_business_runtime: bool = False
    legacy_tool_name: str = "ask_bi"
    allowed_tools: list[str] = Field(default_factory=lambda: ["ask_bi"])
    replacement_boundary: str = "DatalogueAgenticShell + BI atomic tools"


class AgentScopeShellResponse(BaseModel):
    """AgentScope Shell 第一阶段响应，只包含 ask_bi 的外层安全结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    used_tools: list[str] = Field(default_factory=list)
    answer: str | None = None
    artifact_card: ArtifactCard | None = None
    visible_events: list[AgentScopeShellEvent] = Field(default_factory=list)
    trace_events: list[AgentScopeShellEvent] = Field(default_factory=list)
    primary_ref: str | None = None
    related_refs: list[str] = Field(default_factory=list)
    status: str = "completed"
    task_id: str | None = None


class AgentScopeShellAdapter:
    """旧 AgentScope 外层 Shell 兼容入口；不导入或启动 AgentScope runtime。"""

    def __init__(
        self,
        *,
        allowed_tools: list[str] | None = None,
        ask_bi_func: Callable[[AskBIRequest], AskBIResponse | Awaitable[AskBIResponse]] | None = None,
        event_adapter: AgentScopeEventAdapter | None = None,
    ) -> None:
        self.allowed_tools = ["ask_bi"] if allowed_tools is None else list(allowed_tools)
        invalid_tools = sorted(set(self.allowed_tools) - ALLOWED_AGENTSCOPE_TOOLS)
        if invalid_tools:
            raise ValueError(f"AgentScope Shell first phase only allows ask_bi: {invalid_tools}")
        if self.allowed_tools != ["ask_bi"]:
            raise ValueError("AgentScope Shell first phase must expose exactly ['ask_bi']")
        self.ask_bi_func = ask_bi_func or ask_bi
        self.event_adapter = event_adapter or AgentScopeEventAdapter()

    def compatibility_contract(self) -> AgentScopeLegacyCompatibilityContract:
        """声明旧 adapter 只是兼容壳，真实 runtime ownership 已迁到 Agentic Shell。"""

        return AgentScopeLegacyCompatibilityContract(allowed_tools=list(self.allowed_tools))

    async def run(
        self,
        question: str,
        *,
        conversation_id: int | None = None,
        confirmed_dataset_id: int | None = None,
        context_refs: list[str] | None = None,
    ) -> AgentScopeShellResponse:
        request = AskBIRequest(
            question=question,
            conversation_id=conversation_id,
            caller="agentscope_shell",
            confirmed_dataset_id=confirmed_dataset_id,
            context_refs=context_refs or [],
            request_options={},
        )
        # 第一阶段 Shell 只能经 ask_bi 穿透到 BI 内核，不能自行注册 schema/sql/database 等工具。
        maybe_response = self.ask_bi_func(request)
        ask_bi_response = await maybe_response if inspect.isawaitable(maybe_response) else maybe_response
        mapped_events = self.event_adapter.map_events([ask_bi_response.event_envelope])
        return AgentScopeShellResponse(
            used_tools=["ask_bi"],
            answer=ask_bi_response.answer,
            artifact_card=ask_bi_response.artifact_card,
            visible_events=mapped_events.visible_events,
            trace_events=mapped_events.trace_events,
            primary_ref=ask_bi_response.primary_ref.ref_id if ask_bi_response.primary_ref else None,
            related_refs=[item.ref_id for item in ask_bi_response.related_refs],
            status=ask_bi_response.status,
            task_id=ask_bi_response.task_id,
        )
