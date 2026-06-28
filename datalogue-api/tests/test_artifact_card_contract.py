# ============================================================
# File Name   : test_artifact_card_contract.py
# Description:
#   ArtifactCard 与公开引用契约测试。
#
# Responsibilities:
#   - 验证 final payload 只暴露 artifact/trace/checkpoint 引用。
#   - 验证 query_artifact 回填只接收 artifact:<uuid> 引用。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import json

from app.api.chat import (
    _artifact_refs_for_query_artifact,
    _attach_artifact_card_refs_to_final_payload,
)


def test_artifact_card_refs_do_not_expose_internal_details():
    payload = {
        "type": "final",
        "answer": "已完成查询。",
        "conversation_id": 7,
        "message_id": 9,
        "result_ref": "artifact:result-1",
        "report_ref": "artifact:report-1",
        "langfuse_trace_id": "trace-123",
        "retry_checkpoint": {"checkpoint_ref": "checkpoint://conv-7-msg-9/query_context_ready"},
        "sql": "select * from secret_table",
        "sql_result": {"rows": [{"raw": "value"}]},
    }

    _attach_artifact_card_refs_to_final_payload(payload)

    assert payload["task_id"] == "conv-7-msg-9"
    assert payload["trace_id"] == "trace-123"
    assert payload["primary_ref"]["ref_id"] == "artifact:result-1"
    related_ref_ids = {item["ref_id"] for item in payload["related_refs"]}
    assert related_ref_ids == {
        "artifact:report-1",
        "trace:trace-123",
        "checkpoint://conv-7-msg-9/query_context_ready",
    }
    card = payload["artifact_card"]
    assert card["primary_ref"]["ref_id"] == "artifact:result-1"
    assert {action["action_id"]: action for action in card["actions"]}["retry"]["payload_ref"] == "checkpoint://conv-7-msg-9/query_context_ready"
    assert {action["action_id"]: action for action in card["actions"]}["export"]["enabled"] is False
    assert {action["action_id"]: action for action in card["actions"]}["continue_edit"]["enabled"] is False

    visible_json = json.dumps(
        {
            "artifact_card": payload["artifact_card"],
            "primary_ref": payload["primary_ref"],
            "related_refs": payload["related_refs"],
        },
        ensure_ascii=False,
    )
    assert "secret_table" not in visible_json
    assert "sql_result" not in visible_json
    assert "raw" not in visible_json


def test_query_artifact_refs_only_include_artifact_handles():
    payload = {
        "primary_ref": {"ref_id": "artifact:result-1", "ref_type": "result"},
        "related_refs": [
            {"ref_id": "artifact:report-1", "ref_type": "report"},
            {"ref_id": "trace:trace-123", "ref_type": "trace"},
            {"ref_id": "checkpoint://conv-1-msg-2/query_context_ready", "ref_type": "checkpoint"},
        ],
    }

    refs = _artifact_refs_for_query_artifact(payload)

    assert refs == ["artifact:result-1", "artifact:report-1"]


def test_artifact_card_related_refs_accept_repair_plan_ref_without_new_prefix():
    payload = {
        "type": "final",
        "answer": "已自动修复字段口径并完成查询。",
        "conversation_id": 7,
        "message_id": 9,
        "result_ref": "artifact:result-1",
        "repair_plan_ref": "artifact:repair-1",
        "langfuse_trace_id": "trace-123",
        "retry_checkpoint": {"checkpoint_ref": "checkpoint://conv-7-msg-9/query_context_ready"},
    }

    _attach_artifact_card_refs_to_final_payload(payload)

    related_refs = payload["related_refs"]
    assert {"ref_id": "artifact:repair-1", "ref_type": "repair_plan", "label": "RepairPlan"} in related_refs
    assert all(not item["ref_id"].startswith("repair_plan:") for item in related_refs)
    assert "artifact:repair-1" in _artifact_refs_for_query_artifact(payload)
