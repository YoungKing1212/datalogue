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
        selected_agent="bi_worker",
        thread_id="thread-1",
        message_id="message-1",
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).lower()
    assert envelope.event_type == "message.delta"
    assert envelope.task_id == "task-1"
    assert envelope.trace_id == "trace-1"
    assert envelope.thread_id == "thread-1"
    assert envelope.message_id == "message-1"
    assert envelope.selected_agent == "bi_worker"
    assert envelope.payload["artifact_ref"] == "artifact:1"
    assert envelope.payload["checkpoint_ref"] == "checkpoint:1"
    assert "select *" not in encoded
    assert "schema" not in encoded
    assert "raw_rows" not in encoded
    assert "dsl" not in encoded
    assert "query_plan" not in encoded


def test_projection_preserves_message_delta_whitespace():
    """message.delta 增量必须保留 token 边界空格/换行，避免英文被 strip 粘成一坨。"""

    from app.agentscope_service.projection import project_agentscope_service_event

    first = project_agentscope_service_event(
        {"event_type": "message.delta", "payload": {"content": " Now I need to"}},
        task_id="task-delta",
        trace_id="trace-delta",
        selected_agent="agent_team_leader",
    )
    second = project_agentscope_service_event(
        {"event_type": "message.delta", "payload": {"content": " present this\n"}},
        task_id="task-delta",
        trace_id="trace-delta",
        selected_agent="agent_team_leader",
    )

    assert first.event_type == "message.delta"
    # 拼接后仍保留空格与换行，前端才能还原正常表述并分小节
    assert first.payload["content"] + second.payload["content"] == " Now I need to present this\n"


def test_projection_maps_terminal_and_tool_events_to_stable_event_types():
    from app.agentscope_service.projection import project_agentscope_service_event

    completed = project_agentscope_service_event(
        {"event_type": "ReplyEndEvent", "payload": {"summary": "任务已完成", "artifact_ref": "artifact:2"}},
        task_id="task-2",
        trace_id="trace-2",
        selected_agent="bi_worker",
    )
    tool = project_agentscope_service_event(
        {"type": "tool_result", "payload": {"summary": "工具执行完成", "row_count": 3}},
        task_id="task-3",
        trace_id="trace-3",
        selected_agent="bi_worker",
    )

    assert completed.event_type == "message.completed"
    assert completed.payload == {"summary": "任务已完成", "artifact_ref": "artifact:2"}
    assert tool.event_type == "tool.result"
    assert tool.payload == {"summary": "工具执行完成", "row_count": 3}


def test_projection_preserves_agent_progress_as_realtime_safe_event():
    from app.agentscope_service.projection import project_agentscope_service_event

    envelope = project_agentscope_service_event(
        {
            "event_type": "agent.progress",
            "payload": {
                "agent_role": "worker",
                "agent_name": "BI Worker",
                "phase": "dataset_match",
                "status": "running",
                "title": "候选数据集筛选",
                "summary": "已识别日志查询，正在筛选候选数据集。",
                "schema": {"tables": ["hidden_table"]},
                "raw_rows": [{"name": "secret"}],
                "query_plan": {"steps": ["scan"]},
                "sql": "select * from hidden_table",
            },
        },
        task_id="task-progress",
        trace_id="trace-progress",
        selected_agent="agent_team_leader",
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).lower()
    assert envelope.event_type == "agent.progress"
    assert envelope.payload == {
        "agent_role": "worker",
        "agent_name": "BI Worker",
        "phase": "dataset_match",
        "status": "running",
        "title": "候选数据集筛选",
        "summary": "已识别日志查询，正在筛选候选数据集。",
    }
    assert "hidden_table" not in encoded
    assert "raw_rows" not in encoded
    assert "query_plan" not in encoded
    assert "select *" not in encoded


def test_projection_preserves_worker_dataset_candidates_safely():
    from app.agentscope_service.projection import project_agentscope_service_event

    envelope = project_agentscope_service_event(
        {
            "event_type": "ReplyEndEvent",
            "payload": {
                "summary": "BI worker 已筛选候选数据集，请用户确认。",
                "datalogue_event_type": "dataset_candidates",
                "route_decision": {
                    "decision": "ambiguous",
                    "dataset_id": None,
                    "candidates": [
                        {
                            "dataset_id": 10,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "reason": "匹配日志查询",
                            "requires_confirmation": True,
                            "schema": {"fields": ["secret_col"]},
                            "raw_sql": "SELECT secret_col FROM hidden_table",
                        }
                    ],
                },
                "clarification": {
                    "kind": "dataset_choice",
                    "candidates": [
                        {
                            "dataset_id": 10,
                            "dataset_name": "生产经营管理系统日志数据集",
                            "reason": "匹配日志查询",
                        }
                    ],
                },
            },
        },
        task_id="task-dataset-choice",
        trace_id="trace-dataset-choice",
        selected_agent="agent_team_leader",
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
    assert envelope.event_type == "message.completed"
    assert envelope.payload["summary"] == "BI worker 已筛选候选数据集，请用户确认。"
    assert envelope.payload["route_decision"]["decision"] == "ambiguous"
    assert envelope.payload["route_decision"]["candidates"] == [
        {
            "dataset_id": 10,
            "dataset_name": "生产经营管理系统日志数据集",
            "reason": "匹配日志查询",
            "requires_confirmation": True,
        }
    ]
    assert envelope.payload["clarification"]["kind"] == "dataset_choice"
    assert "secret_col" not in encoded
    assert "hidden_table" not in encoded
    assert "SELECT" not in encoded


def test_projection_does_not_treat_block_end_events_as_message_completed():
    from app.agentscope_service.projection import project_agentscope_service_event

    for raw_type in ("TextBlockEndEvent", "ThinkingBlockEndEvent", "ModelCallEndEvent"):
        envelope = project_agentscope_service_event(
            {"event_type": raw_type, "payload": {"summary": "分段结束"}},
            task_id="task-block-end",
            trace_id="trace-block-end",
            selected_agent="bi_worker",
        )

        assert envelope.event_type == "trace.updated"


def test_projection_never_maps_thinking_delta_to_message_delta():
    """ThinkingBlockDeltaEvent.delta 是 raw thinking，不能绕过 debug gate 进入 message.delta。"""

    from app.agentscope_service.projection import project_agentscope_service_event

    envelope = project_agentscope_service_event(
        {
            "event_type": "ThinkingBlockDeltaEvent",
            "reply_id": "reply-1",
            "block_id": "think-1",
            "delta": "先分析用户问题，再构造 select * from hidden_table",
        },
        task_id="task-thinking",
        trace_id="trace-thinking",
        selected_agent="agent_team_leader",
    )

    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False).lower()
    assert envelope.event_type == "trace.updated"
    assert envelope.payload["phase"] == "thinking"
    assert envelope.payload["reply_id"] == "reply-1"
    assert envelope.payload["block_id"] == "think-1"
    assert "先分析用户问题" not in encoded
    assert "select *" not in encoded
    assert "hidden_table" not in encoded
    assert "message.delta" not in encoded


def test_projection_maps_subagent_hitl_custom_event_to_confirmation_required():
    from app.agentscope_service.projection import project_agentscope_service_event

    envelope = project_agentscope_service_event(
        {
            "type": "CUSTOM",
            "name": "subagent_require_user_confirm",
            "value": {
                "worker_session_id": "worker-session-1",
                "worker_agent_id": "worker-agent-1",
                "worker_agent_name": "bi-worker",
                "reply_id": "reply-1",
                "event_type": "require_user_confirm",
                "event": {
                    "type": "REQUIRE_USER_CONFIRM",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "Glob",
                            "input": '{"pattern":"**/*","path":"/tmp/private"}',
                            "state": "asking",
                        }
                    ],
                },
                "created_at": "2026-07-04T13:41:10",
            },
        },
        task_id="task-hitl",
        trace_id="trace-hitl",
        selected_agent="agent_team_leader",
        thread_id="as_1",
        message_id="msg_1",
    )

    assert envelope.event_type == "confirmation.required"
    assert envelope.payload == {
        "summary": "bi-worker 正在等待确认工具调用 Glob。",
        "title": "Worker 需要确认",
        "agent": "bi-worker",
        "agent_name": "bi-worker",
        "worker_session_id": "worker-session-1",
        "worker_agent_id": "worker-agent-1",
        "reply_id": "reply-1",
        "tool_name": "Glob",
        "tool_call_id": "call-1",
        "tool_calls": [{"id": "call-1", "name": "Glob", "state": "asking"}],
        "requires_user_confirmation": True,
        "confirmation_kind": "require_user_confirm",
    }
    encoded = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
    assert "pattern" not in encoded
    assert "/tmp/private" not in encoded
