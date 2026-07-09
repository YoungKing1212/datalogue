# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue 嵌入式 AgentScope Service 包入口。
#
# Responsibilities:
#   - 暴露创建 AgentScope Service FastAPI 子应用的稳定 factory。
#   - 隔离官方 AgentScope Service 基础层与主业务路由的集成边界。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

# Phase B 兼容 facade：所有实体已迁至 app.runtime.engine + app.domains
# 本文件仅转发旧导入路径，禁止新增业务逻辑。

from app.runtime.engine.app_factory import create_embedded_agentscope_app

__all__ = ["create_embedded_agentscope_app"]


def __getattr__(name: str):
    """兼容迁移中按需转发所有旧 agentscope_service 子模块导入。"""

    import importlib

    _FORWARD = {
        # bi_worker → domains/bi/worker/
        "BIWorkerContext": "app.domains.bi.worker.context",
        "BIWorkerContracts": "app.domains.bi.worker.contracts",
        "BIWorkerRuntime": "app.domains.bi.worker.runtime",
        "BIWorkerTimelineCache": "app.domains.bi.worker.timeline_cache",
        "BIWorkerValidator": "app.domains.bi.worker.validator",
        "AgentTeamDatasetQueryResult": "app.domains.bi.worker.dataset_query",
        "execute_dataset_query_for_agent_team_direct_fallback": "app.domains.bi.worker.dataset_query",
        # engine → runtime/engine/
        "app_factory": "app.runtime.engine.app_factory",
        "registry": "app.runtime.engine.registry",
        "runner": "app.runtime.engine.runner",
        "projection": "app.runtime.engine.projection",
        "client": "app.runtime.engine.client",
        "credentials": "app.runtime.engine.credentials",
        "otel_setup": "app.runtime.engine.otel_setup",
        "tools": "app.runtime.engine.tools",
        # agent_team → domains/agent_team/
        "team_templates": "app.domains.agent_team.team_templates",
        "task_context": "app.domains.agent_team.task_context",
        "progress_bridge": "app.domains.agent_team.progress_bridge",
        "worker_logging": "app.domains.agent_team.worker_logging",
    }
    if name in _FORWARD:
        mod = importlib.import_module(_FORWARD[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
