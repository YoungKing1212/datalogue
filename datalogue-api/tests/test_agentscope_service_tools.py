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

    assert [tool.name for tool in tools] == [
        "datalogue_search_assets",
        "datalogue_select_candidate_datasets",
        "datalogue_prepare_query_context",
        "datalogue_request_schema_slice",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
    ]
    assert "datalogue_query_dataset" not in {tool.name for tool in tools}
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


def test_bi_worker_progressive_tools_are_registered_for_team_worker():
    from app.agentscope_service.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(
        worker_context={
            "user_id": "u",
            "agent_id": "a",
            "agent_name": "worker",
            "session_id": "s",
        }
    )
    names = [tool.name for tool in tools]

    assert names == [
        "datalogue_prepare_query_context",
        "datalogue_request_schema_slice",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
    ]


@pytest.mark.asyncio
async def test_execute_query_plan_returns_repair_payload_after_repeated_contract_errors():
    from app.agentscope_service.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle")
    invalid_plan = {
        "intent": "detail_query",
        "question": "查询杨凯2025年日志",
        "result_shape": {"type": "table", "grain": "detail"},
        "data_graph": {
            "primary_entity": {
                "asset_ref": "table:pm_tenant.plan_task_daily_record",
                "alias": "log",
                "role": "fact",
            }
        },
        "select": [
            {
                "target": {
                    "asset_ref": "table:pm_tenant.plan_task_daily_record",
                    "alias": "log",
                    "field": "rzrq",
                },
                "display_name": "日志日期",
            }
        ],
    }

    first_chunk = await execute_tool(
        dataset_id=10,
        confirmed_question="查询杨凯2025年日志",
        query_plan=invalid_plan,
        context_state={},
    )
    second_chunk = await execute_tool(
        dataset_id=10,
        confirmed_question="查询杨凯2025年日志",
        query_plan=invalid_plan,
        context_state={},
    )

    first_payload = json.loads(first_chunk.content[0].text)
    second_payload = json.loads(second_chunk.content[0].text)

    assert first_chunk.state.name == "SUCCESS"
    assert first_payload["datalogue_event_type"] == "bi_worker_repair_request"
    assert first_payload["retry_policy"] == {
        "attempt": 1,
        "signature_attempt": 1,
        "total_attempt": 1,
        "max_retries": 1,
        "stop_retry": False,
    }
    assert first_payload["query_plan_contract_hint"]["detail_query_required_field"] == "selects"
    assert '"select"' not in json.dumps(first_payload, ensure_ascii=False)

    assert second_chunk.state.name == "SUCCESS"
    assert second_payload["datalogue_event_type"] == "bi_worker_repair_request"
    assert second_payload["repair_status"] == "failed"
    assert second_payload["retry_policy"] == {
        "attempt": 2,
        "signature_attempt": 2,
        "total_attempt": 2,
        "max_retries": 1,
        "stop_retry": True,
    }
    assert "TeamSay" in second_payload["recommended_action"]


@pytest.mark.asyncio
async def test_query_plan_contract_hint_points_to_real_operator_and_join_shape():
    from app.agentscope_service.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle")
    invalid_plan = {
        "intent": "detail_query",
        "question": "查询杨凯2025年日志",
        "result_shape": {"type": "table", "grain": "detail"},
        "data_graph": {
            "primary_entity": {"asset_ref": "table:pm_tenant.plan_task_daily_record", "alias": "log", "role": "fact"},
            "supporting_entities": [
                {"asset_ref": "table:pm_tenant.eas_personofile", "alias": "person", "role": "dimension"}
            ],
        },
        "join_requirements": [
            {
                "relationship_ref": "dataset_selected:table:pm_tenant.plan_task_daily_record->table:pm_tenant.eas_personofile",
                "join_type": "inner",
                "left_asset_ref": "table:pm_tenant.plan_task_daily_record",
                "right_asset_ref": "table:pm_tenant.eas_personofile",
            }
        ],
        "filters": [
            {
                "target": {
                    "asset_ref": "table:pm_tenant.eas_personofile.person_name",
                    "alias": "person",
                    "field": "person_name",
                },
                "operator": "eq",
                "value": "杨凯",
                "reason": "筛选人员姓名",
            }
        ],
        "selects": [
            {
                "target": {
                    "asset_ref": "table:pm_tenant.plan_task_daily_record.rzrq",
                    "alias": "log",
                    "field": "rzrq",
                },
                "display_name": "日志日期",
            }
        ],
        "metrics": [],
        "group_by": [],
        "ordering": [],
        "assumptions": [],
    }

    chunk = await execute_tool(
        dataset_id=10,
        confirmed_question="查询杨凯2025年日志",
        query_plan=invalid_plan,
        context_state={},
    )

    payload = json.loads(chunk.content[0].text)

    assert payload["query_plan_contract_hint"]["allowed_filter_operators"] == [
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "between",
        "in",
        "contains",
    ]
    assert payload["query_plan_contract_hint"]["join_requirement_shape"] == {
        "left_alias": "primary_entity_alias",
        "right_alias": "supporting_entity_alias",
        "relationship_ref": "relationship_ref_from_L2",
        "join_type": "inner",
        "required": True,
        "reason": "为什么必须关联该实体",
    }
    assert "literal_error:filters.0.operator" in payload["validation_error_summary"]
    assert "missing:join_requirements.0.left_alias" in payload["validation_error_summary"]
    assert "extra_forbidden:join_requirements.0.left_asset_ref" in payload["validation_error_summary"]


@pytest.mark.asyncio
async def test_query_plan_contract_total_attempts_stop_retry_across_changed_error_signatures():
    from app.agentscope_service.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle")
    first_invalid_plan = {"intent": "detail_query"}
    second_invalid_plan = {
        "intent": "detail_query",
        "question": "查询杨凯2025年日志",
        "result_shape": {"type": "table", "grain": "detail"},
        "data_graph": {
            "primary_entity": {"asset_ref": "table:pm_tenant.plan_task_daily_record", "alias": "main", "role": "fact"}
        },
        "join_requirements": [],
        "filters": [
            {
                "target": {
                    "asset_ref": "table:pm_tenant.plan_task_daily_record.xgr",
                    "alias": "main",
                    "field": "xgr",
                },
                "operator": "eq",
                "value": "杨凯",
                "reason": "筛选人员姓名",
            }
        ],
        "selects": [
            {
                "target": {
                    "asset_ref": "table:pm_tenant.plan_task_daily_record.rzrq",
                    "alias": "main",
                    "field": "rzrq",
                },
                "display_name": "日志日期",
            }
        ],
        "metrics": [],
        "group_by": [],
        "ordering": [],
        "assumptions": [],
    }

    first_chunk = await execute_tool(
        dataset_id=10,
        confirmed_question="查询杨凯2025年日志",
        query_plan=first_invalid_plan,
        context_state={},
    )
    second_chunk = await execute_tool(
        dataset_id=10,
        confirmed_question="查询杨凯2025年日志",
        query_plan=second_invalid_plan,
        context_state={},
    )

    first_payload = json.loads(first_chunk.content[0].text)
    second_payload = json.loads(second_chunk.content[0].text)

    assert first_payload["retry_policy"]["total_attempt"] == 1
    assert first_payload["retry_policy"]["stop_retry"] is False
    assert second_payload["retry_policy"]["total_attempt"] == 2
    assert second_payload["retry_policy"]["signature_attempt"] == 1
    assert second_payload["retry_policy"]["stop_retry"] is True


@pytest.mark.asyncio
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
