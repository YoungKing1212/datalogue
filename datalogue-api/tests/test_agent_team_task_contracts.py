# ============================================================
# File Name   : test_agent_team_task_contracts.py
# Description:
#   AgentScope Agent Team 统一任务入口的模型与 DTO 契约测试。
#
# Responsibilities:
#   - 验证 task request 拒绝 SQL/schema/raw rows 等内部执行态。
#   - 验证 Datalogue event envelope 支持 task/agent/tool/message/ref 事件族。
#   - 验证 AgentTeamTask 模型字段能保存 task 真相源。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

import pytest

from app.core.models.agent_team_task import AgentTeamTask
from app.core.schemas.agentscope_agent_team_task import AgentTeamTaskRequest
from app.core.safety import sanitize_datalogue_payload
from app.core.schemas.bi_workbench import build_datalogue_event_envelope


def test_agent_team_task_request_rejects_internal_payload_keys():
    with pytest.raises(ValueError, match="AGENT_TEAM_TASK_INTERNAL_PAYLOAD_REJECTED"):
        AgentTeamTaskRequest(
            task_source="chat",
            task_type="bi_query",
            question="统计合同总金额",
            dataset_id=12,
            client_context={"schema_context": {"tables": ["hidden_table"]}},
        )


def test_agent_team_task_request_allows_workbench_retry_refs():
    request = AgentTeamTaskRequest(
        task_source="workbench",
        task_type="bi_query",
        question="重试上一步",
        dataset_id=12,
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        retry_checkpoint_ref="checkpoint://as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/msg-1/query_context_ready",
        artifact_ref="artifact:abc123",
        client_context={"action": "retry_last_step"},
    )

    assert request.task_source == "workbench"
    assert request.retry_checkpoint_ref.startswith("checkpoint://")
    assert request.client_context == {"action": "retry_last_step"}


def test_agent_team_task_request_and_output_allow_legitimate_free_text():
    request = AgentTeamTaskRequest(
        task_source="chat",
        question="create a chart from sales，显示同比增长 12.5% 和枚举值 1.5L",
    )

    sanitized = sanitize_datalogue_payload({"answer_summary": "同比增长 12.5%，规格为 1.5L"})

    assert request.question.startswith("create a chart")
    assert sanitized["answer_summary"] == "同比增长 12.5%，规格为 1.5L"


def test_agent_team_task_request_requires_complete_agentscope_model_selection():
    with pytest.raises(
        ValueError, match="AGENTSCOPE_MODEL_SELECTION_REQUIRES_CREDENTIAL_AND_MODEL"
    ):
        AgentTeamTaskRequest(
            task_source="chat",
            task_type="bi_query",
            question="统计销售趋势",
            model_credential_id="openai_credential:prod-main",
        )

    request = AgentTeamTaskRequest(
        task_source="chat",
        task_type="bi_query",
        question="统计销售趋势",
        model_credential_id="openai_credential:prod-main",
        model_name="gpt-4.1-mini",
        model_parameters={"thinking_enable": True},
    )

    assert request.model_credential_id == "openai_credential:prod-main"
    assert request.model_name == "gpt-4.1-mini"
    assert request.model_parameters == {"thinking_enable": True}


def test_datalogue_event_envelope_supports_agent_team_event_types():
    for event_type in (
        "task.started",
        "task.completed",
        "task.failed",
        "task.cancelled",
        "agent.selected",
        "agent.handoff.started",
        "agent.handoff.completed",
        "agent.handoff.failed",
        "message.delta",
        "message.completed",
        "confirmation.required",
        "tool.external_required",
        "tool.result",
        "tool.blocked",
        "checkpoint.created",
        "artifact.ready",
        "trace.updated",
    ):
        envelope = build_datalogue_event_envelope(
            event_type=event_type,
            visibility="user_visible",
            payload={"summary": "安全摘要"},
            task_id="task-agent-team-1",
            trace_id="trace-agent-team-1",
            thread_id="as_1",
            message_id="msg_1",
            selected_agent="agent_team_leader",
        )
        assert envelope.event_type == event_type
        assert envelope.task_id == "task-agent-team-1"
        assert envelope.thread_id == "as_1"
        assert envelope.selected_agent == "agent_team_leader"


def test_agent_team_task_model_persists_truth_source(db_session):
    task = AgentTeamTask(
        task_id="task-agent-team-contract",
        task_source="chat",
        task_type="bi_query",
        status="running",
        selected_agent="agent_team_leader",
        agent_scope_session_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        thread_id="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        message_id="msg-agent-team-1",
        trace_id="trace-agent-team-1",
        artifact_refs_json=["artifact:abc"],
        checkpoint_refs_json=["checkpoint://abc"],
        request_payload_json={"question": "统计合同总金额"},
    )
    db_session.add(task)
    db_session.commit()

    stored = db_session.query(AgentTeamTask).filter_by(task_id="task-agent-team-contract").one()
    assert stored.status == "running"
    assert stored.artifact_refs_json == ["artifact:abc"]
