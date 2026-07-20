# ============================================================
# File Name   : test_directory_facades.py
# Description:
#   验证 typed worker lane 目标目录 facade 能与旧模块入口并存。
#
# Responsibilities:
#   - 覆盖后端目录边界与 canonical 实现入口。
#   - 防止已经删除的兼容 facade 被生产调用方重新引入。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""typed worker lane 目录边界测试。"""

import importlib
import inspect
from importlib.util import find_spec
from pathlib import Path


def test_target_packages_are_importable():
    """目标领域包与运行时引擎入口均可直接导入。"""

    for module_name in [
        "app.domains.data_source",
        "app.domains.query_execution",
        "app.domains.agent_team",
        "app.domains.bi",
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


def test_removed_agentscope_runtime_facade_is_not_importable():
    """已删除的过渡 facade 不得以空目录或 namespace package 形式复活。"""

    assert find_spec("app.agentscope_runtime") is None


def test_runtime_engine_callers_use_canonical_modules():
    """Phase B Step 4c: 生产调用方直连 canonical 模块，禁止恢复已删除 facade。"""

    api_root = Path(__file__).resolve().parents[1] / "app"
    covered_callers = {
        api_root / "main.py": ("app.runtime.engine.app_factory", "app.runtime.engine.otel_setup"),
        api_root / "api" / "agent_team.py": ("app.runtime.engine.runner",),
        api_root / "api" / "agentscope_control_plane.py": ("app.runtime.engine.client",),
        api_root / "api" / "llm.py": ("app.runtime.engine.client",),
        api_root / "core" / "llm_config.py": ("app.runtime.engine.client",),
    }

    for caller, expected_modules in covered_callers.items():
        source = caller.read_text(encoding="utf-8")
        assert "app.agentscope_runtime" not in source
        for module_name in expected_modules:
            assert module_name in source


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
    """SQL Guard 留在领域层，标识符转义统一复用 core 的方言实现。"""

    domain_guard = importlib.import_module("app.domains.query_execution.guard")
    domain_names = importlib.import_module("app.domains.query_execution.dialect.names")
    core_identifiers = importlib.import_module("app.core.sql_identifiers")

    assert domain_guard.SQLGuardResult.__module__ == "app.domains.query_execution.guard"
    assert domain_guard.guard_readonly_sql.__module__ == "app.domains.query_execution.guard"
    assert domain_names.quote_ident is core_identifiers.quote_identifier
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
        "app/core/sql_identifiers.py"
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
        "capability_policy.py",
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


def test_domains_agent_team_boundary_exposes_datalogue_task_workbench_and_event_projection():
    """Phase E: domains/agent_team 只新增 Datalogue task、Workbench view/retry 与事件 envelope 边界。"""

    package = importlib.import_module("app.domains.agent_team")
    contracts = importlib.import_module("app.domains.agent_team.contracts")
    event_projection = importlib.import_module("app.domains.agent_team.event_projection")
    retry_actions = importlib.import_module("app.domains.agent_team.retry_actions")
    task_runtime = importlib.import_module("app.domains.agent_team.task_runtime")
    workbench_view = importlib.import_module("app.domains.agent_team.workbench_view")

    core_task_schema = importlib.import_module("app.core.schemas.agentscope_agent_team_task")
    core_task_model = importlib.import_module("app.core.models.agent_team_task")
    core_event_projection = importlib.import_module("app.core.events.projection")
    runtime = importlib.import_module("app.runtime.agent_team_runtime")
    workbench_actions = importlib.import_module("app.domains.workbench.actions")
    workbench_view_model = importlib.import_module("app.domains.workbench.view_model")

    assert package.__all__ == [
        "contracts",
        "event_projection",
        "retry_actions",
        "task_runtime",
        "workbench_view",
    ]
    assert contracts.AgentTeamTask is core_task_model.AgentTeamTask
    assert contracts.AgentTeamTaskRequest is core_task_schema.AgentTeamTaskRequest
    assert contracts.AgentTeamTaskStreamEvent is core_task_schema.AgentTeamTaskStreamEvent
    assert event_projection.build_task_envelope is core_event_projection.build_task_envelope
    assert event_projection.project_agentscope_event is core_event_projection.project_agentscope_event
    assert task_runtime.AgentTeamTaskRuntime is runtime.AgentTeamTaskRuntime
    assert retry_actions.request_controlled_retry is workbench_actions.request_controlled_retry
    assert retry_actions.validate_retry_checkpoint is workbench_actions.validate_retry_checkpoint
    assert workbench_view.build_workbench_thread_view is workbench_view_model.build_workbench_thread_view
    assert workbench_view.build_workbench_artifact_view is workbench_view_model.build_workbench_artifact_view
