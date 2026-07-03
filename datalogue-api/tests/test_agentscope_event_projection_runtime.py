# ============================================================
# File Name   : test_agentscope_event_projection_runtime.py
# Description:
#   AgentScope 原生事件到 Datalogue envelope 的投影测试。
#
# Responsibilities:
#   - 验证 external tool required/result 事件映射到稳定 tool.* envelope。
#   - 验证文本增量和终态事件不泄露 AgentScope SDK 对象结构。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState

from app.events.projection import (
    build_task_envelope,
    project_agentscope_event,
)


def test_project_require_external_execution_event_to_tool_required():
    event = RequireExternalExecutionEvent(
        reply_id="reply-1",
        id="evt-require-1",
        tool_calls=[
            ToolCallBlock(id="call-1", name="get_dataset_status", input='{"dataset_id":12}')
        ],
    )

    envelope = project_agentscope_event(
        event,
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type == "tool.external_required"
    assert envelope.payload["tool_calls"][0]["name"] == "get_dataset_status"
    assert "input" not in envelope.payload["tool_calls"][0]


def test_project_external_execution_result_event_to_tool_result():
    event = ExternalExecutionResultEvent(
        reply_id="reply-1",
        id="evt-result-1",
        execution_results=[
            ToolResultBlock(
                id="call-1",
                name="get_dataset_status",
                state=ToolResultState.SUCCESS,
                output=[TextBlock(text='{"status":"ready","summary":"可查询"}')],
            )
        ],
    )

    envelope = project_agentscope_event(
        event,
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type == "tool.result"
    assert envelope.payload["results"][0]["name"] == "get_dataset_status"
    assert envelope.payload["results"][0]["state"] == "success"


def test_build_task_envelope_rejects_visible_internal_payload():
    envelope = build_task_envelope(
        event_type="task.failed",
        task_id="task-1",
        trace_id="trace-1",
        payload={"error_summary": "select * from hidden_table"},
    )

    assert "select" not in str(envelope.payload).lower()


def test_project_legacy_sse_final_to_message_completed():
    envelope = project_agentscope_event(
        {"data": '{"type":"final","answer":"合同总金额为 100 万元","trace_id":"trace-legacy"}'},
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type == "message.completed"
    assert envelope.legacy_payload["answer"] == "合同总金额为 100 万元"
    assert envelope.trace_id == "trace-legacy"


def test_project_legacy_answer_completed_envelope_to_message_completed():
    envelope = project_agentscope_event(
        {
            "data": (
                '{"answer":"合同总金额为 100 万元",'
                '"event_envelope":{"event_type":"answer.completed","payload":{"answer":"合同总金额为 100 万元"}}}'
            )
        },
        task_id="task-1",
        trace_id="trace-1",
        thread_id="as_1",
        message_id="msg-1",
        selected_agent="bi_agent",
    )

    assert envelope.event_type == "message.completed"
    assert envelope.legacy_payload["answer"] == "合同总金额为 100 万元"
