# ============================================================
# File Name   : test_agentscope_service_imports.py
# Description:
#   校验 AgentScope Service 基础依赖和 Datalogue 嵌入式入口可导入。
#
# Responsibilities:
#   - 捕捉 AgentScope Service/Storage extras 缺失导致的启动期导入失败。
#   - 保证 Datalogue 的 agentscope_service 包暴露稳定 factory 入口。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations


def test_agentscope_service_dependencies_import_with_project_dependency_set():
    """Agent Service extras 缺失会让 FastAPI worker 在导入阶段失败。"""

    from agentscope.app import create_app
    from agentscope.app.message_bus import RedisMessageBus
    from agentscope.app.storage import RedisStorage
    from agentscope.app.workspace_manager import LocalWorkspaceManager

    assert create_app is not None
    assert RedisStorage is not None
    assert RedisMessageBus is not None
    assert LocalWorkspaceManager is not None


def test_datalogue_agentscope_service_factory_is_importable():
    """主应用通过该 factory 嵌入 AgentScope Service。"""

    from app.runtime.engine.app_factory import create_embedded_runtime_app

    assert create_embedded_runtime_app is not None


def test_datalogue_agentscope_runtime_facade_is_importable():
    """目录治理新入口先作为 facade 存在，后续迁移调用方时可从这里稳定导入。"""

    from app.agentscope_runtime.app_factory import create_embedded_runtime_app
    from app.agentscope_runtime.client import (
        DEFAULT_AGENTSCOPE_USER_ID,
        AgentScopeServiceClient,
    )
    from app.agentscope_runtime.credentials import DatalogueLLMCredential
    from app.agentscope_runtime.projection import project_runtime_event
    from app.agentscope_runtime.registry import build_datalogue_subagent_templates
    from app.agentscope_runtime.runner import AgentTeamTaskRunner
    from app.agentscope_runtime.worker_logging import build_datalogue_extra_agent_middlewares
    from app.runtime.engine.client import DEFAULT_AGENTSCOPE_USER_ID as legacy_default_user_id

    assert create_embedded_runtime_app is not None
    assert DEFAULT_AGENTSCOPE_USER_ID == legacy_default_user_id
    assert AgentScopeServiceClient is not None
    assert DatalogueLLMCredential is not None
    assert project_runtime_event is not None
    assert build_datalogue_subagent_templates is not None
    assert AgentTeamTaskRunner is not None
    assert build_datalogue_extra_agent_middlewares is not None
