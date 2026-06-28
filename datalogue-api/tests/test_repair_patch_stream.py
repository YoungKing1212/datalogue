# ============================================================
# File Name   : test_repair_patch_stream.py
# Description:
#   C2 PR2 RepairPatch 接入 SQL 失败重跑链路测试。
#
# Responsibilities:
#   - 验证 sql_audit 后进入 RepairPatch 节点，而不是让 LLM 重新生成 SQL。
#   - 验证 RepairPatch 只修补 QueryPlan / compiler binding，并重新走工具编译。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import json

from app.services.subagent_planning import CandidateAsset, QueryPlan


def _field_asset(name: str, table_name: str, column_name: str) -> CandidateAsset:
    return CandidateAsset(
        asset_type="field",
        asset_id=f"{table_name}.{column_name}",
        name=name,
        display_name=name,
        source="schema",
        confidence=0.9,
        metadata={"table_name": table_name, "column_name": column_name},
        usage="selected",
    )


def test_sql_audit_router_sends_field_failures_to_repair_patch_node():
    from app.graph.workflow import _sql_audit_router

    state = {
        "sql_audit_result": {
            "retryable": True,
            "severity": "fixable",
            "code": "FIELD_NOT_FOUND",
        },
        "repair_plan": {"failure_class": "FIELD_NOT_FOUND"},
        "repair_status": "plan_created",
        "query_plan": {"selected_assets": []},
        "retry_count": 0,
        "max_retry_count": 1,
    }

    assert _sql_audit_router(state) == "repair_patch"


def test_sql_audit_router_sends_field_mapping_drift_to_repair_patch_node():
    from app.graph.workflow import _sql_audit_router

    state = {
        "sql_audit_result": {
            "retryable": True,
            "severity": "fixable",
            "code": "FIELD_MAPPING_DRIFT",
        },
        "repair_plan": {"failure_class": "FIELD_MAPPING_DRIFT"},
        "repair_status": "plan_created",
        "query_plan": {"selected_assets": []},
        "retry_count": 0,
        "max_retry_count": 1,
    }

    assert _sql_audit_router(state) == "repair_patch"


def test_build_workflow_registers_repair_patch_without_state_key_collision(db_session):
    from app.graph.workflow import build_workflow

    workflow = build_workflow(db_session)

    assert workflow is not None


def test_repair_patch_node_applies_query_plan_patch_and_recompiles(db_session, sample_dataset):
    from app.graph.nodes import repair_patch_node

    failed_plan = QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.88,
        selected_assets=[_field_asset("工作日期", "work_log", "missing_date")],
        debug={"selected_main_table": "work_log"},
    )
    state = {
        "question": "查询某员工 2024 年工作日志",
        "dataset_id": sample_dataset.id,
        "query_plan": failed_plan.to_dict(),
        "sql_generation_context": {
            "table_schemas": [
                {
                    "table_name": "work_log",
                    "fields": [
                        {"column_name": "work_date", "display_name": "工作日期"},
                        {"column_name": "person_name", "display_name": "人员姓名"},
                    ],
                }
            ]
        },
        "datasource_context": {
            "dialect": "sqlite",
            "allowed_tables": ["work_log"],
        },
        "query_constraints": {"enabled": False},
        "sql_audit_result": {"code": "FIELD_NOT_FOUND", "retryable": True},
        "sql_diagnosis": {"wrong_field": "missing_date", "suggested_fix": "改用工作日期字段"},
        "repair_plan": {
            "schema_version": "repair_plan.v1",
            "failure_class": "FIELD_NOT_FOUND",
            "status": "plan_created",
            "attempts": 1,
        },
        "repair_status": "plan_created",
        "retry_count": 0,
        "sql_retry_trace": [{"attempt": 1, "status": "pending"}],
    }

    result = repair_patch_node(db_session)(state)

    assert result["repair_status"] == "patch_applied"
    assert result["should_retry"] is False
    assert result["dsl"] == {"compiled_query_plan": True}
    assert result["query_plan_compilation"]["ok"] is True
    assert '"work_log"."work_date"' in result["query_plan_compilation"]["sql"]
    assert "missing_date" not in result["query_plan_compilation"]["sql"]
    assert result["repair_patch_summary"]["confidence_band"] in {"high", "medium"}
    assert result["repair_patch"]["trace_only_metadata"]["replacement_field_ref"] == "work_log.work_date"
    assert result["sql_retry_trace"][0]["status"] == "patch_applied"
    assert "work_log" not in json.dumps(result["repair_patch_summary"], ensure_ascii=False)
    assert "sql" not in json.dumps(result["repair_patch_summary"], ensure_ascii=False).lower()


def test_repair_patch_node_blocks_raw_sql_patch_payload(db_session, sample_dataset):
    from app.graph.nodes import repair_patch_node

    state = {
        "question": "查询某员工 2024 年工作日志",
        "dataset_id": sample_dataset.id,
        "query_plan": {
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "confidence": 0.88,
            "selected_assets": [],
            "debug": {},
            "raw_sql": "SELECT * FROM work_log",
        },
        "sql_generation_context": {},
        "datasource_context": {"dialect": "sqlite", "allowed_tables": ["work_log"]},
        "sql_audit_result": {"code": "FIELD_NOT_FOUND", "retryable": True},
        "sql_diagnosis": {"wrong_field": "missing_date"},
        "repair_plan": {"failure_class": "FIELD_NOT_FOUND", "attempts": 1},
        "repair_status": "plan_created",
        "sql_retry_trace": [],
    }

    result = repair_patch_node(db_session)(state)

    assert result["repair_status"] == "blocked"
    assert result["should_retry"] is False
    assert result["query_plan_compilation"]["ok"] is False
    assert result["query_plan_compilation"]["code"] == "REPAIR_PATCH_BLOCKED"
    assert "raw_sql" not in json.dumps(result["repair_patch_summary"], ensure_ascii=False).lower()
