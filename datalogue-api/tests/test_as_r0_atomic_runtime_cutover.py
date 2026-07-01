# ============================================================
# File Name   : test_as_r0_atomic_runtime_cutover.py
# Description:
#   AS-R0 PR1.3-b BI atomic runtime 直接接管测试。
#
# Responsibilities:
#   - 验证单数据集 BI 查询默认绕过 legacy LangGraph 执行核心。
#   - 验证 atomic runtime 的结果仍复用现有 /chat/stream final、artifact、trace 收口契约。
#   - 验证用户可见 SSE 不暴露 SQL、schema、raw rows 或 query_plan 主体。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from app import models
from app.schemas.chat import ChatRequest
from app.services.multiturn_context import MergeDecision
from app.services.subagent_planning import CandidateAsset, QueryPlan


def _repairable_field_dsl() -> QueryPlan:
    """构造一个旧字段 DSL，用于验证 direct 入口能触发 repair_dsl 后重跑。"""

    return QueryPlan(
        query_type="detail_query",
        execution_strategy="query_graph",
        confidence=0.91,
        selected_assets=[
            CandidateAsset(
                asset_type="field",
                asset_id="project_manager.ZTGZL",
                name="项目总体工作量",
                display_name="项目总体工作量",
                source="schema",
                confidence=0.9,
                metadata={"table_name": "project_manager", "column_name": "ZTGZL"},
                usage="selected",
            )
        ],
        debug={"selected_main_table": "project_manager"},
    )


def _bind_repairable_project_manager_table(db_session, sample_dataset) -> None:
    """为 direct endpoint 准备 repair_dsl 可用的同表同业务标签替代字段。"""

    table = models.SourceTable(
        datasource_id=sample_dataset.datasource_id,
        schema_name="",
        table_name="project_manager",
        table_comment="项目管理表",
    )
    db_session.add(table)
    db_session.flush()
    db_session.add(
        models.SourceColumn(
            table_id=table.id,
            column_name="ZTGZL_NEW",
            data_type="numeric",
            column_comment="项目总体工作量",
            ordinal_position=1,
        )
    )
    db_session.add(
        models.DatasetSourceTable(
            dataset_id=sample_dataset.id,
            source_table_id=table.id,
        )
    )
    db_session.commit()


def test_dataset_runtime_direct_entry_bypasses_lead_agent_and_legacy_graph(
    db_session,
    sample_dataset,
    monkeypatch,
):
    """DatasetAgent Runtime 直通测试入口不能触发 LeadAgent 或 legacy graph。"""

    from app.api import chat as chat_api

    def fake_agentscope_direct(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["dataset_id"] == sample_dataset.id
        assert kwargs["payload"].question == "查询 GMV"
        return {
            "status": "completed",
            "artifact_ref": "artifact:direct-runtime",
            "artifact_summary": {"artifact_ref": "artifact:direct-runtime"},
            "row_count": 1,
            "column_count": 1,
            "tool_results": [
                {"name": "get_dataset_status", "status": "active"},
                {"name": "list_candidate_assets", "status": "ready"},
                {"name": "compile_dsl_to_sql", "status": "compiled"},
                {"name": "execute_compiled_query", "status": "completed"},
                {"name": "create_query_artifact", "status": "ready"},
                {"name": "get_artifact_summary", "status": "ready"},
            ],
        }

    monkeypatch.setattr(
        chat_api,
        "build_lead_agent_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("LeadAgent must not run in direct DatasetAgent Runtime test entry")
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "route_query_intent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("route_query_intent must not run in direct DatasetAgent Runtime test entry")
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "build_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy graph must not run in direct DatasetAgent Runtime test entry")
        ),
    )
    monkeypatch.setattr(chat_api, "_run_agentscope_dataset_runtime_direct", fake_agentscope_direct)

    result = chat_api.dataset_runtime_direct(
        ChatRequest(question="查询 GMV", dataset_id=sample_dataset.id),
        db_session,
    )

    assert result["status"] == "completed", result
    assert result["artifact_ref"] == "artifact:direct-runtime"
    assert result["row_count"] == 1
    assert result["column_count"] == 1
    assert [item["name"] for item in result["tool_calls"]] == [
        "get_dataset_status",
        "list_candidate_assets",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "create_query_artifact",
        "get_artifact_summary",
    ]


def test_dataset_runtime_direct_entry_can_drive_agentscope_repair_dsl(
    db_session,
    sample_dataset,
    monkeypatch,
):
    """HTTP direct 测试入口应可直接验证 AgentScope bridge 的 repair_dsl 链路。"""

    from app.api import chat as chat_api

    _bind_repairable_project_manager_table(db_session, sample_dataset)
    executed_sql: list[str] = []

    def repairable_executor(*, db, dataset, question):
        del db, dataset, question

        def _execute(sql: str) -> dict[str, Any]:
            executed_sql.append(sql)
            if "ZTGZL" in sql and "ZTGZL_NEW" not in sql:
                raise RuntimeError(
                    '(pymysql.err.OperationalError) (1054, "Unknown column '
                    "'project_manager.ZTGZL' in 'field list'\")"
                )
            return {"columns": ["项目总体工作量"], "rows": [{"项目总体工作量": 1}], "row_count": 1}

        return _execute

    monkeypatch.setattr(
        chat_api,
        "_build_atomic_dsl_generator",
        lambda **_kwargs: (lambda **_inner_kwargs: _repairable_field_dsl()),
    )
    monkeypatch.setattr(chat_api, "_build_atomic_query_executor", repairable_executor)

    result = chat_api.dataset_runtime_direct(
        ChatRequest(question="查询项目总体工作量", dataset_id=sample_dataset.id),
        db_session,
    )

    assert result["status"] == "completed", result
    assert result["execution_path"] == "agentscope_dataset_runtime_direct"
    assert [item["name"] for item in result["tool_results"]] == [
        "get_dataset_status",
        "list_candidate_assets",
        "compile_dsl_to_sql",
        "execute_compiled_query",
        "repair_dsl",
        "execute_compiled_query",
        "create_query_artifact",
        "get_artifact_summary",
    ]
    assert any(item["name"] == "repair_dsl" and item["status"] == "repaired" for item in result["tool_results"])
    assert result["row_count"] == 1
    assert any("ZTGZL_NEW" in sql for sql in executed_sql)


@pytest.mark.asyncio
async def test_chat_stream_atomic_runtime_bypasses_legacy_graph_core_without_flag(
    db_session,
    sample_dataset,
    monkeypatch,
    caplog,
):
    """PR1.3-b: BI 查询执行核心应默认走 AgentScope-owned atomic runtime。"""

    from app.api import chat as chat_api

    class Settings:
        MULTITURN_ENABLED = False
        MULTITURN_REFINEMENT_FAST_PATH_ENABLED = False
        MULTITURN_RESULT_LOCAL_FILTER_ENABLED = False
        MULTITURN_SQL_AST_PATCH_ENABLED = False
        MULTITURN_ARTIFACT_CACHE_TTL_SECONDS = 1800
        LEAD_AGENT_ENABLE_DATASET_FANOUT = False
        AS_R0_AGENTIC_RUNTIME_SHADOW_ENABLED = False

    class FakeAtomicRuntime:
        def __init__(self, *, toolkit, dsl_generator):
            self.toolkit = toolkit
            self.dsl_generator = dsl_generator

        def run_query(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["dataset_id"] == sample_dataset.id
            assert kwargs["question"] == "查询 GMV"
            return {
                "status": "completed",
                "artifact_ref": "artifact:atomic-result",
                "artifact_summary": {
                    "artifact_ref": "artifact:atomic-result",
                    "kind": "sql_result",
                    "size_bytes": 128,
                },
                "row_count": 2,
                "column_count": 1,
                "tool_calls": [
                    {"name": "get_dataset_status", "status": "active"},
                    {"name": "list_candidate_assets", "status": "ready"},
                    {"name": "generate_dsl", "status": "generated"},
                    {"name": "compile_dsl_to_sql", "status": "compiled"},
                    {"name": "execute_compiled_query", "status": "completed"},
                    {"name": "get_artifact_summary", "status": "ready"},
                ],
            }

    def fake_build_workflow(_db):
        raise AssertionError("legacy LangGraph core must not run for BI query main chain")

    def fail_lead_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("LeadAgent control plane must not run for direct DatasetAgent Runtime main chain")

    def fail_route_query_intent(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("route_query_intent must not run for direct DatasetAgent Runtime main chain")

    monkeypatch.setattr(chat_api, "get_settings", lambda: Settings())
    monkeypatch.setattr(chat_api, "build_workflow", fake_build_workflow)
    monkeypatch.setattr(chat_api, "build_lead_agent_context", fail_lead_context)
    monkeypatch.setattr(
        chat_api,
        "merge_multiturn_decision_for_chat",
        lambda **_kwargs: MergeDecision(turn_type="new_query", multiturn_context={}, merge_debug={}),
    )
    monkeypatch.setattr(
        chat_api,
        "resolve_term_clarification",
        lambda *_args, **_kwargs: {"status": "none"},
    )
    monkeypatch.setattr(
        chat_api,
        "classify_turn_event",
        lambda *_args, **_kwargs: {"event_type": "query", "reason": "test_direct_runtime"},
    )
    monkeypatch.setattr(chat_api, "route_query_intent", fail_route_query_intent)
    monkeypatch.setattr(chat_api, "DatasetAgentToolCallRuntime", FakeAtomicRuntime, raising=False)

    with caplog.at_level(logging.INFO, logger="app.api.chat"):
        parsed_events = [
            json.loads(event["data"])
            async for event in chat_api._stream_chat_singleturn(
                ChatRequest(question="查询 GMV", dataset_id=sample_dataset.id),
                db_session,
            )
        ]

    final_events = [event for event in parsed_events if event.get("type") == "final"]
    assert final_events
    final_payload = final_events[-1]
    assert final_payload["answer"] == "Atomic runtime 查询完成，共返回 2 行、1 列。"
    assert final_payload["entry_route"] == "query_graph"
    assert final_payload["result_ref"] == "artifact:atomic-result"
    assert "trace_id" not in final_payload or final_payload["trace_id"] in (None, "")
    assert any(
        (event.get("event_envelope") or {}).get("event_type") == "dataset.query.completed"
        for event in parsed_events
    )

    visible_dump = repr(
        [
            (event.get("event_envelope") or {}).get("payload")
            for event in parsed_events
            if (event.get("event_envelope") or {}).get("visibility") == "user_visible"
        ]
    )
    for forbidden in ("SELECT ", "sql_preview", "schema", "raw_rows", "query_plan", "RepairPatch"):
        assert forbidden.lower() not in visible_dump.lower()

    backend_logs = "\n".join(record.getMessage() for record in caplog.records)
    for removed_log in (
        "[chat.stream.dataset_agent_runtime_start]",
        "[chat.stream.dataset_agent_runtime_completed]",
    ):
        assert removed_log not in backend_logs
    for legacy_term in ("legacy LangGraph", "build_workflow", "DatasetSubAgent"):
        assert legacy_term.lower() not in backend_logs.lower()
