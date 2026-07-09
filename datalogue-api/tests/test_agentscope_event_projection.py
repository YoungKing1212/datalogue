# ============================================================
# File Name   : test_agentscope_event_projection.py
# Description:
#   C3 AgentScope event projection 服务测试。
#
# Responsibilities:
#   - 验证 Datalogue event envelope 可投影为 AgentScope mirror event。
#   - 验证 artifact、checkpoint、trace 等业务级 refs 被抽取并关联到消息。
#
# Author      : yangkai
# Created On  : 2026-06-30
# ============================================================

import pytest

from app.core.schemas.bi_workbench import build_datalogue_event_envelope
from app.core.events.projection import (
    extract_refs_from_envelope,
    project_event_envelope_to_agentscope,
)
from app.services.agentscope_mirror import create_agentscope_session, create_running_assistant_message


def test_project_event_envelope_to_agentscope_event_and_refs(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_66666666-6666-6666-6666-666666666666",
        title="事件投影测试",
    )
    message = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    envelope = build_datalogue_event_envelope(
        event_type="artifact.created",
        visibility="user_visible",
        payload={
            "artifact_ref": "artifact:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "checkpoint_ref": "checkpoint:1",
            "summary": "查询产物已生成",
        },
        task_id="task-1",
        trace_id="trace-1",
    )

    event = project_event_envelope_to_agentscope(
        db_session,
        thread_id=session.thread_id,
        assistant_message_id=message.message_id,
        envelope=envelope,
    )

    assert event.event_type == "artifact.created"
    assert event.visibility == "user"
    assert event.task_id == "task-1"
    refs = {(ref.ref_type, ref.ref_value, ref.relation) for ref in session_refs(db_session, session.thread_id)}
    assert ("artifact", "artifact:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "primary") in refs
    assert ("checkpoint", "checkpoint:1", "checkpoint") in refs
    assert ("trace", "trace-1", "trace") in refs


def test_extract_refs_from_envelope_reads_primary_and_related_refs():
    envelope = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={
            "primary_ref": {"ref_type": "artifact", "ref": "artifact:primary"},
            "related_refs": [
                {"ref_type": "repair_plan", "ref": "artifact:repair"},
                {"ref_type": "checkpoint", "ref": "checkpoint:2"},
            ],
        },
        trace_id="trace-2",
    )

    refs = extract_refs_from_envelope(envelope)

    assert ("artifact", "artifact:primary", "primary") in refs
    assert ("repair_plan", "artifact:repair", "related") in refs
    assert ("checkpoint", "checkpoint:2", "checkpoint") in refs
    assert ("trace", "trace-2", "trace") in refs


def test_project_event_envelope_rejects_payload_with_internal_details(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_77777777-7777-7777-7777-777777777777",
        title="投影泄露测试",
    )
    message = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    envelope = build_datalogue_event_envelope(
        event_type="artifact.created",
        visibility="trace_only",
        payload={"compiled_sql": "select * from private_table"},
    )

    with pytest.raises(ValueError, match="AGENTSCOPE_MIRROR_PAYLOAD_LEAK_DETECTED"):
        project_event_envelope_to_agentscope(
            db_session,
            thread_id=session.thread_id,
            assistant_message_id=message.message_id,
            envelope=envelope,
        )


def test_project_event_envelope_normalizes_result_refs_before_leak_scan(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_99999999-9999-9999-9999-999999999999",
        title="结果引用投影测试",
    )
    message = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    envelope = build_datalogue_event_envelope(
        event_type="answer.completed",
        visibility="user_visible",
        payload={
            "answer": "已完成",
            "result_ref": "artifact:result",
            "report_ref": "artifact:report",
            "subagent_tool_results": [
                {"result_ref": "artifact:child-result", "sql": "select * from private_table"},
            ],
        },
        trace_id="trace-result",
    )

    event = project_event_envelope_to_agentscope(
        db_session,
        thread_id=session.thread_id,
        assistant_message_id=message.message_id,
        envelope=envelope,
    )

    assert "result_ref" not in event.payload_json
    assert event.payload_json["primary_ref"] == {"ref_type": "result", "ref": "artifact:result"}
    assert {"ref_type": "report", "ref": "artifact:report"} in event.payload_json["related_refs"]
    assert {"ref_type": "result", "ref": "artifact:child-result"} in event.payload_json["related_refs"]
    refs = {(ref.ref_type, ref.ref_value, ref.relation) for ref in session_refs(db_session, session.thread_id)}
    assert ("result", "artifact:result", "primary") in refs
    assert ("report", "artifact:report", "related") in refs
    assert ("result", "artifact:child-result", "related") in refs
    assert ("trace", "trace-result", "trace") in refs


def test_project_error_event_sanitizes_internal_database_error_text(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        title="错误事件脱敏测试",
    )
    message = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    envelope = build_datalogue_event_envelope(
        event_type="error.blocked",
        visibility="user_visible",
        payload={"answer": 'psycopg2.errors.UndefinedColumn: column "secret_name" does not exist'},
    )

    event = project_event_envelope_to_agentscope(
        db_session,
        thread_id=session.thread_id,
        assistant_message_id=message.message_id,
        envelope=envelope,
    )

    payload_text = str(event.payload_json)
    assert event.payload_json["answer"] == "问数执行失败，内部细节已隐藏。"
    assert "psycopg2" not in payload_text
    assert "secret_name" not in payload_text
    assert "does not exist" not in payload_text


def test_project_error_event_keeps_candidate_summary_and_drops_schema_metadata(db_session):
    session = create_agentscope_session(
        db_session,
        thread_id="as_abababab-abab-abab-abab-abababababab",
        title="候选数据集事件投影测试",
    )
    message = create_running_assistant_message(db_session, thread_id=session.thread_id, lease_seconds=60)
    envelope = build_datalogue_event_envelope(
        event_type="error.blocked",
        visibility="user_visible",
        payload={
            "reason": "没有 Manifest 达到自动路由阈值。",
            "route_decision": {
                "decision": "no_match",
                "bound_schema_version": "internal-schema-v1",
                "candidates": [
                    {
                        "dataset_id": 10,
                        "dataset_name": "生产经营管理系统日志数据集",
                        "reason": "业务问题可能相关。",
                        "requires_confirmation": True,
                    }
                ],
            },
        },
    )

    event = project_event_envelope_to_agentscope(
        db_session,
        thread_id=session.thread_id,
        assistant_message_id=message.message_id,
        envelope=envelope,
    )

    payload_text = str(event.payload_json)
    assert event.payload_json["route_decision"]["candidates"][0]["dataset_name"] == "生产经营管理系统日志数据集"
    assert "bound_schema_version" not in payload_text
    assert "schema" not in payload_text


def session_refs(db_session, thread_id):
    from app.core.models.agentscope_workbench import AgentScopeRef

    return db_session.query(AgentScopeRef).filter(AgentScopeRef.thread_id == thread_id).all()
