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


def test_target_packages_are_importable():
    """目标领域包先作为兼容层存在，迁移期不要求承载新业务逻辑。"""

    for module_name in [
        "app.domains.data_source",
        "app.domains.query_execution",
        "app.domains.agent_team",
        "app.domains.bi",
        "app.runtime.engine",
    ]:
        assert importlib.import_module(module_name)


def test_data_source_service_facade_reexports_legacy_public_capabilities():
    """data_source.service 必须复用旧 datasource 服务对象，保证新旧入口同源。"""

    legacy = importlib.import_module("app.services.datasource")
    facade = importlib.import_module("app.domains.data_source.service")

    assert facade.create_engine_for_datasource is legacy.create_engine_for_datasource
    assert facade.test_connection is legacy.test_connection
    assert facade.sync_source_tables is legacy.sync_source_tables


def test_query_execution_preview_facade_reexports_legacy_function():
    """SQL preview facade 必须指向旧实现，避免迁移期复制执行逻辑。"""

    legacy = importlib.import_module("app.services.sql_preview")
    facade = importlib.import_module("app.domains.query_execution.preview")

    assert facade.preview_dataset_sql is legacy.preview_dataset_sql


def test_runtime_engine_app_factory_is_direct_source():
    """runtime.engine.app_factory 是 create_embedded_agentscope_app 的直接实体，不再经过中间 facade。"""

    engine = importlib.import_module("app.runtime.engine.app_factory")
    assert callable(engine.create_embedded_agentscope_app)


def test_data_source_implementation_lives_in_domain_modules():
    """Phase C 要求数据源实现进入统一领域目录，同时旧入口保持同源兼容。"""

    legacy = importlib.import_module("app.services.datasource")
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
    assert service.preview_table.__module__ == "app.domains.data_source.service"

    assert inspect.getsourcefile(capabilities.DatasourceCapability).endswith(
        "app/domains/data_source/capabilities.py"
    )
    assert inspect.getsourcefile(context.DatasourceContext).endswith("app/domains/data_source/context.py")
    assert inspect.getsourcefile(diagnostics.DatasourceDiagnostic).endswith(
        "app/domains/data_source/diagnostics.py"
    )
    assert inspect.getsourcefile(base.DatasourceAdapter).endswith(
        "app/domains/data_source/adapters/base.py"
    )
    assert inspect.getsourcefile(hive.HiveAdapter).endswith("app/domains/data_source/adapters/hive.py")
    assert inspect.getsourcefile(oracle.OracleAdapter).endswith(
        "app/domains/data_source/adapters/oracle.py"
    )
    assert inspect.getsourcefile(registry.get_adapter).endswith(
        "app/domains/data_source/adapters/registry.py"
    )
    assert "class DatasourceAdapter" in inspect.getsource(base.DatasourceAdapter)
    assert "class HiveAdapter" in inspect.getsource(hive.HiveAdapter)
    assert "class OracleAdapter" in inspect.getsource(oracle.OracleAdapter)
    assert "def get_adapter" in inspect.getsource(registry.get_adapter)

    # 旧入口复用新领域对象，避免迁移期出现两套注册表或两套服务函数。
    assert legacy.test_connection is service.test_connection
    assert legacy.get_adapter is registry.get_adapter
    assert legacy.DatasourceAdapter is base.DatasourceAdapter


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
    """G041 要求 SQL 方言适配器与查询计划编译器进入 query_execution，旧 service 路径只做门面。"""

    legacy_adapter = importlib.import_module("app.services.sql_dialect_adapter")
    domain_adapter = importlib.import_module("app.domains.query_execution.dialect.adapter")
    legacy_compiler = importlib.import_module("app.services.query_plan_compiler")
    domain_compiler = importlib.import_module("app.domains.query_execution.compiler")

    assert domain_adapter.adapt_sql_for_execution.__module__ == (
        "app.domains.query_execution.dialect.adapter"
    )
    assert domain_adapter.quote_identifier.__module__ == "app.domains.query_execution.dialect.adapter"
    assert domain_compiler.compile_query_plan_to_sql.__module__ == "app.domains.query_execution.compiler"

    # 旧 service 路径复用 domain 对象，避免迁移期间出现两套 SQL 编译/适配规则。
    assert legacy_adapter.adapt_sql_for_execution is domain_adapter.adapt_sql_for_execution
    assert legacy_adapter.quote_identifier is domain_adapter.quote_identifier
    assert legacy_compiler.compile_query_plan_to_sql is domain_compiler.compile_query_plan_to_sql

    assert inspect.getsourcefile(domain_adapter.adapt_sql_for_execution).endswith(
        "app/domains/query_execution/dialect/adapter.py"
    )
    assert inspect.getsourcefile(domain_compiler.compile_query_plan_to_sql).endswith(
        "app/domains/query_execution/compiler.py"
    )


def test_query_execution_preview_implementation_lives_in_domain_module():
    """G042 要求 SQL preview 实现进入 query_execution，旧 service 路径只做兼容门面。"""

    legacy = importlib.import_module("app.services.sql_preview")
    domain = importlib.import_module("app.domains.query_execution.preview")

    assert domain.preview_dataset_sql.__module__ == "app.domains.query_execution.preview"
    assert legacy.preview_dataset_sql is domain.preview_dataset_sql
    assert inspect.getsourcefile(domain.preview_dataset_sql).endswith(
        "app/domains/query_execution/preview.py"
    )


def test_query_execution_artifact_and_repair_implementation_lives_in_domain_modules():
    """G043 要求 ArtifactStore 与 RepairPlan 服务进入 query_execution，旧 service 路径只做门面。"""

    legacy_artifact = importlib.import_module("app.services.artifact_store")
    domain_artifact = importlib.import_module("app.domains.query_execution.artifact_store")
    legacy_repair = importlib.import_module("app.services.repair_plan")
    domain_repair = importlib.import_module("app.domains.query_execution.repair_plan")

    assert domain_artifact.ArtifactStore.__module__ == "app.domains.query_execution.artifact_store"
    assert domain_repair.validate_repair_plan.__module__ == "app.domains.query_execution.repair_plan"
    assert domain_repair.sanitize_repair_plan_artifact_payload.__module__ == (
        "app.domains.query_execution.repair_plan"
    )

    # 旧 service 路径必须复用新领域对象，避免 Artifact/RepairPlan 出现两套安全边界。
    assert legacy_artifact.ArtifactStore is domain_artifact.ArtifactStore
    assert legacy_artifact.ArtifactPayloadTooLargeError is domain_artifact.ArtifactPayloadTooLargeError
    assert legacy_repair.validate_repair_plan is domain_repair.validate_repair_plan
    assert legacy_repair.sanitize_repair_plan_artifact_payload is (
        domain_repair.sanitize_repair_plan_artifact_payload
    )

    assert inspect.getsourcefile(domain_artifact.ArtifactStore).endswith(
        "app/domains/query_execution/artifact_store.py"
    )
    assert inspect.getsourcefile(domain_repair.validate_repair_plan).endswith(
        "app/domains/query_execution/repair_plan.py"
    )
