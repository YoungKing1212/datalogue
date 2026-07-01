# ============================================================
# File Name   : agentscope_runtime_driver.py
# Description:
#   AgentScope Runtime 接入前的 Datalogue 边界适配契约。
#
# Responsibilities:
#   - 将 DatalogueAgenticShell 的受控回合契约转换为 Runtime 可见的安全契约。
#   - 只注册当前已实现且可安全暴露的 BI atomic tools。
#   - 保持 AS-R0 不替换 /chat/stream、不调用旧 ask_bi Shell Adapter、不启动真实 runner。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.agentic_shell import (
    AgenticShellAction,
    AgenticShellStatus,
    AgenticShellTurnContract,
    DatalogueAgenticShell,
    TaskType,
)
from app.services.agentic_bi_tools import BIAtomicToolProvider


RuntimeToolStatus = Literal["available"]


class AgentScopeRuntimeToolSpec(BaseModel):
    """AgentScope Runtime 可注册工具的安全描述，不包含 callable 或内部执行载荷。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    provider: str
    method: str
    status: RuntimeToolStatus = "available"


class AgentScopeRuntimeBoundaryContract(BaseModel):
    """AS-R0 进入真实 AgentScope Runtime 前的边界契约。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver_name: str = "agentscope_runtime_boundary"
    contract_version: str = "as-r0-runtime-boundary"
    status: AgenticShellStatus
    task_type: TaskType
    selected_agent: str
    projected_context: dict[str, Any] = Field(default_factory=dict)
    tool_registry: list[AgentScopeRuntimeToolSpec] = Field(default_factory=list)
    business_capabilities: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    disabled_agents: list[str] = Field(default_factory=list)
    lead_agent_action: AgenticShellAction


class DatalogueAgentScopeRuntimeDriver:
    """把 Agentic Shell 契约投影成 Runtime 边界；当前不执行 AgentScope runner。"""

    def __init__(self, *, shell: DatalogueAgenticShell | None = None) -> None:
        self.shell = shell or DatalogueAgenticShell()

    def prepare_runtime(
        self,
        *,
        question: str,
        context: dict[str, Any] | None = None,
        capability: str | None = None,
    ) -> AgentScopeRuntimeBoundaryContract:
        shell_contract = self.shell.prepare_turn(question=question, context=context or {})
        # PR1.2: Runtime boundary 必须显式携带 BI LeadAgent action 或非 BI disabled action。
        lead_agent_action = self.shell.route_action_from_contract(shell_contract, capability=capability)
        return self.from_shell_contract(shell_contract, lead_agent_action=lead_agent_action)

    def from_shell_contract(
        self,
        shell_contract: AgenticShellTurnContract,
        *,
        lead_agent_action: AgenticShellAction | None = None,
    ) -> AgentScopeRuntimeBoundaryContract:
        if not isinstance(shell_contract, AgenticShellTurnContract):
            raise TypeError("AgentScope Runtime driver only accepts AgenticShellTurnContract")

        # 非 BI placeholder 必须 fail-closed：不注册任何工具，等待后续阶段显式启用。
        tool_registry = (
            self._build_tool_registry(shell_contract.tool_policy.allowed_tools)
            if shell_contract.status == "ready"
            else []
        )
        return AgentScopeRuntimeBoundaryContract(
            status=shell_contract.status,
            task_type=shell_contract.task_type,
            selected_agent=shell_contract.selected_agent,
            projected_context=shell_contract.projected_context.model_dump(),
            tool_registry=tool_registry,
            business_capabilities=list(shell_contract.tool_policy.business_capabilities),
            disabled_tools=list(shell_contract.tool_policy.disabled_tools),
            disabled_agents=list(shell_contract.disabled_agents),
            lead_agent_action=lead_agent_action
            or self.shell.route_action_from_contract(shell_contract),
        )

    @staticmethod
    def _build_tool_registry(allowed_tools: list[str]) -> list[AgentScopeRuntimeToolSpec]:
        provider_methods = {
            "get_dataset_status": BIAtomicToolProvider.get_dataset_status,
            "list_candidate_assets": BIAtomicToolProvider.list_candidate_assets,
            "compile_dsl_to_sql": BIAtomicToolProvider.compile_dsl_to_sql,
            "execute_compiled_query": BIAtomicToolProvider.execute_compiled_query,
            "create_query_artifact": BIAtomicToolProvider.create_query_artifact,
            "get_artifact_summary": BIAtomicToolProvider.get_artifact_summary,
        }
        registry: list[AgentScopeRuntimeToolSpec] = []
        for tool_name in allowed_tools:
            method = provider_methods.get(tool_name)
            if method is None:
                # allowed_tools 理论上已经是受控白名单；这里再次 fail-closed，避免注册未实现方法。
                continue
            registry.append(
                AgentScopeRuntimeToolSpec(
                    name=tool_name,
                    provider="BIAtomicToolProvider",
                    method=method.__name__,
                )
            )
        return registry
