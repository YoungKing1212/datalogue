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

from app.schemas.bi_workbench import DatalogueEventEnvelope, build_datalogue_event_envelope
from app.services.agentscope_event_adapter import AgentScopeEventAdapter


def test_agentscope_event_adapter_maps_visibility_boundaries():
    adapter = AgentScopeEventAdapter()
    result = adapter.map_events(
        [
            DatalogueEventEnvelope(
                event_type="answer.completed",
                visibility="user_visible",
                task_id="task-1",
                payload={"answer": "安全摘要"},
            ),
            DatalogueEventEnvelope(
                event_type="route.started",
                visibility="trace_only",
                task_id="task-1",
                payload={"summary": "trace 摘要", "raw_sql": "select * from t"},
            ),
            DatalogueEventEnvelope(
                event_type="dataset.query.completed",
                visibility="control_plane",
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


def test_agentscope_event_adapter_maps_repair_events_without_control_plane():
    result = AgentScopeEventAdapter().map_events(
        [
            build_datalogue_event_envelope(
                event_type="repair.rerun_started",
                visibility="user_visible",
                task_id="task-1",
                trace_id="trace-1",
                payload={
                    "summary": "已生成自动修复方案，正在重新执行查询。",
                    "repair_plan_ref": "artifact:repair-1",
                    "checkpoint_ref": "checkpoint://conv-1-msg-2/repair",
                    "raw_sql": "select bad_col from work_log",
                    "patch": {"field": "bad_col"},
                },
            )
        ]
    )

    assert len(result.visible_events) == 1
    event = result.visible_events[0]
    assert event.event_type == "repair.rerun_started"
    assert event.channel == "shell_visible"
    assert event.trace_id == "trace-1"
    assert event.payload == {
        "summary": "已生成自动修复方案，正在重新执行查询。",
        "repair_plan_ref": "artifact:repair-1",
        "checkpoint_ref": "checkpoint://conv-1-msg-2/repair",
    }
    rendered = result.model_dump_json()
    assert "bad_col" not in rendered
    assert "work_log" not in rendered
