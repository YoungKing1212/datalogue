# ============================================================
# File Name   : test_event_envelope.py
# Description:
#   Datalogue 业务事件 envelope 契约测试。
#
# Responsibilities:
#   - 验证统一事件 envelope 的类型、可见性和脱敏边界。
#   - 验证 /chat/stream SSE 兼容旧 payload 的同时追加事件 envelope。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import json


def test_datalogue_event_envelope_supports_required_event_types_and_visibility():
    """统一事件 envelope 必须覆盖 P0.5 约定的业务事件和可见性集合。"""

    from app.schemas.bi_workbench import (
        DatalogueEventEnvelope,
        DatalogueEventType,
        DatalogueEventVisibility,
        build_datalogue_event_envelope,
    )

    assert set(DatalogueEventType.__args__) == {
        "task.started",
        "route.started",
        "dataset.selected",
        "clarification.required",
        "dataset.query.started",
        "dataset.query.completed",
        "repair.evaluated",
        "repair.plan_created",
        "repair.confirmation_required",
        "repair.patch_applied",
        "repair.rerun_started",
        "repair.rerun_completed",
        "repair.failed",
        "repair.blocked",
        "retry.started",
        "retry.checkpoint_restored",
        "retry.fallback_to_whole_task",
        "retry.completed",
        "retry.failed",
        "artifact.created",
        "answer.completed",
        "error.blocked",
    }
    assert set(DatalogueEventVisibility.__args__) == {
        "user_visible",
        "trace_only",
        "control_plane",
    }

    envelope = build_datalogue_event_envelope(
        event_type="route.started",
        visibility="trace_only",
        payload={"route": "manifest"},
        metadata={"conversation_id": 10},
    )

    assert isinstance(envelope, DatalogueEventEnvelope)
    assert envelope.event_type == "route.started"
    assert envelope.visibility == "trace_only"
    assert envelope.payload == {"route": "manifest"}
    assert envelope.metadata["conversation_id"] == 10
    assert envelope.event_id
    assert envelope.created_at is not None


def test_user_visible_event_envelope_removes_sensitive_query_material():
    """用户可见事件不能泄露 raw SQL、完整结果集、schema、capsule 或控制面主体。"""

    from app.schemas.bi_workbench import build_datalogue_event_envelope

    envelope = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={
            "answer": "GMV 为 100。",
            "sql": "SELECT * FROM orders",
            "raw_sql": "select amount from orders",
            "sql_result": {"rows": [{"amount": 100}], "columns": ["amount"]},
            "schema": {"tables": ["orders"]},
            "query_task_capsule": {"dataset_id": 1, "sql": "select 1"},
            "control_plane": {"capsule": {"raw_sql": "select 2"}},
            "artifact": {"result_ref": "artifact://result/1"},
        },
        metadata={
            "conversation_id": 10,
            "raw_sql": "SELECT 1",
            "capsule": {"dataset_id": 1},
        },
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).lower()
    assert envelope.payload["answer"] == "GMV 为 100。"
    assert envelope.payload["artifact"] == {"result_ref": "artifact://result/1"}
    assert "select * from orders" not in encoded
    assert "raw_sql" not in encoded
    assert "sql_result" not in encoded
    assert "rows" not in encoded
    assert "schema" not in encoded
    assert "capsule" not in encoded
    assert "control_plane" not in encoded


def test_chat_sse_payload_sanitizes_legacy_fields_and_adds_event_envelope():
    """SSE 追加 envelope 时，顶层兼容字段也不能泄露内部执行面。"""

    from app.api.chat import _with_event_envelope

    legacy_payload = {
        "type": "final",
        "answer": "查询完成",
        "sql": "SELECT * FROM orders",
        "sql_result": {"rows": [{"amount": 100}]},
        "conversation_id": 10,
        "message_id": 20,
        "route_decision": {"decision": "selected", "dataset_id": 1},
        "result_ref": "artifact://result/1",
    }

    payload = _with_event_envelope(
        legacy_payload,
        event_type="answer.completed",
        visibility="user_visible",
        payload_fields=("answer", "result_ref", "sql", "sql_result"),
    )

    assert payload["type"] == "final"
    assert payload["answer"] == "查询完成"
    encoded = json.dumps(payload, ensure_ascii=False).lower()
    assert "sql" not in payload
    assert "sql_result" not in payload
    assert "select * from orders" not in encoded
    assert "orders" not in encoded
    assert "rows" not in encoded
    assert payload["event_envelope"]["event_type"] == "answer.completed"
    assert payload["event_envelope"]["visibility"] == "user_visible"
    assert payload["event_envelope"]["payload"] == {
        "answer": "查询完成",
        "result_ref": "artifact://result/1",
    }
    assert payload["event_envelope"]["metadata"] == {
        "conversation_id": 10,
        "message_id": 20,
        "dataset_id": 1,
        "route_decision": {"decision": "selected", "dataset_id": 1},
    }


def test_repair_event_envelope_only_exposes_business_summary_and_refs():
    """RepairPlan 用户可见事件只暴露业务摘要、状态和 ref，不暴露 patch/SQL/schema。"""

    from app.schemas.bi_workbench import build_datalogue_event_envelope

    envelope = build_datalogue_event_envelope(
        event_type="repair.plan_created",
        visibility="user_visible",
        payload={
            "summary": "已识别字段口径不匹配，准备按业务口径自动修复。",
            "status": "plan_created",
            "requires_user_confirmation": False,
            "repair_plan_ref": "artifact:repair-1",
            "checkpoint_ref": "checkpoint://conv-1-msg-2/repair",
            "patch": {"target_field": "work_log.bad_col", "replacement_field": "work_date"},
            "raw_sql": "select bad_col from work_log",
            "schema": {"tables": ["work_log"]},
            "raw_result": {"rows": []},
        },
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).lower()
    assert envelope.payload == {
        "summary": "已识别字段口径不匹配，准备按业务口径自动修复。",
        "status": "plan_created",
        "requires_user_confirmation": False,
        "repair_plan_ref": "artifact:repair-1",
        "checkpoint_ref": "checkpoint://conv-1-msg-2/repair",
    }
    assert "bad_col" not in encoded
    assert "work_log" not in encoded
    assert "select" not in encoded
    assert "schema" not in encoded
    assert "raw_result" not in encoded


def test_chat_sse_public_payload_removes_final_internal_debug_fields():
    """final SSE 顶层只保留安全摘要；调试字段必须留在后端 trace/store。"""

    from app.api.chat import _with_event_envelope

    payload = _with_event_envelope(
        {
            "type": "final",
            "answer": "查询完成",
            "query_plan": {"debug": {"sql_template": "SELECT secret_col FROM hidden_table"}},
            "candidate_assets": {"fields": [{"column_name": "secret_col"}]},
            "dsl": {"direct_sql": "SELECT secret_col FROM hidden_table"},
            "sql": "SELECT secret_col FROM hidden_table",
            "sql_list": ["SELECT secret_col FROM hidden_table"],
            "sql_result": {
                "columns": ["secret_col"],
                "rows": [{"secret_col": "private"}],
            },
            "sql_diagnosis": {"root_cause": "missing secret_col"},
            "query_profile": {"sql": {"statement": "SELECT secret_col FROM hidden_table"}},
            "explainability": {"query_profile": {"sql": {"statement": "SELECT secret_col"}}},
            "response_metadata": {"query_plan": {"debug": "hidden_table.secret_col"}},
            "result_artifact": {"result_ref": "result:1", "rows": [{"secret_col": "private"}]},
            "result_ref": "artifact:result-1",
            "repair_plan": {"summary": "已生成业务级修复方案"},
        },
        event_type="answer.completed",
        visibility="user_visible",
        payload_fields=("answer", "result_ref", "repair_plan"),
    )

    encoded = json.dumps(payload, ensure_ascii=False).lower()
    assert payload["answer"] == "查询完成"
    assert payload["result_ref"] == "artifact:result-1"
    assert payload["repair_plan"] == {"summary": "已生成业务级修复方案"}
    assert "query_plan" not in payload
    assert "candidate_assets" not in payload
    assert "dsl" not in payload
    assert "query_profile" not in payload
    assert "explainability" not in payload
    assert "response_metadata" not in payload
    assert "result_artifact" not in payload
    assert "sql" not in payload
    assert "sql_result" not in payload
    assert "secret_col" not in encoded
    assert "hidden_table" not in encoded
    assert "select" not in encoded


def test_chat_sse_public_payload_keeps_repair_patch_summary_but_removes_internal_body():
    """RepairPatch 公开层只能暴露业务摘要/ref，完整 patch 和 apply 详情留在 trace/store。"""

    from app.api.chat import _with_event_envelope

    payload = _with_event_envelope(
        {
            "type": "step",
            "node": "repair_patch",
            "status": "done",
            "repair_plan_ref": "artifact:repair-1",
            "repair_patch_summary": {
                "repair_strategy": "按业务口径自动修复字段引用。",
                "failure_class": "FIELD_MAPPING_DRIFT",
                "confidence_band": "high",
                "validation_summary": "修复方案已通过工具校验。",
            },
            "repair_patch": {
                "operations": [
                    {
                        "replacement_field_ref": "work_log.work_date",
                        "target_path": ["selected_assets", 0, "metadata", "column_name"],
                    }
                ],
                "trace_only_metadata": {"replacement_field_ref": "work_log.work_date"},
            },
            "repair_patch_apply": {
                "trace_only_details": [{"before": "missing_date", "after": "work_date"}],
            },
            "raw_sql": "select missing_date from work_log",
        },
        event_type="repair.patch_applied",
        visibility="user_visible",
        payload_fields=("repair_plan_ref", "repair_patch_summary"),
    )

    encoded = json.dumps(payload, ensure_ascii=False).lower()
    assert payload["repair_plan_ref"] == "artifact:repair-1"
    assert payload["repair_patch_summary"]["failure_class"] == "FIELD_MAPPING_DRIFT"
    assert "repair_patch" not in payload
    assert "repair_patch_apply" not in payload
    assert "replacement_field_ref" not in encoded
    assert "work_log" not in encoded
    assert "missing_date" not in encoded
    assert "select" not in encoded


def test_chat_sse_trace_only_event_envelope_payload_removes_internal_details():
    """trace_only envelope 只要随 SSE 下发给浏览器，也不能携带内部执行面。"""

    from app.api.chat import _with_event_envelope

    payload = _with_event_envelope(
        {
            "type": "step",
            "node": "query_plan",
            "query_plan": {"debug": {"sql_template": "SELECT secret_col FROM hidden_table"}},
            "candidate_assets": {
                "fields": [{"table_name": "hidden_table", "column_name": "secret_col"}],
            },
            "schema_summary": ["hidden_table.secret_col"],
        },
        event_type="dataset.query.started",
        visibility="trace_only",
        payload_fields=("type", "node", "query_plan", "candidate_assets", "schema_summary"),
    )

    encoded = json.dumps(payload, ensure_ascii=False).lower()
    assert payload["event_envelope"]["visibility"] == "trace_only"
    assert payload["event_envelope"]["payload"] == {"type": "step"}
    assert "query_plan" not in payload
    assert "candidate_assets" not in payload
    assert "schema_summary" not in payload
    assert "query_plan" not in json.dumps(payload["event_envelope"], ensure_ascii=False).lower()
    assert "secret_col" not in encoded
    assert "hidden_table" not in encoded
    assert "select" not in encoded
