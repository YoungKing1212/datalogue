# ============================================================
# File Name   : test_agentic_shell_contract.py
# Description:
#   Datalogue Agentic Shell-first AS-R0 契约测试。
#
# Responsibilities:
#   - 验证 AS-R0 只启用 BI 主链 Agent，其他业务 Agent 作为 disabled placeholder。
#   - 验证 Agentic Shell 的工具白名单、上下文投影和输出清洗安全边界。
#   - 验证 BI atomic tool provider 第一阶段只暴露安全目录摘要，不泄露 SQL/schema/raw rows。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from app.models.dataset import AnalysisBlueprint
from app.services.agentic_bi_tools import BIAtomicToolProvider
from app.services.agentic_shell import DatalogueAgenticShell


def test_agentic_shell_as_r0_registry_enables_only_bi_main_chain():
    shell = DatalogueAgenticShell()

    contract = shell.prepare_turn(
        question="查询 GMV 和订单数",
        context={"dataset_id": 12, "thread_id": "thread-1"},
    )

    assert contract.status == "ready"
    assert contract.task_type == "bi_query"
    assert contract.selected_agent == "bi_lead_agent"
    assert contract.enabled_agents == ["bi_lead_agent"]
    assert {"report_agent", "python_agent", "audit_agent"}.issubset(contract.disabled_agents)

    assert contract.tool_policy.allowed_tools == [
        "get_dataset_status",
        "list_candidate_assets",
        "get_artifact_summary",
    ]
    assert contract.tool_policy.business_capabilities == ["query_dataset", "query_multiple_datasets"]
    assert "ask_bi" not in contract.tool_policy.allowed_tools
    assert "compile_dsl_to_sql" in contract.tool_policy.disabled_tools
    assert "execute_compiled_query" in contract.tool_policy.disabled_tools
    assert "create_query_artifact" in contract.tool_policy.disabled_tools
    assert "repair_dsl" in contract.tool_policy.disabled_tools
    assert "create_report_from_artifact" in contract.tool_policy.disabled_tools


def test_agentic_shell_context_projection_and_output_sanitizer_drop_execution_payloads():
    shell = DatalogueAgenticShell()

    contract = shell.prepare_turn(
        question="查询销售额",
        context={
            "dataset_id": 12,
            "conversation_id": 7,
            "sql": "select * from orders",
            "schema_context": {"tables": ["orders"]},
            "raw_rows": [{"amount": 1}],
            "query_plan": {"steps": ["internal"]},
            "blueprint": {"raw_sql": "select 1"},
            "safe_note": "保留业务上下文",
        },
    )

    dumped_context = contract.projected_context.model_dump()
    assert dumped_context == {
        "conversation_id": 7,
        "dataset_id": 12,
        "question": "查询销售额",
        "safe_note": "保留业务上下文",
    }

    sanitized = shell.sanitize_output(
        {
            "answer": "已生成查询结果",
            "sql": "select * from orders",
            "artifact": {
                "artifact_ref": "artifact:query:1",
                "raw_rows": [{"amount": 1}],
                "schema": {"orders": ["amount"]},
            },
            "events": [{"type": "checkpoint", "repair_patch": {"body": "internal"}}],
            "debug": {
                "queryPlan": {"steps": ["internal"]},
                "repairPatch": {"body": "internal"},
                "rows": [{"n": 1}],
                "fields": ["orders.amount"],
                "safe_label": "GMV",
            },
        }
    )

    assert sanitized == {
        "answer": "已生成查询结果",
        "artifact": {"artifact_ref": "artifact:query:1"},
        "events": [{"type": "checkpoint"}],
        "debug": {"safe_label": "GMV"},
    }


def test_agentic_shell_non_bi_task_routes_to_disabled_placeholder_without_tools():
    shell = DatalogueAgenticShell()

    contract = shell.prepare_turn(question="根据查询结果生成一份经营报告")

    assert contract.status == "disabled"
    assert contract.task_type == "report"
    assert contract.selected_agent == "report_agent"
    assert contract.enabled_agents == ["bi_lead_agent"]
    assert "report_agent" in contract.disabled_agents
    assert contract.tool_policy.allowed_tools == []


def test_bi_atomic_tool_provider_exposes_safe_dataset_status_and_full_catalog(
    db_session,
    sample_dataset,
):
    blueprint = AnalysisBlueprint(
        dataset_id=sample_dataset.id,
        name="区域销售诊断",
        description="按区域定位销售变化",
        trigger_keywords=["区域", "销售"],
        when_to_use="需要解释区域销售变化时使用",
        raw_sql="select * from secret_orders",
        status="active",
    )
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(blueprint)

    provider = BIAtomicToolProvider(db_session)

    status = provider.get_dataset_status(sample_dataset.id)
    catalog = provider.list_candidate_assets(sample_dataset.id, question="这个参数第一阶段保留但不参与召回")

    assert status == {
        "dataset_id": sample_dataset.id,
        "name": "测试数据集",
        "status": "active",
        "metric_count": 2,
        "dimension_count": 2,
        "blueprint_count": 1,
        "metadata_schema_summary": {"selected_table_count": 0},
    }
    assert catalog["dataset_id"] == sample_dataset.id
    assert catalog["question_used"] is False
    assert [item["name"] for item in catalog["metric"]] == ["GMV", "订单数"]
    assert [item["name"] for item in catalog["dimension"]] == ["地区", "品类"]
    assert catalog["blueprint"] == [
        {
            "id": blueprint.id,
            "name": "区域销售诊断",
            "description": "按区域定位销售变化",
            "trigger_keywords": ["区域", "销售"],
            "when_to_use": "需要解释区域销售变化时使用",
        }
    ]

    dumped = repr(catalog) + repr(status)
    for forbidden in ("raw_sql", "select *", "schema_context", "raw_rows", "orders.amount"):
        assert forbidden not in dumped
