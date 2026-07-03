# ============================================================
# File Name   : test_agentic_architecture_p4_bi_agent_legacy_cleanup.py
# Description:
#   AgentScope 架构瘦身 P4 BI Agent legacy 实现层删除测试。
#
# Responsibilities:
#   - 验证 BI Agent 应用服务实现已归属 app.agents.bi_agent。
#   - 验证旧 app.services.bi_lead_agent 包不再作为业务入口存在。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import importlib

import pytest


def test_p4_bi_agent_application_services_owned_by_agents_package():
    from app.agents.bi_agent import (
        BIAgentConfirmationService,
        BIAgentHandoffService,
        BIAgentRunService,
        build_bi_agent_capabilities,
    )
    from app.agents.bi_agent.confirmation_service import BIAgentConfirmationService as DirectConfirmationService
    from app.agents.bi_agent.dataset_agent_factory import AgentScopeDatasetAgentFactory
    from app.agents.bi_agent.handoff_port import BIHandoffPort
    from app.agents.bi_agent.handoff_service import BIAgentHandoffService as DirectHandoffService
    from app.agents.bi_agent.native_handoff import AgentScopeNativeBIHandoff
    from app.agents.bi_agent.run_service import BIAgentRunService as DirectRunService

    assert BIAgentRunService is DirectRunService
    assert BIAgentConfirmationService is DirectConfirmationService
    assert BIAgentHandoffService is DirectHandoffService
    assert DirectRunService.__module__ == "app.agents.bi_agent.run_service"
    assert DirectConfirmationService.__module__ == "app.agents.bi_agent.confirmation_service"
    assert DirectHandoffService.__module__ == "app.agents.bi_agent.handoff_service"
    assert AgentScopeNativeBIHandoff.__module__ == "app.agents.bi_agent.native_handoff"
    assert AgentScopeDatasetAgentFactory.__module__ == "app.agents.bi_agent.dataset_agent_factory"
    assert BIHandoffPort.__module__ == "app.agents.bi_agent.handoff_port"
    assert build_bi_agent_capabilities.__module__ == "app.agents.bi_agent.capabilities"


def test_p4_bi_agent_api_owned_by_bi_agent_module():
    from app.api import bi_agent
    from app.api.bi_agent import create_bi_agent_run

    assert bi_agent.router is not None
    assert create_bi_agent_run.__module__ == "app.api.bi_agent"


@pytest.mark.parametrize(
    "module_name",
    [
        "app.api.bi_lead_agent",
        "app.models.bi_lead_agent",
        "app.schemas.bi_lead_agent",
        "app.services.bi_lead_agent",
        "app.services.bi_lead_agent.capabilities",
        "app.services.bi_lead_agent.confirmation_service",
        "app.services.bi_lead_agent.dataset_agent_factory",
        "app.services.bi_lead_agent.handoff_adapter",
        "app.services.bi_lead_agent.handoff_events",
        "app.services.bi_lead_agent.handoff_port",
        "app.services.bi_agent.handoff_service",
        "app.services.bi_agent.native_handoff",
        "app.services.bi_lead_agent.run_service",
        "app.agents.bi_agent.handoff_adapter",
    ],
)
def test_p4_old_bi_lead_agent_services_package_is_not_importable(module_name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
