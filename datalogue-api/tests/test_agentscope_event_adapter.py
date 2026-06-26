# ============================================================
# File Name   : test_agentscope_event_adapter.py
# Description:
#   AgentScopeEventAdapter 映射边界测试。
#
# Responsibilities:
#   - 验证 user_visible 事件进入 Shell 可见事件。
#   - 验证 trace_only 事件只进入 trace 事件。
#   - 验证 control_plane 事件不会进入 AgentScope 可见输出。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from app.schemas.bi_workbench import DatalogueEventEnvelope, EventVisibility
from app.services.agentscope_event_adapter import AgentScopeEventAdapter


def test_agentscope_event_adapter_maps_visibility_boundaries():
    adapter = AgentScopeEventAdapter()
    result = adapter.map_events(
        [
            DatalogueEventEnvelope(
                event_type="answer.completed",
                visibility=EventVisibility.USER_VISIBLE,
                task_id="task-1",
                payload={"answer": "安全摘要"},
            ),
            DatalogueEventEnvelope(
                event_type="planner.trace",
                visibility=EventVisibility.TRACE_ONLY,
                task_id="task-1",
                payload={"summary": "trace 摘要", "raw_sql": "select * from t"},
            ),
            DatalogueEventEnvelope(
                event_type="dataset.query.control",
                visibility=EventVisibility.CONTROL_PLANE,
                task_id="task-1",
                payload={"control_plane": {"raw_sql": "select * from t"}},
            ),
        ]
    )

    assert [event.channel for event in result.visible_events] == ["shell_visible"]
    assert result.visible_events[0].payload == {"answer": "安全摘要"}
    assert [event.channel for event in result.trace_events] == ["trace"]
    assert result.trace_events[0].payload == {"summary": "trace 摘要"}
    assert result.dropped_internal_count == 1
    rendered = result.model_dump_json()
    assert "select * from t" not in rendered
    assert "control_plane" not in rendered


def test_agentscope_event_adapter_accepts_dict_envelopes():
    result = AgentScopeEventAdapter().map_events(
        [
            {
                "event_type": "answer.completed",
                "visibility": "user_visible",
                "task_id": "task-1",
                "payload": {"answer": "ok"},
            }
        ]
    )

    assert result.visible_events[0].event_type == "answer.completed"
