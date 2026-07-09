# Phase B 迁移：bi_agent 实体已迁至 app.domains.bi.agent
# 本文件保留为兼容 facade，禁止新增业务逻辑。

__all__: list[str] = []


def __getattr__(name: str):
    """兼容迁移中按需加载旧路径，转发至新 agents。"""

    import importlib

    _FORWARD = {
        "build_bi_agent_capabilities": "app.domains.bi.agent.capabilities",
        "sanitize_dataset_capability": "app.domains.bi.agent.capabilities",
        "BIAgentConfirmationService": "app.domains.bi.agent.confirmation_service",
        "BIAgentHandoffService": "app.domains.bi.agent.handoff_service",
        "BIAgentRunService": "app.domains.bi.agent.run_service",
        "BIHandoffPort": "app.domains.bi.agent.handoff_port",
        "AgentScopeDatasetAgentFactory": "app.domains.bi.agent.dataset_agent_factory",
        "AgentScopeNativeBIHandoff": "app.domains.bi.agent.native_handoff",
        "build_bi_runtime_context": "app.domains.bi.agent.runtime_context",
    }
    if name in _FORWARD:
        mod = importlib.import_module(_FORWARD[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
