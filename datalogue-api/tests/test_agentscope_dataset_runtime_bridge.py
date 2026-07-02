# ============================================================
# File Name   : test_agentscope_dataset_runtime_bridge.py
# Description:
#   AS-R0 DatasetAgent Runtime 的 AgentScope 2.0 SDK bridge 测试。
#
# Responsibilities:
#   - 验证 BI 原子工具以 AgentScope ToolBase external tool 形态注册。
#   - 验证 PermissionContext/Decision/Behavior 拦截越权、乱序和敏感入参。
#   - 验证 RequireExternalExecutionEvent 到 ToolResultBlock 的安全回填链路。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from agentscope.event import ExternalExecutionResultEvent, RequireExternalExecutionEvent
from agentscope.message import TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState
from agentscope.permission import PermissionBehavior, PermissionContext
from agentscope.tool import ToolBase, ToolChunk, ToolMiddlewareBase, Toolkit

from app.services.agentscope_middlewares import DatasetRuntimeToolLoggingMiddleware
from app.services.agentscope_dataset_runtime import (
    AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE,
    AgentScopeDatasetRuntimeBridge,
    build_dataset_agentscope_tools,
)
from app.services.bi_tools import DatalogueBIAtomicToolkit, build_bi_atomic_toolkit
from app.services.subagent_planning import CandidateAsset, QueryPlan

def _field_asset(name: str, table_name: str, column_name: str) -> CandidateAsset:
    return CandidateAsset(
        asset_type="field",
        asset_id=f"{table_name}.{column_name}",
        name=name,
        display_name=name,
        source="schema",
        confidence=0.9,
        metadata={"table_name": table_name, "column_name": column_name},
        usage="selected",
    )


def _valid_dsl() -> QueryPlan:
    return QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.91,
        selected_assets=[_field_asset("账号", "user_logs", "account")],
        debug={"selected_main_table": "user_logs"},
    )


def _repairable_dsl() -> QueryPlan:
    return QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.91,
        selected_assets=[
            _field_asset("项目总体工作量", "project_manager", "ZTGZL"),
        ],
        debug={"selected_main_table": "project_manager"},
    )


def test_bi_atomic_tools_are_toolbase_classes_exposed_by_toolkit(db_session):
    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda _sql: {"rows": []})

    assert isinstance(toolkit, DatalogueBIAtomicToolkit)
    assert isinstance(toolkit.agentscope_toolkit, Toolkit)
    assert [tool.name for tool in toolkit.tools] == list(AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE)
    assert all(isinstance(tool, ToolBase) for tool in toolkit.tools)
    assert all(tool.is_external_tool is True for tool in toolkit.tools)
    assert toolkit.get_tool("compile_dsl_to_sql").name == "compile_dsl_to_sql"


@pytest.mark.asyncio
async def test_dataset_runtime_tool_logging_middleware_wraps_toolbase_calls(caplog):
    class DummyDatasetTool(ToolBase):
        name = "execute_compiled_query"
        description = "Dummy DatasetAgent tool."
        input_schema = {"type": "object", "properties": {}}
        is_concurrency_safe = False
        is_read_only = False
        is_external_tool = False

        def __init__(self) -> None:
            super().__init__(
                middlewares=[
                    DatasetRuntimeToolLoggingMiddleware(
                        dataset_id=10,
                        conversation_id=7,
                        trace_id="trace-tool-middleware",
                    )
                ]
            )

        async def call(self, **_kwargs: Any) -> ToolChunk:
            return ToolChunk(
                content=[
                    TextBlock(
                        text='{"status":"completed","raw_rows":[{"account":"alice"}],"compiled_query_ref":"compiled_query:ok"}'
                    )
                ],
                state=ToolResultState.SUCCESS,
            )

        async def check_permissions(
            self,
            tool_input: dict[str, Any],
            context: PermissionContext,
        ):
            del tool_input, context
            raise NotImplementedError

    tool = DummyDatasetTool()
    middleware = tool._middlewares[0]
    assert isinstance(middleware, ToolMiddlewareBase)

    with caplog.at_level(logging.INFO, logger="app.services.agentscope_middlewares.dataset_tool_logging"):
        chunks = [
            chunk
            async for chunk in await tool(
                compiled_query_ref="compiled_query:ok",
                sql="SELECT * FROM user_logs",
            )
        ]

    assert len(chunks) == 1
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "[agentscope.dataset_tool.call]" in logs
    assert "[agentscope.dataset_tool.result]" in logs
    assert '"tool": "execute_compiled_query"' in logs
    assert '"has_compiled_query_ref": true' in logs
    for forbidden in ("SELECT", "user_logs", "sql", "raw_rows", "account", "alice", "schema", "query_plan"):
        assert forbidden.lower() not in logs.lower()


@pytest.mark.asyncio
async def test_agentscope_dataset_tools_are_external_toolbase_with_fail_closed_permission(
    db_session,
    sample_dataset,
):
    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda _sql: {"rows": []})
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(dataset_id=sample_dataset.id, question="查询账号明细")

    tools = build_dataset_agentscope_tools(session=session, agent_name="bi_lead_agent")
    assert [tool.name for tool in tools] == list(AGENTSCOPE_DATASET_EXTERNAL_TOOL_SEQUENCE)
    assert all(isinstance(tool, ToolBase) for tool in tools)
    assert all(tool.is_external_tool is True for tool in tools)
    assert all(
        any(isinstance(middleware, DatasetRuntimeToolLoggingMiddleware) for middleware in tool._middlewares)
        for tool in tools
    )

    execute_tool = {tool.name: tool for tool in tools}["execute_compiled_query"]
    denied_before_compile = await execute_tool.check_permissions(
        {"compiled_query_ref": "compiled_query:fake"},
        PermissionContext(),
    )
    assert denied_before_compile.behavior is PermissionBehavior.DENY
    assert denied_before_compile.decision_reason == "COMPILE_REQUIRED"

    status_tool_for_report_agent = build_dataset_agentscope_tools(
        session=session,
        agent_name="report_agent",
    )[0]
    non_bi_denied = await status_tool_for_report_agent.check_permissions({}, PermissionContext())
    assert non_bi_denied.behavior is PermissionBehavior.DENY
    assert non_bi_denied.decision_reason == "AGENT_NOT_ALLOWED"

    sensitive_denied = await tools[0].check_permissions(
        {"sql": "SELECT * FROM user_logs"},
        PermissionContext(),
    )
    assert sensitive_denied.behavior is PermissionBehavior.DENY
    assert sensitive_denied.decision_reason == "SENSITIVE_TOOL_ARGUMENT"


@pytest.mark.asyncio
async def test_agentscope_external_execution_event_returns_safe_tool_result_blocks(
    db_session,
    sample_dataset,
):
    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda _sql: {"rows": []})
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        agent_name="bi_lead_agent",
    )
    event = RequireExternalExecutionEvent(
        reply_id="reply-1",
        tool_calls=[
            ToolCallBlock(id="tc-1", name="get_dataset_status", input=json.dumps({})),
        ],
    )

    result_event = await bridge.handle_external_execution_event(session, event)

    assert isinstance(result_event, ExternalExecutionResultEvent)
    assert result_event.reply_id == "reply-1"
    assert len(result_event.execution_results) == 1
    block = result_event.execution_results[0]
    assert isinstance(block, ToolResultBlock)
    assert block.id == "tc-1"
    assert block.name == "get_dataset_status"
    assert block.state == ToolResultState.SUCCESS
    assert isinstance(block.output[0], TextBlock)
    payload = json.loads(block.output[0].text)
    assert payload == {"status": "active", "dataset_id": sample_dataset.id}

    dumped = block.model_dump_json()
    for forbidden in ("SELECT", "user_logs", "account", "raw_rows", "query_plan", "schema"):
        assert forbidden.lower() not in dumped.lower()


@pytest.mark.asyncio
async def test_agentscope_compile_and_execute_flow_only_exposes_compiled_query_ref(
    db_session,
    sample_dataset,
):
    executed_sql: list[str] = []

    def fake_executor(sql: str) -> dict[str, Any]:
        executed_sql.append(sql)
        return {"columns": ["账号"], "rows": [{"账号": "alice"}], "row_count": 1}

    toolkit = build_bi_atomic_toolkit(db_session, query_executor=fake_executor)
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        agent_name="bi_lead_agent",
        sql_generation_context={"table_schemas": [{"table_name": "user_logs"}]},
        allowed_tables=["user_logs"],
    )

    for tool_name, tool_input in (
        ("get_dataset_status", {}),
        ("list_candidate_assets", {}),
        ("compile_dsl_to_sql", {"dsl": _valid_dsl().to_dict()}),
    ):
        event = RequireExternalExecutionEvent(
            reply_id=f"reply-{tool_name}",
            tool_calls=[
                ToolCallBlock(id=f"tc-{tool_name}", name=tool_name, input=json.dumps(tool_input)),
            ],
        )
        result_event = await bridge.handle_external_execution_event(session, event)

    compile_block = result_event.execution_results[0]
    compile_payload = json.loads(compile_block.output[0].text)
    assert compile_block.state == ToolResultState.SUCCESS
    assert compile_payload["status"] == "compiled"
    assert compile_payload["agent_context"] == {
        "compiled_query_ref": compile_payload["compiled_query_ref"],
    }
    assert "sql" not in json.dumps(compile_payload).lower()

    forged = RequireExternalExecutionEvent(
        reply_id="reply-forged",
        tool_calls=[
            ToolCallBlock(
                id="tc-forged",
                name="execute_compiled_query",
                input=json.dumps({"compiled_query_ref": "compiled_query:forged"}),
            ),
        ],
    )
    forged_result = await bridge.handle_external_execution_event(session, forged)
    forged_payload = json.loads(forged_result.execution_results[0].output[0].text)
    assert forged_result.execution_results[0].state == ToolResultState.DENIED
    assert forged_payload["code"] == "COMPILED_QUERY_REF_MISMATCH"
    assert executed_sql == []

    execute = RequireExternalExecutionEvent(
        reply_id="reply-execute",
        tool_calls=[
            ToolCallBlock(
                id="tc-execute",
                name="execute_compiled_query",
                input=json.dumps({"compiled_query_ref": compile_payload["compiled_query_ref"]}),
            ),
        ],
    )
    execute_result = await bridge.handle_external_execution_event(session, execute)
    execute_payload = json.loads(execute_result.execution_results[0].output[0].text)
    assert execute_result.execution_results[0].state == ToolResultState.SUCCESS
    assert execute_payload["status"] == "completed"
    assert execute_payload["artifact_ref"].startswith("artifact:")
    assert execute_payload["row_count"] == 1
    assert executed_sql and "SELECT" in executed_sql[0]

    dumped = "\n".join(
        block.model_dump_json()
        for event in (result_event, forged_result, execute_result)
        for block in event.execution_results
    )
    for forbidden in ("SELECT", "user_logs", "account", "alice", "raw_rows", "query_plan", "schema"):
        assert forbidden.lower() not in dumped.lower()


@pytest.mark.asyncio
async def test_agentscope_execute_field_missing_returns_blocked_repair_signal(
    db_session,
    sample_dataset,
):
    executed_sql: list[str] = []

    def repairable_executor(sql: str) -> dict[str, Any]:
        executed_sql.append(sql)
        if "`ZTGZL`" in sql:
            raise RuntimeError(
                '(pymysql.err.OperationalError) (1054, "Unknown column '
                "'project_manager.ZTGZL' in 'field list'\")"
            )
        return {"columns": ["项目总体工作量"], "rows": [{"项目总体工作量": 1}], "row_count": 1}

    toolkit = build_bi_atomic_toolkit(db_session, query_executor=repairable_executor)
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(
        dataset_id=sample_dataset.id,
        question="查询项目总体工作量",
        sql_generation_context={
            "table_schemas": [
                {
                    "table_name": "project_manager",
                    "fields": [
                        {
                            "name": "ZTGZL_NEW",
                            "column_name": "ZTGZL_NEW",
                            "display_name": "项目总体工作量",
                        },
                    ],
                }
            ]
        },
        dialect="mysql",
        allowed_tables=["project_manager"],
    )

    for tool_name, tool_input in (
        ("get_dataset_status", {}),
        ("list_candidate_assets", {}),
        (
            "compile_dsl_to_sql",
            {"dsl": _repairable_dsl().to_dict()},
        ),
    ):
        await bridge.handle_external_execution_event(
            session,
            RequireExternalExecutionEvent(
                reply_id=f"reply-{tool_name}",
                tool_calls=[
                    ToolCallBlock(id=f"tc-{tool_name}", name=tool_name, input=json.dumps(tool_input)),
                ],
            ),
        )

    execute_result = await bridge.handle_external_execution_event(
        session,
        RequireExternalExecutionEvent(
            reply_id="reply-execute",
            tool_calls=[
                ToolCallBlock(
                    id="tc-execute",
                    name="execute_compiled_query",
                    input=json.dumps({"compiled_query_ref": session.compiled_query_ref}),
                ),
            ],
        ),
    )

    execute_block = execute_result.execution_results[0]
    execute_payload = json.loads(execute_block.output[0].text)
    assert execute_block.state == ToolResultState.DENIED
    assert execute_payload == {
        "status": "blocked",
        "code": "FIELD_NOT_FOUND",
    }
    assert session.last_error == execute_payload
    assert "ZTGZL" not in execute_block.model_dump_json()

    repair_result = await bridge.handle_external_execution_event(
        session,
        RequireExternalExecutionEvent(
            reply_id="reply-repair",
            tool_calls=[
                ToolCallBlock(
                    id="tc-repair",
                    name="repair_dsl",
                    input=json.dumps({"compiled_query_ref": session.compiled_query_ref}),
                ),
            ],
        ),
    )
    repair_block = repair_result.execution_results[0]
    repair_payload = json.loads(repair_block.output[0].text)
    assert repair_block.state == ToolResultState.SUCCESS
    assert repair_payload["status"] == "repaired"
    assert repair_payload["compiled_query_ref"].startswith("compiled_query:")
    assert repair_payload["agent_context"] == {
        "compiled_query_ref": repair_payload["compiled_query_ref"],
    }
    assert "ZTGZL" not in repair_block.model_dump_json()

    rerun_result = await bridge.handle_external_execution_event(
        session,
        RequireExternalExecutionEvent(
            reply_id="reply-rerun",
            tool_calls=[
                ToolCallBlock(
                    id="tc-rerun",
                    name="execute_compiled_query",
                    input=json.dumps({"compiled_query_ref": session.compiled_query_ref}),
                ),
            ],
        ),
    )
    rerun_payload = json.loads(rerun_result.execution_results[0].output[0].text)
    assert rerun_result.execution_results[0].state == ToolResultState.SUCCESS
    assert rerun_payload["status"] == "completed"
    assert rerun_payload["row_count"] == 1
    assert any("ZTGZL_NEW" in sql for sql in executed_sql)


@pytest.mark.asyncio
async def test_agentscope_reply_stream_loop_resumes_agent_with_external_execution_results(
    db_session,
    sample_dataset,
):
    class FakeDatasetAgent:
        def __init__(self) -> None:
            self.received_external_events: list[ExternalExecutionResultEvent] = []

        async def reply_stream(self, _msg: Any):
            yield RequireExternalExecutionEvent(
                reply_id="reply-loop",
                tool_calls=[
                    ToolCallBlock(id="tc-loop", name="get_dataset_status", input=json.dumps({})),
                ],
            )

        async def reply(self, event: ExternalExecutionResultEvent) -> dict[str, str]:
            self.received_external_events.append(event)
            return {"answer": "done"}

    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda _sql: {"rows": []})
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        agent_name="bi_lead_agent",
    )
    agent = FakeDatasetAgent()

    results = await bridge.run_reply_stream(agent, msg={"role": "user", "content": "查询账号明细"}, session=session)

    assert len(agent.received_external_events) == 1
    assert isinstance(agent.received_external_events[0], ExternalExecutionResultEvent)
    block = agent.received_external_events[0].execution_results[0]
    assert block.name == "get_dataset_status"
    assert block.state == ToolResultState.SUCCESS
    assert results[-1] == {"answer": "done"}


@pytest.mark.asyncio
async def test_agentscope_reply_stream_loop_drives_nested_external_execution_events(
    db_session,
    sample_dataset,
):
    class FakeDatasetAgent:
        def __init__(self) -> None:
            self.received_external_events: list[ExternalExecutionResultEvent] = []

        async def reply_stream(self, _msg: Any):
            yield RequireExternalExecutionEvent(
                reply_id="reply-first",
                tool_calls=[
                    ToolCallBlock(id="tc-status", name="get_dataset_status", input=json.dumps({})),
                ],
            )

        async def reply(self, event: ExternalExecutionResultEvent):
            self.received_external_events.append(event)
            if len(self.received_external_events) == 1:
                async def next_tool_stream():
                    yield RequireExternalExecutionEvent(
                        reply_id="reply-second",
                        tool_calls=[
                            ToolCallBlock(id="tc-assets", name="list_candidate_assets", input=json.dumps({})),
                        ],
                    )

                return next_tool_stream()
            return {"answer": "done"}

    toolkit = build_bi_atomic_toolkit(db_session, query_executor=lambda _sql: {"rows": []})
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    session = bridge.start_session(
        dataset_id=sample_dataset.id,
        question="查询账号明细",
        agent_name="bi_lead_agent",
    )
    agent = FakeDatasetAgent()

    results = await bridge.run_reply_stream(agent, msg={"role": "user", "content": "查询账号明细"}, session=session)

    assert len(agent.received_external_events) == 2
    assert [event.execution_results[0].name for event in agent.received_external_events] == [
        "get_dataset_status",
        "list_candidate_assets",
    ]
    assert [item["name"] for item in session.tool_results] == [
        "get_dataset_status",
        "list_candidate_assets",
    ]
    assert results[-1] == {"answer": "done"}
