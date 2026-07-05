# ============================================================
# File Name   : test_agentscope_service_tools.py
# Description:
#   AgentScope Service 额外工具注册测试。
#
# Responsibilities:
#   - 验证 Datalogue extra_agent_tools 不重复注入 AgentScope Service 已内置的通用工具。
#   - 验证 Dataset Query 业务工具只对 Agent Team worker 可见。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json
import logging

import pytest


AGENTSCOPE_SERVICE_BUILTIN_TOOL_NAMES = {
    "Bash",
    "Read",
    "Write",
    "Edit",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
}


@pytest.mark.asyncio
async def test_extra_agent_tools_hides_dataset_tool_from_leader():
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    class FakeAgentRecord:
        source = "user"

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            assert user_id == "user-1"
            assert agent_id == "leader-1"
            return FakeAgentRecord()

    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())

    leader_tools = await factory("user-1", "leader-1", "session-1")

    assert leader_tools == []
    assert AGENTSCOPE_SERVICE_BUILTIN_TOOL_NAMES.isdisjoint({tool.name for tool in leader_tools})


@pytest.mark.asyncio
async def test_extra_agent_tools_returns_dataset_tool_for_team_worker_only():
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    class FakeAgentRecord:
        source = "team"

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            assert user_id == "user-1"
            assert agent_id == "worker-bi-1"
            return FakeAgentRecord()

    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())

    tools = await factory("user-1", "worker-bi-1", "session-1")

    assert [tool.name for tool in tools] == ["datalogue_select_candidate_datasets", "datalogue_query_dataset"]
    assert AGENTSCOPE_SERVICE_BUILTIN_TOOL_NAMES.isdisjoint({tool.name for tool in tools})


@pytest.mark.asyncio
async def test_extra_agent_tools_fail_closed_without_agent_record():
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            return None

    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())

    tools = await factory("user-1", "missing-agent", "session-1")

    assert tools == []


@pytest.mark.asyncio
async def test_bi_worker_dataset_tool_prints_safe_worker_logs(monkeypatch, caplog):
    from app.agentscope_service import tools as tools_module
    from app.agentscope_service.dataset_query_executor import AgentTeamDatasetQueryResult
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "bi-worker"

    class FakeAgentRecord:
        source = "team"
        data = FakeAgentData()

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            assert user_id == "user-1"
            assert agent_id == "worker-bi-1"
            return FakeAgentRecord()

    async def fake_execute_dataset_query_for_agent_team(**kwargs):
        assert kwargs["dataset_id"] == 12
        return AgentTeamDatasetQueryResult(
            answer_summary="查询已完成，结果已生成 artifact_ref=artifact:ok，共 2 行、3 列。",
            artifact_ref="artifact:ok",
            checkpoint_ref="checkpoint:ok",
            row_count=2,
            column_count=3,
        )

    monkeypatch.setattr(
        tools_module,
        "execute_dataset_query_for_agent_team",
        fake_execute_dataset_query_for_agent_team,
    )
    with caplog.at_level(logging.INFO, logger="app.agentscope_service.tools"):
        factory = build_datalogue_extra_agent_tools(storage=FakeStorage())
        tools = await factory("user-1", "worker-bi-1", "worker-session-1")
        tool = next(item for item in tools if item.name == "datalogue_query_dataset")
        chunk = await tool(
            dataset_id=12,
            confirmed_question="查询杨凯2025年日志",
            trace_id="trace-1",
        )

    assert chunk.state.name == "SUCCESS"
    payload = json.loads(chunk.content[0].text)
    assert payload["datalogue_event_type"] == "dataset_query_result"
    assert payload["summary"] == "查询已完成，结果已生成 artifact_ref=artifact:ok，共 2 行、3 列。"
    assert payload["result_ref"] == "artifact:ok"
    assert payload["artifact_ref"] == "artifact:ok"
    assert payload["artifact_card"]["title"] == "查询结果"
    assert payload["artifact_card"]["primary_ref"] == {
        "ref_id": "artifact:ok",
        "ref_type": "result",
        "label": "查询结果",
    }
    assert payload["artifact_card"]["actions"][0] == {
        "action_type": "view",
        "label": "查看详情",
        "ref": "artifact:ok",
        "disabled": False,
    }
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.bi_worker.toolkit.attached]" in logs
    assert "[agentscope.bi_worker.dataset_query.started]" in logs
    assert "[agentscope.bi_worker.dataset_query.completed]" in logs
    assert '"agent_id": "worker-bi-1"' in logs
    assert '"agent_name": "bi-worker"' in logs
    assert '"session_id": "worker-session-1"' in logs
    assert '"dataset_id": 12' in logs
    assert '"row_count": 2' in logs
    assert "查询杨凯2025年日志" not in logs
    assert "SELECT" not in logs


@pytest.mark.asyncio
async def test_bi_worker_candidate_dataset_tool_returns_safe_candidates(monkeypatch):
    from app.agentscope_service import tools as tools_module
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "bi-worker"

    class FakeAgentRecord:
        source = "team"
        data = FakeAgentData()

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            return FakeAgentRecord()

    def fake_select_candidate_datasets_for_agent_team(*, question: str, limit: int = 5):
        assert question == "查询杨凯2025年日志"
        assert limit == 5
        return {
            "datalogue_event_type": "dataset_candidates",
            "summary": "BI worker 已筛选候选数据集，请用户确认。",
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
            "requires_user_confirmation": True,
        }

    monkeypatch.setattr(
        tools_module,
        "select_candidate_datasets_for_agent_team",
        fake_select_candidate_datasets_for_agent_team,
    )
    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())
    tools = await factory("user-1", "worker-bi-1", "worker-session-1")
    tool = next(item for item in tools if item.name == "datalogue_select_candidate_datasets")

    chunk = await tool(question="查询杨凯2025年日志")

    payload = chunk.content[0].text
    assert chunk.state.name == "SUCCESS"
    assert "生产经营管理系统日志数据集" in payload
    assert "secret_col" not in payload
    assert "hidden_table" not in payload
    assert "SELECT" not in payload


@pytest.mark.asyncio
async def test_bi_worker_candidate_dataset_tool_publishes_safe_final_event(monkeypatch):
    from app.agentscope_service import tools as tools_module
    from app.agentscope_service.progress_bridge import agent_progress_subscription
    from app.agentscope_service.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "bi-worker"

    class FakeAgentRecord:
        source = "team"
        data = FakeAgentData()

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            return FakeAgentRecord()

    def fake_select_candidate_datasets_for_agent_team(*, question: str, limit: int = 5):
        return {
            "datalogue_event_type": "dataset_candidates",
            "summary": "BI worker 已筛选候选数据集，请用户确认。",
            "route_decision": {
                "decision": "ambiguous",
                "candidates": [
                    {
                        "dataset_id": 10,
                        "dataset_name": "生产经营管理系统日志数据集",
                        "reason": "匹配日志查询",
                    }
                ],
            },
            "clarification": {"kind": "dataset_choice"},
            "requires_user_confirmation": True,
        }

    monkeypatch.setattr(
        tools_module,
        "select_candidate_datasets_for_agent_team",
        fake_select_candidate_datasets_for_agent_team,
    )

    async with agent_progress_subscription(user_id="user-1") as queue:
        factory = build_datalogue_extra_agent_tools(storage=FakeStorage())
        tools = await factory("user-1", "worker-bi-1", "worker-session-1")
        tool = next(item for item in tools if item.name == "datalogue_select_candidate_datasets")
        await tool(question="查询杨凯2025年日志")

        event = queue.get_nowait()

    assert event["event_type"] == "message.completed"
    assert event["payload"]["datalogue_event_type"] == "dataset_candidates"
    assert event["payload"]["requires_user_confirmation"] is True
    assert event["payload"]["route_decision"]["candidates"][0]["dataset_id"] == 10
