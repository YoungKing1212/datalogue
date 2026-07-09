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
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

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
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "bi-worker"
        system_prompt = "你是 Datalogue BI Worker，只处理 Datalogue Dataset Query 类问数任务。"

    class FakeAgentRecord:
        source = "team"
        data = FakeAgentData()

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
        "datalogue_describe_tables",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
    ]
    assert "datalogue_query_dataset" not in {tool.name for tool in tools}
    assert AGENTSCOPE_SERVICE_BUILTIN_TOOL_NAMES.isdisjoint({tool.name for tool in tools})


@pytest.mark.asyncio
async def test_extra_agent_tools_returns_report_tool_for_report_worker_only():
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "report-worker"
        system_prompt = "你是 Datalogue Report Worker。REPORT_WORKER_BOUNDARY"

    class FakeAgentRecord:
        source = "team"
        data = FakeAgentData()

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            assert user_id == "user-1"
            assert agent_id == "worker-report-1"
            return FakeAgentRecord()

    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())

    tools = await factory("user-1", "worker-report-1", "session-1")

    assert [tool.name for tool in tools] == ["datalogue_get_artifact_report_input"]
    assert "datalogue_execute_query_plan_bundle" not in {tool.name for tool in tools}
    assert AGENTSCOPE_SERVICE_BUILTIN_TOOL_NAMES.isdisjoint({tool.name for tool in tools})


@pytest.mark.asyncio
async def test_extra_agent_tools_fail_closed_for_unmarked_team_worker():
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "team-worker"
        system_prompt = "普通 Team worker，没有 Datalogue marker。"

    class FakeAgentRecord:
        source = "team"
        data = FakeAgentData()

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            return FakeAgentRecord()

    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())

    tools = await factory("user-1", "worker-unknown", "session-1")

    assert tools == []


@pytest.mark.asyncio
async def test_extra_agent_tools_fail_closed_without_agent_record():
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

    class FakeStorage:
        async def get_agent(self, user_id, agent_id):
            return None

    factory = build_datalogue_extra_agent_tools(storage=FakeStorage())

    tools = await factory("user-1", "missing-agent", "session-1")

    assert tools == []


def test_bi_worker_progressive_tools_are_registered_for_team_worker():
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

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
        "datalogue_describe_tables",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
    ]


@pytest.mark.asyncio
async def test_execute_query_plan_returns_repair_payload_after_repeated_contract_errors():
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(
        tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
    )
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
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(
        tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
    )
    invalid_plan = {
        "intent": "detail_query",
        "question": "查询杨凯2025年日志",
        "result_shape": {"type": "table", "grain": "detail"},
        "data_graph": {
            "primary_entity": {
                "asset_ref": "table:pm_tenant.plan_task_daily_record",
                "alias": "log",
                "role": "fact",
            },
            "supporting_entities": [
                {
                    "asset_ref": "table:pm_tenant.eas_personofile",
                    "alias": "person",
                    "role": "dimension",
                }
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
        "join_keys": [
            {"left_field": "left_table_field_name", "right_field": "right_table_field_name"},
        ],
    }
    assert "literal_error:filters.0.operator" in payload["validation_error_summary"]
    assert "missing:join_requirements.0.left_alias" in payload["validation_error_summary"]
    assert (
        "extra_forbidden:join_requirements.0.left_asset_ref" in payload["validation_error_summary"]
    )
    details = {item["path"]: item for item in payload["validation_error_details"]}
    assert details["filters.0.operator"]["expected"].startswith("把 operator 改为允许值之一")
    assert "`=`" in details["filters.0.operator"]["expected"]
    assert "left_alias" in details["join_requirements.0.left_asset_ref"]["expected"]
    assert "relationship_ref" in details["join_requirements.0.right_asset_ref"]["expected"]
    assert "left_alias" in details["join_requirements.0.left_alias"]["expected"]
    assert "right_alias" in details["join_requirements.0.right_alias"]["expected"]


@pytest.mark.asyncio
async def test_query_plan_contract_details_explain_legacy_join_fields():
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(
        tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
    )
    invalid_plan = {
        "intent": "detail_query",
        "question": "统计合同总金额",
        "result_shape": {"type": "table", "grain": "detail"},
        "data_graph": {
            "primary_entity": {"asset_ref": "asset:contract", "alias": "contract", "role": "fact"},
            "supporting_entities": [
                {"asset_ref": "asset:customer", "alias": "customer", "role": "dimension"},
                {"asset_ref": "asset:org", "alias": "org", "role": "dimension"},
                {"asset_ref": "asset:person", "alias": "person", "role": "dimension"},
            ],
        },
        "join_requirements": [
            {
                "left": "contract",
                "right": "customer",
                "type": "inner",
                "relationship_ref": "rel:contract_customer",
                "reason": "关联客户",
            },
            {
                "left": "contract",
                "right": "org",
                "type": "left",
                "relationship_ref": "rel:contract_org",
                "reason": "关联组织",
            },
            {
                "left": "contract",
                "right": "person",
                "type": "left",
                "relationship_ref": "rel:contract_person",
                "reason": "关联人员",
            },
        ],
        "filters": [],
        "selects": [
            {
                "target": {
                    "asset_ref": "field:contract.name",
                    "alias": "contract",
                    "field": "name",
                },
                "display_name": "合同名称",
            }
        ],
        "metrics": [],
        "group_by": [],
        "ordering": [],
        "assumptions": [],
    }

    chunk = await execute_tool(
        dataset_id=10,
        confirmed_question="统计合同总金额",
        query_plan=invalid_plan,
        context_state={},
    )

    payload = json.loads(chunk.content[0].text)
    details = {item["path"]: item for item in payload["validation_error_details"]}

    assert "extra_forbidden:join_requirements.0.left" in payload["validation_error_summary"]
    assert "missing:join_requirements.0.left_alias" in payload["validation_error_summary"]
    assert details["join_requirements.0.left"]["expected"].startswith("删除 left，改用 left_alias")
    assert details["join_requirements.0.right"]["expected"].startswith(
        "删除 right，改用 right_alias"
    )
    assert details["join_requirements.0.type"]["expected"].startswith("删除 type，改用 join_type")
    assert details["join_requirements.0.left_alias"]["message"].endswith(
        "关联关系必须声明左右实体 alias 和关系引用。"
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"left": "contract"' not in serialized
    assert '"right": "customer"' not in serialized


@pytest.mark.asyncio
async def test_query_plan_contract_total_attempts_stop_retry_across_changed_error_signatures():
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    execute_tool = next(
        tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
    )
    first_invalid_plan = {"intent": "detail_query"}
    second_invalid_plan = {
        "intent": "detail_query",
        "question": "查询杨凯2025年日志",
        "result_shape": {"type": "table", "grain": "detail"},
        "data_graph": {
            "primary_entity": {
                "asset_ref": "table:pm_tenant.plan_task_daily_record",
                "alias": "main",
                "role": "fact",
            }
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
    from app.runtime.engine import tools as tools_module
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "bi-worker"
        system_prompt = "你是 Datalogue BI Worker，只处理 Datalogue Dataset Query 类问数任务。"

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
    from app.runtime.engine import tools as tools_module
    from app.domains.agent_team.progress_bridge import agent_progress_subscription
    from app.runtime.engine.tools import build_datalogue_extra_agent_tools

    class FakeAgentData:
        name = "bi-worker"
        system_prompt = "你是 Datalogue BI Worker，只处理 Datalogue Dataset Query 类问数任务。"

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


def test_plan_contract_error_expected_guides_join_condition_to_join_keys():
    """LLM 常见错误：塞 join_condition SQL 片段。hint 需引导改用 join_keys。"""
    from app.runtime.engine.tools import _plan_contract_error_expected

    expected = _plan_contract_error_expected(
        code="extra_forbidden",
        loc=("join_requirements", 0, "join_condition"),
    )
    assert "join_keys" in expected
    assert "SQL 片段" in expected
    assert "left_field" in expected and "right_field" in expected


@pytest.mark.asyncio
async def test_execute_query_plan_bundle_accepts_join_keys_field():
    """契约扩展后，join_requirements 允许携带 join_keys；不再报 extra_forbidden。"""
    from app.runtime.engine import tools as tools_module
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    async def fake_execute(*args, **kwargs):
        return {
            "datalogue_event_type": "dataset_query_result",
            "status": "completed",
            "artifact_ref": "artifact:test-1",
            "row_count": 1,
            "column_count": 1,
            "summary": "OK",
        }

    from app.domains.bi.worker.runtime import BIWorkerQueryRuntime

    # monkeypatch execute_query_plan：只验证契约 model_validate 通过、能进入执行分支。
    original = BIWorkerQueryRuntime.execute_query_plan
    BIWorkerQueryRuntime.execute_query_plan = fake_execute  # type: ignore[assignment]
    try:
        tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
        execute_tool = next(
            tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
        )
        plan_with_join_keys = {
            "intent": "detail_query",
            "question": "查询日志",
            "result_shape": {"type": "table", "grain": "detail", "limit": 100},
            "data_graph": {
                "primary_entity": {"asset_ref": "asset:log", "alias": "main", "role": "primary"},
                "supporting_entities": [
                    {"asset_ref": "asset:person", "alias": "person", "role": "supporting"},
                ],
            },
            "join_requirements": [
                {
                    "left_alias": "main",
                    "right_alias": "person",
                    "relationship_ref": "rel:log_person",
                    "join_type": "left",
                    "required": True,
                    "reason": "按人员姓名筛选",
                    "join_keys": [
                        {"left_field": "account", "right_field": "person_card"},
                    ],
                }
            ],
            "filters": [],
            "selects": [
                {
                    "target": {"asset_ref": "asset:log.id", "alias": "main", "field": "id"},
                    "display_name": "ID",
                    "requires_decoding": False,
                }
            ],
            "metrics": [],
            "group_by": [],
            "ordering": [],
            "assumptions": [],
        }
        result_chunk = await execute_tool(
            dataset_id=1,
            confirmed_question="查询日志",
            query_plan=plan_with_join_keys,
            context_state={},
        )
        # 契约通过 → 走到 fake_execute → payload.status=completed，不含 repair_request。
        payload_text = tools_module.json.dumps(
            [block.text for block in result_chunk.content], ensure_ascii=False
        )
        assert "bi_worker_repair_request" not in payload_text
        assert "completed" in payload_text
    finally:
        BIWorkerQueryRuntime.execute_query_plan = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_execute_query_plan_bundle_logs_runtime_exception(caplog):
    """运行时未预期异常要进入后端日志,并转成结构化失败 payload 给 Worker。"""
    import json
    import logging

    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    async def fake_execute(*args, **kwargs):
        raise TypeError("unsupported operand type(s) for |: 'list' and 'set'")

    from app.domains.bi.worker.runtime import BIWorkerQueryRuntime

    original = BIWorkerQueryRuntime.execute_query_plan
    BIWorkerQueryRuntime.execute_query_plan = fake_execute  # type: ignore[assignment]
    try:
        tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
        execute_tool = next(
            tool for tool in tools if tool.name == "datalogue_execute_query_plan_bundle"
        )
        with caplog.at_level(logging.ERROR, logger="app.runtime.engine.tools"):
            result_chunk = await execute_tool(
                dataset_id=1,
                confirmed_question="查询日志",
                query_plan={
                    "intent": "detail_query",
                    "question": "查询日志",
                    "result_shape": {"type": "table", "grain": "detail", "limit": 100},
                    "data_graph": {
                        "primary_entity": {
                            "asset_ref": "asset:log",
                            "alias": "main",
                            "role": "primary",
                        },
                        "supporting_entities": [],
                    },
                    "join_requirements": [],
                    "filters": [],
                    "selects": [
                        {
                            "target": {
                                "asset_ref": "asset:log.id",
                                "alias": "main",
                                "field": "id",
                            },
                            "display_name": "ID",
                            "requires_decoding": False,
                        }
                    ],
                    "metrics": [],
                    "group_by": [],
                    "ordering": [],
                    "assumptions": [],
                },
                context_state={"asset_refs": ["asset:log"], "field_refs": ["asset:log.id"]},
            )
        payload = json.loads(result_chunk.content[0].text)
        assert payload["status"] == "failed"
        assert payload["datalogue_event_type"] == "dataset_query_result"
        assert payload["failure_type"] == "FIELD_NOT_FOUND"
        assert "BI Worker query plan execution failed" in caplog.text
        assert "unsupported operand type" in caplog.text
    finally:
        BIWorkerQueryRuntime.execute_query_plan = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_describe_tables_tool_rejects_empty_table_names():
    """describe_tables 工具要求 table_names 为非空 list,否则拒绝并返回 code。"""
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    describe_tool = next(tool for tool in tools if tool.name == "datalogue_describe_tables")

    result_chunk = await describe_tool(dataset_id=1, table_names=[])
    payload = json.loads(result_chunk.content[0].text)
    assert payload["status"] == "failed"
    assert payload["code"] == "TABLE_NAMES_REQUIRED"

    # 非 list 类型也应被拒绝,防止 LLM 传入单字符串。
    result_chunk = await describe_tool(dataset_id=1, table_names="not_a_list")
    payload = json.loads(result_chunk.content[0].text)
    assert payload["code"] == "TABLE_NAMES_REQUIRED"


def test_progressive_bi_worker_tools_include_describe_tables():
    """describe_tables 工具应注册并紧跟 request_schema_slice 之后。"""
    from app.runtime.engine.tools import build_datalogue_progressive_bi_worker_tools

    tools = build_datalogue_progressive_bi_worker_tools(worker_context=None)
    names = [tool.name for tool in tools]

    assert "datalogue_describe_tables" in names
    idx_slice = names.index("datalogue_request_schema_slice")
    idx_describe = names.index("datalogue_describe_tables")
    assert idx_describe == idx_slice + 1


@pytest.mark.asyncio
async def test_progressive_readonly_tools_bypass_permission_engine():
    """所有 is_read_only=True 的 progressive 工具必须走 DatalogueBIWorkerReadOnlyTool 基类,
    使 check_permissions 返回 ALLOW 决策,避免 AgentScope DONT_ASK 引擎在
    SubAgentTemplate 场景下误拦截 (曾多次踩坑: search_assets / describe_tables 等)。
    """
    from agentscope.permission import PermissionBehavior, PermissionContext

    from app.runtime.engine.tools import (
        DatalogueBIWorkerReadOnlyTool,
        build_datalogue_progressive_bi_worker_tools,
        build_datalogue_search_assets_tool,
    )

    tools = list(build_datalogue_progressive_bi_worker_tools(worker_context=None))
    tools.append(build_datalogue_search_assets_tool(worker_context=None))

    readonly_names = set()
    for tool in tools:
        if getattr(tool, "is_read_only", False):
            # 只读工具必须继承自绕过基类
            assert isinstance(
                tool, DatalogueBIWorkerReadOnlyTool
            ), f"read-only tool {tool.name} 必须继承 DatalogueBIWorkerReadOnlyTool"
            readonly_names.add(tool.name)
            # 权限检查必须直接返回 ALLOW,不能落到默认 DENY/ASK
            decision = await tool.check_permissions({}, PermissionContext())
            assert decision.behavior is PermissionBehavior.ALLOW
            assert decision.decision_reason == "ALLOWED_BY_TOOL"

    # 核心只读工具都要被覆盖到 (execute_query_plan_bundle 不在此列表, 它是 read_only=False)
    assert {
        "datalogue_search_assets",
        "datalogue_prepare_query_context",
        "datalogue_request_schema_slice",
        "datalogue_describe_tables",
        "datalogue_repair_query_plan",
    }.issubset(readonly_names)
