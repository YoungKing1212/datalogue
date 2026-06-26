# ============================================================
# File Name   : test_event_envelope.py
# Description:
#   DatalogueEventEnvelope 可见性边界测试。
#
# Responsibilities:
#   - 验证 user_visible 事件不能携带 SQL、schema 和 control_plane 字段。
#   - 验证 trace_only/control_plane 事件可作为内部协议输入，但不代表用户可见。
#   - 固化 ArtifactCard preview_payload 的外层安全约束。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import pytest

from app.schemas.bi_workbench import (
    ArtifactCard,
    ArtifactRef,
    DatalogueEventEnvelope,
    EventVisibility,
    sanitize_outer_payload,
)


def test_user_visible_event_rejects_raw_sql():
    with pytest.raises(ValueError):
        DatalogueEventEnvelope(
            event_type="dataset.query.completed",
            visibility=EventVisibility.USER_VISIBLE,
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
        event_type="dataset.query.internal",
        visibility=EventVisibility.CONTROL_PLANE,
        task_id="task-1",
        payload={"raw_sql": "select * from t", "control_plane": {"ok": True}},
    )

    assert event.visibility == EventVisibility.CONTROL_PLANE


def test_artifact_card_preview_payload_rejects_schema_details():
    with pytest.raises(ValueError):
        ArtifactCard(
            title="BI 查询结果",
            primary_ref=ArtifactRef(ref="artifact:answer:1"),
            preview_payload={"schema": {"tables": ["internal_table"]}},
        )


def test_sanitize_outer_payload_drops_sensitive_keys_recursively():
    payload = sanitize_outer_payload(
        {
            "answer": "ok",
            "raw_sql": "select * from t",
            "nested": {"capsule": {"secret": True}, "summary": "safe"},
        }
    )

    assert payload == {"answer": "ok", "nested": {"summary": "safe"}}
