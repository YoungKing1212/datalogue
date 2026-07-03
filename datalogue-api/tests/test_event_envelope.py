# ============================================================
# File Name   : test_event_envelope.py
# Description:
#   Datalogue 业务事件 envelope 契约测试。
#
# Responsibilities:
#   - 验证统一事件 envelope 的类型、可见性和脱敏边界。
#   - 验证 Agent Team task stream 使用统一事件 envelope。
#   - 固化 AgentScope Agent Team 需要的 ArtifactCard / outer payload 安全约束。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import json

import pytest

from app.schemas.bi_workbench import (
    ArtifactCard,
    ArtifactRef,
    DatalogueEventEnvelope,
    DatalogueEventType,
    DatalogueEventVisibility,
    build_datalogue_event_envelope,
    sanitize_event_payload,
)


def test_datalogue_event_envelope_supports_required_event_types_and_visibility():
    """统一事件 envelope 必须覆盖 P0.5 约定的业务事件和可见性集合。"""

    required_event_types = {
        "task.started",
        "agent.selected",
        "message.completed",
        "artifact.created",
        "answer.completed",
        "error.blocked",
        "repair.patch_applied",
    }
    assert required_event_types.issubset(set(DatalogueEventType.__args__))
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

    encoded_payload = json.dumps(
        {"payload": envelope.payload, "metadata": envelope.metadata, "legacy_payload": envelope.legacy_payload},
        ensure_ascii=False,
    ).lower()
    assert envelope.payload["answer"] == "GMV 为 100。"
    assert envelope.payload["artifact"] == {"result_ref": "artifact://result/1"}
    assert "select * from orders" not in encoded_payload
    assert "select amount from orders" not in encoded_payload
    assert "raw_sql" not in encoded_payload
    assert "sql_result" not in encoded_payload
    assert "rows" not in encoded_payload
    assert "schema" not in encoded_payload
    assert "capsule" not in encoded_payload
    assert "control_plane" not in encoded_payload


def test_user_visible_event_rejects_raw_sql_when_constructed_directly():
    with pytest.raises(ValueError):
        DatalogueEventEnvelope(
            event_type="dataset.query.completed",
            visibility="user_visible",
            task_id="task-1",
            payload={"raw_sql": "select * from t"},
        )


def test_user_visible_event_rejects_nested_control_plane():
    with pytest.raises(ValueError):
        DatalogueEventEnvelope(
            event_type="answer.completed",
            visibility="user_visible",
            task_id="task-1",
            payload={"artifact": {"control_plane": {"capsule": "secret"}}},
        )


def test_control_plane_event_can_exist_as_internal_input():
    event = DatalogueEventEnvelope(
        event_type="dataset.query.started",
        visibility="control_plane",
        task_id="task-1",
        payload={"raw_sql": "select * from t", "control_plane": {"ok": True}},
    )

    assert event.visibility == "control_plane"


def test_artifact_card_preview_payload_rejects_schema_details():
    with pytest.raises(ValueError):
        ArtifactCard(
            title="BI 查询结果",
            primary_ref=ArtifactRef(ref_id="artifact:answer:1"),
            preview_payload={"schema": {"tables": ["internal_table"]}},
        )


def test_sanitize_event_payload_drops_sensitive_keys_recursively():
    payload = sanitize_event_payload(
        {
            "answer": "ok",
            "raw_sql": "select * from t",
            "nested": {"capsule": {"secret": True}, "summary": "safe"},
        }
    )

    assert payload == {"answer": "ok", "nested": {"summary": "safe"}}
