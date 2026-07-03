# ============================================================
# File Name   : test_agentscope_service_projection.py
# Description:
#   AgentScope Service 事件到 Datalogue Envelope 的投影测试。
#
# Responsibilities:
#   - 保证 AgentScope 原始事件不会直接暴露给前端。
#   - 保证 SQL/schema/raw rows/DSL/query_plan 等敏感内容被过滤。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json


def test_projection_filters_sensitive_payload_with_lead_agent_sanitizer():
    from app.agentscope_service.projection import project_agentscope_service_event

    envelope = project_agentscope_service_event(
        {
            "event_type": "message",
            "payload": {
                "content": "select * from contracts",
                "artifact_ref": "artifact:1",
                "checkpoint_ref": "checkpoint:1",
                "schema": {"tables": ["contract_table"]},
                "raw_rows": [{"amount": 100}],
                "dsl": {"metric": "amount"},
                "query_plan": {"steps": ["scan"]},
            },
        },
        task_id="task-1",
        trace_id="trace-1",
        selected_agent="bi_agent",
        thread_id="thread-1",
        message_id="message-1",
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).lower()
    assert envelope.event_type == "message.delta"
    assert envelope.task_id == "task-1"
    assert envelope.trace_id == "trace-1"
    assert envelope.thread_id == "thread-1"
    assert envelope.message_id == "message-1"
    assert envelope.selected_agent == "bi_agent"
    assert envelope.payload["artifact_ref"] == "artifact:1"
    assert envelope.payload["checkpoint_ref"] == "checkpoint:1"
    assert "select *" not in encoded
    assert "schema" not in encoded
    assert "raw_rows" not in encoded
    assert "dsl" not in encoded
    assert "query_plan" not in encoded


def test_projection_maps_terminal_and_tool_events_to_stable_event_types():
    from app.agentscope_service.projection import project_agentscope_service_event

    completed = project_agentscope_service_event(
        {"type": "final", "payload": {"summary": "任务已完成", "artifact_ref": "artifact:2"}},
        task_id="task-2",
        trace_id="trace-2",
        selected_agent="bi_agent",
    )
    tool = project_agentscope_service_event(
        {"type": "tool_result", "payload": {"summary": "工具执行完成", "row_count": 3}},
        task_id="task-3",
        trace_id="trace-3",
        selected_agent="bi_agent",
    )

    assert completed.event_type == "message.completed"
    assert completed.payload == {"summary": "任务已完成", "artifact_ref": "artifact:2"}
    assert tool.event_type == "tool.result"
    assert tool.payload == {"summary": "工具执行完成", "row_count": 3}
