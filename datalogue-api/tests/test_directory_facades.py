# ============================================================
# File Name   : test_directory_facades.py
# Description:
#   验证 typed worker lane 目标目录 facade 能与旧模块入口并存。
#
# Responsibilities:
#   - 覆盖后端 facade-first 包骨架的导入兼容性，避免目录迁移期间破坏旧调用方。
#   - 确认关键 facade 仅复用旧实现对象，不在新目录承载业务逻辑。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""typed worker lane facade-first 目录骨架导入测试。"""

import importlib
import inspect
from pathlib import Path


def test_target_packages_are_importable():
    """目标领域包先作为兼容层存在，迁移期不要求承载新业务逻辑。"""

    for module_name in [
        "app.domains.data_source",
        "app.domains.query_execution",
        "app.domains.agent_team",
        "app.domains.bi",
        "app.agentscope_runtime",
        "app.runtime.engine",
    ]:
        assert importlib.import_module(module_name)


def test_data_source_service_is_direct_domain_access():
    """Phase F: 数据源服务直连 domains/data_source/service，无中间 facade。"""

    service = importlib.import_module("app.domains.data_source.service")
    assert callable(service.create_engine_for_datasource)
    assert callable(service.test_connection)
    assert callable(service.sync_source_tables)


def test_query_execution_preview_is_direct_domain_access():
    """Phase F: SQL preview 直连 domains/query_execution/preview，无中间 facade。"""

    preview = importlib.import_module("app.domains.query_execution.preview")
    assert callable(preview.preview_dataset_sql)


def test_runtime_engine_app_factory_is_direct_source():
    """runtime.engine.app_factory 是 create_embedded_runtime_app 的直接实体，不再经过中间 facade。"""

    engine = importlib.import_module("app.runtime.engine.app_factory")
    assert callable(engine.create_embedded_runtime_app)


def test_agentscope_runtime_facade_exposes_only_service_runtime_boundary():
    """Phase E: agentscope_runtime 先作为 AgentScope Service 嵌入边界 facade，不承载 BI 工具业务。"""

    facade = importlib.import_module("app.agentscope_runtime")
    legacy = importlib.import_module("app.runtime.engine")
    worker_logging = importlib.import_module("app.agentscope_runtime.worker_logging")
    legacy_worker_logging = importlib.import_module("app.domains.agent_team.worker_logging")

    assert facade.create_embedded_runtime_app is legacy.create_embedded_runtime_app
    assert facade.AgentScopeServiceClient is legacy.AgentScopeServiceClient
    assert facade.AgentTeamTaskRunner is legacy.AgentTeamTaskRunner
    assert facade.project_runtime_event is legacy.project_runtime_event
    assert facade.setup_runtime_tracing is legacy.setup_runtime_tracing
    assert facade.build_datalogue_extra_agent_middlewares is (
        legacy_worker_logging.build_datalogue_extra_agent_middlewares
    )
    assert worker_logging.build_datalogue_extra_agent_middlewares is (
        legacy_worker_logging.build_datalogue_extra_agent_middlewares
    )
    # BI worker 工具链仍在 runtime.engine.tools / domains.bi 内；新 facade 暂不把业务工具暴露为顶层 API。
    assert "build_datalogue_extra_agent_tools" not in facade.__all__
    assert not hasattr(facade, "build_datalogue_extra_agent_tools")


def test_data_source_implementation_lives_in_domain_modules():
    """Phase F: 数据源实现完全在 domains/data_source/，无 legacy facade。"""

    service = importlib.import_module("app.domains.data_source.service")
    capabilities = importlib.import_module("app.domains.data_source.capabilities")
    context = importlib.import_module("app.domains.data_source.context")
    diagnostics = importlib.import_module("app.domains.data_source.diagnostics")
    registry = importlib.import_module("app.domains.data_source.adapters.registry")
    base = importlib.import_module("app.domains.data_source.adapters.base")
    hive = importlib.import_module("app.domains.data_source.adapters.hive")
    oracle = importlib.import_module("app.domains.data_source.adapters.oracle")

    assert capabilities.DatasourceCapability.__module__ == "app.domains.data_source.capabilities"
    assert context.DatasourceContext.__module__ == "app.domains.data_source.context"
    assert diagnostics.DatasourceDiagnostic.__module__ == "app.domains.data_source.diagnostics"
    assert base.DatasourceAdapter.__module__ == "app.domains.data_source.adapters.base"
    assert hive.HiveAdapter.__module__ == "app.domains.data_source.adapters.hive"
    assert oracle.OracleAdapter.__module__ == "app.domains.data_source.adapters.oracle"
    assert registry.get_adapter.__module__ == "app.domains.data_source.adapters.registry"
    assert service.test_connection.__module__ == "app.domains.data_source.service"


def test_query_execution_guard_and_dialect_implementation_lives_in_domain_modules():
    """Phase B: SQL guard / dialect 实体已直接迁入 query_execution，旧 utils 路径通过 facade 转发。"""

    domain_guard = importlib.import_module("app.domains.query_execution.guard")
    domain_names = importlib.import_module("app.domains.query_execution.dialect.names")

    assert domain_guard.SQLGuardResult.__module__ == "app.domains.query_execution.guard"
    assert domain_guard.guard_readonly_sql.__module__ == "app.domains.query_execution.guard"
    assert domain_names.quote_ident.__module__ == "app.domains.query_execution.dialect.names"
    assert domain_names.sanitize_filter_sql.__module__ == "app.domains.query_execution.dialect.names"

    # utils facade 必须转发到同领域对象
    from app.core.utils import SQLGuardResult, guard_readonly_sql
    from app.core.utils import quote_ident, sanitize_filter_sql

    assert SQLGuardResult is domain_guard.SQLGuardResult
    assert guard_readonly_sql is domain_guard.guard_readonly_sql
    assert quote_ident is domain_names.quote_ident
    assert sanitize_filter_sql is domain_names.sanitize_filter_sql

    assert inspect.getsourcefile(domain_guard.guard_readonly_sql).endswith(
        "app/domains/query_execution/guard.py"
    )
    assert inspect.getsourcefile(domain_names.quote_ident).endswith(
        "app/domains/query_execution/dialect/names.py"
    )


def test_query_execution_adapter_and_compiler_implementation_lives_in_domain_modules():
    """Phase F: SQL 方言适配器与查询计划编译器直连 domains/query_execution。"""

    domain_adapter = importlib.import_module("app.domains.query_execution.dialect.adapter")
    domain_compiler = importlib.import_module("app.domains.query_execution.compiler")

    assert domain_adapter.adapt_sql_for_execution.__module__ == (
        "app.domains.query_execution.dialect.adapter"
    )
    assert domain_compiler.compile_query_plan_to_sql.__module__ == "app.domains.query_execution.compiler"


def test_query_execution_preview_implementation_lives_in_domain_module():
    """Phase F: SQL preview 直连 domains/query_execution/preview。"""

    domain = importlib.import_module("app.domains.query_execution.preview")
    assert domain.preview_dataset_sql.__module__ == "app.domains.query_execution.preview"


def test_query_execution_artifact_and_repair_implementation_lives_in_domain_modules():
    """Phase F: Artifact/RepairPlan 直连 domains/query_execution。"""

    domain_artifact = importlib.import_module("app.domains.query_execution.artifact_store")
    domain_repair = importlib.import_module("app.domains.query_execution.repair_plan")

    assert domain_artifact.ArtifactStore.__module__ == "app.domains.query_execution.artifact_store"
    assert domain_repair.validate_repair_plan.__module__ == "app.domains.query_execution.repair_plan"


def test_domains_bi_boundary_is_canonical_source_for_bi_capabilities():
    """Phase E: domains/bi 只收 Datalogue BI 能力、Skill、Toolkit、QueryPlan 契约与 runtime context。"""

    app_root = Path(__file__).resolve().parents[1] / "app"
    bi_root = app_root / "domains" / "bi"

    assert bi_root.is_dir()
    assert not (app_root / "bi").exists()
    assert not (app_root / "agents" / "bi_agent").exists()
    assert not any((bi_root / "toolchain").glob("*.py"))

    allowed_top_level = {
        "__init__.py",
        "agent",
        "agent_services.py",
        "skill",
        "toolkit",
        "worker",
        "worker_query.py",
    }
    source_names = {
        path.name
        for path in bi_root.iterdir()
        if path.name != "__pycache__" and (path.is_file() or any(path.rglob("*.py")))
    }
    assert source_names <= allowed_top_level

    bi_package = importlib.import_module("app.domains.bi")
    agent = importlib.import_module("app.domains.bi.agent")
    skill = importlib.import_module("app.domains.bi.skill")
    toolkit = importlib.import_module("app.domains.bi.toolkit")
    worker_contracts = importlib.import_module("app.domains.bi.worker.contracts")
    worker_runtime = importlib.import_module("app.domains.bi.worker.runtime")
    runtime_context = importlib.import_module("app.domains.bi.agent.runtime_context")

    assert bi_package.__all__ == []
    assert agent.BIAgentRunService.__module__ == "app.domains.bi.agent.run_service"
    assert skill.DatasetQuerySkill.__module__ == "app.domains.bi.skill.dataset_query"
    assert skill.AgentScopeDatasetRuntimeBridge.__module__ == "app.domains.bi.skill.runtime_bridge"
    assert toolkit.build_bi_atomic_toolkit.__module__ == "app.domains.bi.toolkit.atomic"
    assert worker_contracts.BIWorkerQueryPlan.__module__ == "app.domains.bi.worker.contracts"
    assert worker_runtime.BIWorkerQueryRuntime.__module__ == "app.domains.bi.worker.runtime"
    assert runtime_context.build_bi_runtime_context.__module__ == "app.domains.bi.agent.runtime_context"
