# ============================================================
# File Name   : test_bi_main_chain_acceptance.py
# Description:
#   P0 主链路五件套验收用例。
#
# Responsibilities:
#   - 验证 SSE、后端 checkpoint、trace index、artifact 和多轮状态可互相核对。
#   - 覆盖成功问数、低置信确认、拒答、受控失败 retry 和历史回放边界。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import asyncio
import json

from app import models, schemas
from app.core.config import Settings
from app.services.conversation_store import ConversationStore
from app.services.dataset_manifest import publish_manifest

from tests.test_chat import _manifest_manual_fields


def _collect_stream_events(payload, db_session):
    from app.api.chat import _stream_chat

    async def _collect():
        return [
            json.loads(event["data"])
            async for event in _stream_chat(schemas.ChatRequest(**payload), db_session)
        ]

    return asyncio.run(_collect())


def _lead_context(dataset, *, decision="selected", should_continue=True, candidates=None):
    return {
        "tool_policy": {},
        "selected_skills": [],
        "planned_tool_calls": [{"tool": "manifest_route"}],
        "executed_tool_calls": [{"tool": "manifest_route"}],
        "system_inferred_tool_calls": [],
        "policy_violations": [],
        "original_question": "最近30日GMV趋势如何",
        "resolved_question": "最近30日GMV趋势如何",
        "multiturn_context": {},
        "multiturn_classification": {"intent": "new_query"},
        "time_context": {"detected_time_range": {"label": "最近30日"}},
        "thread_context": {"active_dataset_id": dataset.id},
        "route_decision": {
            "decision": decision,
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "manifest_version": "manifest-acceptance",
            "bound_schema_version": "schema-acceptance",
            "score": 0.91 if decision == "selected" else 0.48,
            "candidates": candidates or [],
            "reason": f"acceptance_{decision}",
        },
        "schema_status": {"status": "ok", "stale": False, "dataset_id": dataset.id},
        "clarification": None,
        "dispatch": {"dataset_id": dataset.id},
        "audit_trace": {"dispatched": should_continue},
        "should_continue": should_continue,
        "effective_dataset_id": dataset.id if should_continue else None,
    }


class _SuccessSubAgent:
    def __init__(self, db, dataset_id):
        self.db = db
        self.dataset_id = dataset_id

    async def run(self, request, _trace_context, *, graph, initial_state=None, graph_kwargs=None):
        from app.services.subagent_planning import SubAgentEvent

        candidate_assets = {
            "summary": {"metrics": 1, "dimensions": 1, "tables": 1},
            "assets": [
                {
                    "asset_type": "metric",
                    "asset_id": "gmv",
                    "name": "gmv",
                    "display_name": "GMV",
                    "confidence": 0.96,
                }
            ],
        }
        query_plan = {
            "query_type": "metric_query",
            "execution_strategy": "query_graph",
            "confidence": 0.94,
            "planner_source": "deterministic",
            "explanation": {"summary": "按最近30日聚合 GMV。"},
            "selected_assets": [
                {
                    "asset_type": "metric",
                    "name": "gmv",
                    "metadata": {"table_name": "orders", "column_name": "amount"},
                }
            ],
            "debug": {"selected_main_table": "orders"},
        }
        yield SubAgentEvent(
            event_type="candidate_assets",
            payload={"node": "candidate_assets", "candidate_assets": candidate_assets},
        )
        yield SubAgentEvent(
            event_type="query_plan",
            payload={"node": "query_plan", "query_plan": query_plan},
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_start",
                    "metadata": {"langgraph_node": "sql_execute"},
                    "data": {},
                }
            },
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "sql_execute"},
                    "data": {
                        "output": {
                            "answer": "最近30日 GMV 为 100。",
                            "entry_intent": "metric_query",
                            "entry_route": "query_graph",
                            "entry_reason": "acceptance_success",
                            "query_plan": query_plan,
                            "candidate_assets": candidate_assets,
                            "sql": "SELECT 100 AS gmv",
                            "sql_list": ["SELECT 100 AS gmv"],
                            "sql_result": {
                                "columns": ["gmv"],
                                "rows": [{"gmv": 100}],
                                "row_count": 1,
                            },
                            "dsl": {
                                "metrics": [{"name": "gmv", "expr": "SUM(o.amount)"}],
                                "fields": [
                                    {
                                        "table_name": "orders",
                                        "column_name": "amount",
                                        "name": "amount",
                                    }
                                ],
                            },
                            "generation_mode": "semantic",
                            "out_capsule": {
                                "capsule_version": "subagent.v1",
                                "dataset_id": request.dataset_id,
                                "schema_version": "schema-acceptance",
                                "query_context": {"metrics": ["gmv"]},
                            },
                        }
                    },
                }
            },
        )


class _RetryFailureSubAgent:
    def __init__(self, db, dataset_id):
        self.db = db
        self.dataset_id = dataset_id

    async def run(self, request, _trace_context, *, graph, initial_state=None, graph_kwargs=None):
        from app.services.subagent_planning import SubAgentEvent

        diagnosis = {
            "code": "COLUMN_NOT_FOUND",
            "severity": "retryable",
            "retryable": True,
            "title": "字段不存在",
            "suggested_action": "重新选择字段",
        }
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_start",
                    "metadata": {"langgraph_node": "sql_audit"},
                    "data": {},
                }
            },
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "sql_audit"},
                    "data": {
                        "output": {
                            "entry_route": "query_graph",
                            "query_plan": {
                                "query_type": "metric_query",
                                "execution_strategy": "query_graph",
                                "planner_source": "deterministic",
                            },
                            "error": "no such column: o.amount2",
                            "sql": "SELECT SUM(o.amount2) FROM orders o",
                            "sql_list": ["SELECT SUM(o.amount2) FROM orders o"],
                            "sql_diagnosis": diagnosis,
                            "sql_audit_result": diagnosis,
                            "sql_retry_trace": [{"attempt": 1, "reason": "column_missing"}],
                            "should_retry": True,
                            "retry_count": 1,
                        }
                    },
                }
            },
        )


class _RepairPlanSuccessSubAgent:
    def __init__(self, db, dataset_id):
        self.db = db
        self.dataset_id = dataset_id

    async def run(self, request, _trace_context, *, graph, initial_state=None, graph_kwargs=None):
        from app.services.subagent_planning import SubAgentEvent

        query_plan = {
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "planner_source": "deterministic",
        }
        diagnosis = {
            "code": "FIELD_NOT_FOUND",
            "severity": "retryable",
            "retryable": True,
            "title": "字段不存在",
            "suggested_action": "使用工作日期口径重新执行",
        }
        repair_plan = {
            "schema_version": "repair_plan.v1",
            "dataset_id": request.dataset_id,
            "failure_class": "FIELD_NOT_FOUND",
            "status": "plan_created",
            "business_summary": "字段口径不匹配，已按工作日志日期口径生成自动修复方案。",
            "actions": [
                {
                    "action_type": "replace_field",
                    "business_summary": "将不存在的日期口径替换为已发布的工作日期口径。",
                    "target": {"dataset_id": request.dataset_id, "table": "work_log", "field": "bad_col"},
                    "replacement": {"dataset_id": request.dataset_id, "table": "work_log", "field": "work_date"},
                    "confidence": 0.94,
                }
            ],
            "requires_user_confirmation": False,
            "confidence": 0.94,
            "attempts": 1,
        }
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_start",
                    "metadata": {"langgraph_node": "sql_audit"},
                    "data": {},
                }
            },
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "sql_audit"},
                    "data": {
                        "output": {
                            "entry_route": "query_graph",
                            "query_plan": query_plan,
                            "error": "no such column: work_log.bad_col",
                            "sql": "SELECT bad_col FROM work_log",
                            "sql_list": ["SELECT bad_col FROM work_log"],
                            "sql_diagnosis": diagnosis,
                            "sql_audit_result": diagnosis,
                            "repair_plan": repair_plan,
                            "repair_failure_class": "FIELD_NOT_FOUND",
                            "repair_status": "plan_created",
                            "repair_attempts": 1,
                            "repair_requires_user_confirmation": False,
                            "should_retry": True,
                            "retry_count": 1,
                        }
                    },
                }
            },
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_start",
                    "metadata": {"langgraph_node": "sql_execute"},
                    "data": {},
                }
            },
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "sql_execute"},
                    "data": {
                        "output": {
                            "answer": "杨凯 2024 年共有 2 条工作日志。",
                            "entry_intent": "detail_query",
                            "entry_route": "query_graph",
                            "entry_reason": "repair_plan_rerun_success",
                            "query_plan": query_plan,
                            "sql": "SELECT work_date, content FROM work_log",
                            "sql_list": ["SELECT work_date, content FROM work_log"],
                            "sql_result": {
                                "columns": ["work_date", "content"],
                                "rows": [
                                    {"work_date": "2024-01-01", "content": "项目研发"},
                                    {"work_date": "2024-01-02", "content": "联调验收"},
                                ],
                                "row_count": 2,
                            },
                            "error": None,
                            "repair_status": "rerun_completed",
                            "repair_attempts": 1,
                            "sql_retry_trace": [{"attempt": 1, "status": "success"}],
                            "out_capsule": {
                                "capsule_version": "subagent.v1",
                                "dataset_id": request.dataset_id,
                                "query_context": {"fields": ["work_date", "content"]},
                            },
                        }
                    },
                }
            },
        )


class _RepairPlanBlockedSubAgent:
    def __init__(self, db, dataset_id):
        self.db = db
        self.dataset_id = dataset_id

    async def run(self, request, _trace_context, *, graph, initial_state=None, graph_kwargs=None):
        from app.services.subagent_planning import SubAgentEvent

        diagnosis = {
            "code": "FIELD_NOT_FOUND",
            "severity": "architectural",
            "retryable": False,
            "title": "字段不存在",
            "suggested_action": "需要先修正数据集语义资产。",
        }
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_start",
                    "metadata": {"langgraph_node": "sql_audit"},
                    "data": {},
                }
            },
        )
        yield SubAgentEvent(
            event_type="graph_event",
            payload={
                "event": {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "sql_audit"},
                    "data": {
                        "output": {
                            "entry_route": "query_graph",
                            "error": "SQL 执行失败诊断：字段不存在，需要先修正数据集语义资产。",
                            "sql": "SELECT bad_col FROM work_log",
                            "sql_list": ["SELECT bad_col FROM work_log"],
                            "sql_diagnosis": diagnosis,
                            "sql_audit_result": diagnosis,
                            "repair_failure_class": "FIELD_NOT_FOUND",
                            "repair_status": "blocked",
                            "repair_attempts": 0,
                            "repair_requires_user_confirmation": False,
                            "should_retry": False,
                            "retry_count": 0,
                        }
                    },
                }
            },
        )


def test_single_dataset_success_cross_checks_five_evidence_sets(
    db_session, sample_dataset, monkeypatch
):
    """成功问数应能用 final 串起 SSE、metadata、artifact、trace index 和会话状态。"""

    publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
    monkeypatch.setattr(
        "app.api.chat.get_settings",
        lambda: Settings(MULTITURN_ENABLED=True, LANGFUSE_ENABLED=False),
    )
    monkeypatch.setattr(
        "app.api.chat.build_lead_agent_context",
        lambda *_args, **_kwargs: _lead_context(sample_dataset),
    )
    monkeypatch.setattr(
        "app.api.chat.route_query_intent",
        lambda *_args, **_kwargs: {
            "intent": "query",
            "entities": {"metrics": ["gmv"]},
            "entry_intent": "metric_query",
            "entry_route": "query_graph",
            "entry_reason": "acceptance_success",
            "route_payload": {"kind": "metric_query"},
        },
    )
    monkeypatch.setattr("app.api.chat.build_workflow", lambda _db: object())
    monkeypatch.setattr("app.api.chat.DatasetSubAgent", _SuccessSubAgent)

    events = _collect_stream_events(
        {
            "question": "最近30日GMV趋势如何",
            "dataset_id": sample_dataset.id,
            "session_id": "acceptance-success",
        },
        db_session,
    )

    final = [event for event in events if event.get("type") == "final"][-1]
    metadata = final["response_metadata"]
    assistant = db_session.get(models.Message, final["message_id"])
    trace_index = db_session.query(models.ObservabilityTraceIndex).one()
    artifacts = (
        db_session.query(models.QueryArtifact)
        .filter(models.QueryArtifact.artifact_id.in_([final["result_ref"], final["report_ref"]]))
        .all()
    )
    state = db_session.get(models.ConversationState, "acceptance-success")
    thread_state = ConversationStore(db_session).get_thread_state(state.session_id)

    assert final["conversation_id"] == assistant.conversation_id == trace_index.conversation_id
    assert final["message_id"] == assistant.id == trace_index.message_id
    assert final["langfuse_trace_id"] == metadata["langfuse"]["trace_id"]
    assert trace_index.langfuse_trace_id == final["langfuse_trace_id"]
    assert final["query_plan"] == metadata["query_plan"] == trace_index.metadata_json["query_plan"]
    assert final["candidate_assets"] == metadata["candidate_assets"]
    assert any(event.get("node") == "query_plan" for event in events)
    assert any(event.get("node") == "sql_execute" for event in events)
    assert final["sql_result"] is None
    assert {item.message_id for item in artifacts} == {final["message_id"]}
    assert thread_state["last_success_task"]["result_ref"] == final["result_artifact"]["result_ref"]
    assert thread_state["last_success_task_write_status"]["status"] == "ready"


def test_repair_plan_success_cross_checks_five_evidence_sets(
    db_session, sample_dataset, monkeypatch
):
    """RepairPlan 自动修复成功后，应串起 SSE、artifact、trace index 和 conversation_state。"""

    publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
    monkeypatch.setattr(
        "app.api.chat.get_settings",
        lambda: Settings(MULTITURN_ENABLED=True, LANGFUSE_ENABLED=False),
    )
    monkeypatch.setattr(
        "app.api.chat.build_lead_agent_context",
        lambda *_args, **_kwargs: _lead_context(sample_dataset),
    )
    monkeypatch.setattr(
        "app.api.chat.route_query_intent",
        lambda *_args, **_kwargs: {
            "intent": "query",
            "entities": {"fields": ["工作日志"]},
            "entry_intent": "detail_query",
            "entry_route": "query_graph",
            "entry_reason": "repair_plan_acceptance",
            "route_payload": {"kind": "detail_query"},
        },
    )
    monkeypatch.setattr("app.api.chat.build_workflow", lambda _db: object())
    monkeypatch.setattr("app.api.chat.DatasetSubAgent", _RepairPlanSuccessSubAgent)

    events = _collect_stream_events(
        {
            "question": "查询杨凯 2024 年工作日志",
            "dataset_id": sample_dataset.id,
            "session_id": "acceptance-repair-plan",
        },
        db_session,
    )

    final = [event for event in events if event.get("type") == "final"][-1]
    repair_event_types = [
        event["event_envelope"]["event_type"]
        for event in events
        if event.get("event_envelope", {}).get("event_type", "").startswith("repair.")
    ]
    assert repair_event_types == [
        "repair.evaluated",
        "repair.plan_created",
        "repair.rerun_started",
        "repair.rerun_completed",
    ]
    assert final["answer"] == "杨凯 2024 年共有 2 条工作日志。"
    assert final["repair_plan_ref"].startswith("artifact:")
    assert final["repair_status"] == "rerun_completed"
    assert any(ref["ref_type"] == "repair_plan" for ref in final["related_refs"])
    assert final["artifact_card"]["related_refs"] == final["related_refs"]

    repair_artifact = (
        db_session.query(models.QueryArtifact)
        .filter(models.QueryArtifact.artifact_id == final["repair_plan_ref"])
        .one()
    )
    assert repair_artifact.kind == "repair_plan"
    assert repair_artifact.message_id == final["message_id"]
    assert "actions" in repair_artifact.content_json

    trace_index = db_session.query(models.ObservabilityTraceIndex).one()
    assert trace_index.metadata_json["repair_plan"]["repair_plan_ref"] == final["repair_plan_ref"]
    assert trace_index.metadata_json["repair_plan"]["failure_class"] == "FIELD_NOT_FOUND"

    state = db_session.get(models.ConversationState, "acceptance-repair-plan")
    repair_facts = [
        item for item in (state.facts or []) if isinstance(item, dict) and item.get("kind") == "repair_plan"
    ]
    assert repair_facts[-1]["repair_plan_ref"] == final["repair_plan_ref"]
    assert repair_facts[-1]["failure_class"] == "FIELD_NOT_FOUND"
    assert repair_facts[-1]["repair_status"] == "rerun_completed"


def test_repair_plan_blocked_emits_repair_events_without_artifact_ref(
    db_session, sample_dataset, monkeypatch
):
    """不可自动修复类仍应发 repair 评估事件，但不能伪造 RepairPlan artifact。"""

    publish_manifest(db_session, sample_dataset.id, _manifest_manual_fields())
    monkeypatch.setattr(
        "app.api.chat.get_settings",
        lambda: Settings(MULTITURN_ENABLED=True, LANGFUSE_ENABLED=False),
    )
    monkeypatch.setattr(
        "app.api.chat.build_lead_agent_context",
        lambda *_args, **_kwargs: _lead_context(sample_dataset),
    )
    monkeypatch.setattr(
        "app.api.chat.route_query_intent",
        lambda *_args, **_kwargs: {
            "intent": "query",
            "entities": {"fields": ["工作日志"]},
            "entry_intent": "detail_query",
            "entry_route": "query_graph",
            "entry_reason": "repair_plan_blocked",
            "route_payload": {"kind": "detail_query"},
        },
    )
    monkeypatch.setattr("app.api.chat.build_workflow", lambda _db: object())
    monkeypatch.setattr("app.api.chat.DatasetSubAgent", _RepairPlanBlockedSubAgent)

    events = _collect_stream_events(
        {
            "question": "查询杨凯 2024 年工作日志",
            "dataset_id": sample_dataset.id,
            "session_id": "acceptance-repair-plan-blocked",
        },
        db_session,
    )

    final = [event for event in events if event.get("type") == "final"][-1]
    repair_event_types = [
        event["event_envelope"]["event_type"]
        for event in events
        if event.get("event_envelope", {}).get("event_type", "").startswith("repair.")
    ]
    assert repair_event_types == ["repair.evaluated", "repair.blocked"]
    assert final["repair_status"] == "blocked"
    assert final["repair_failure_class"] == "FIELD_NOT_FOUND"
    assert final["repair_plan_ref"] is None
    assert not any(ref.get("ref_type") == "repair_plan" for ref in final["related_refs"])
    assert (
        db_session.query(models.QueryArtifact)
        .filter(models.QueryArtifact.kind == "repair_plan")
        .count()
        == 0
    )


def test_low_confidence_candidate_confirmation_records_clarification_without_artifacts(
    db_session, sample_dataset, monkeypatch
):
    """低置信候选应停在确认态，不伪造 SQL / artifact。"""

    candidates = [
        {"dataset_id": sample_dataset.id, "dataset_name": sample_dataset.name, "score": 0.48}
    ]
    monkeypatch.setattr(
        "app.api.chat.build_lead_agent_context",
        lambda *_args, **_kwargs: _lead_context(
            sample_dataset,
            decision="ambiguous",
            should_continue=False,
            candidates=candidates,
        ),
    )
    monkeypatch.setattr(
        "app.api.chat.build_workflow",
        lambda _db: (_ for _ in ()).throw(AssertionError("blocked route must not build graph")),
    )

    events = _collect_stream_events(
        {"question": "看一下销售表现", "dataset_id": sample_dataset.id},
        db_session,
    )

    final = events[-1]
    assert final["entry_route"] == "ambiguous"
    assert final["route_payload"]["decision"] == "ambiguous"
    assert final["route_payload"]["candidates"] == candidates
    assert final["sql"] is None
    assert final["sql_result"] is None
    assert "result_ref" not in final
    trace_index = db_session.query(models.ObservabilityTraceIndex).one()
    assert trace_index.status == "blocked"
    assert trace_index.metadata_json["route_decision"]["decision"] == "ambiguous"


def test_unsupported_question_rejects_without_fabricating_artifacts(
    db_session, sample_dataset, monkeypatch
):
    """无法回答拒答应保留拒答原因，且不伪造 SQL / artifact。"""

    monkeypatch.setattr(
        "app.api.chat.build_lead_agent_context",
        lambda *_args, **_kwargs: _lead_context(sample_dataset),
    )
    monkeypatch.setattr(
        "app.api.chat.route_query_intent",
        lambda *_args, **_kwargs: {
            "intent": "function",
            "entities": {},
            "entry_intent": "rejection",
            "entry_route": "reject",
            "entry_reason": "功能操作不应进入 QueryGraph。",
            "answer": "当前问数入口暂不直接执行导出类操作。",
            "route_payload": {"kind": "unsupported_function"},
        },
    )
    monkeypatch.setattr(
        "app.api.chat.build_workflow",
        lambda _db: (_ for _ in ()).throw(AssertionError("reject route must not build graph")),
    )

    events = _collect_stream_events(
        {"question": "帮我导出报表", "dataset_id": sample_dataset.id},
        db_session,
    )

    final = events[-1]
    assert final["entry_route"] == "reject"
    assert final["entry_reason"] == "功能操作不应进入 QueryGraph。"
    assert final["route_payload"]["kind"] == "unsupported_function"
    assert final["sql"] is None
    assert final["sql_result"] is None
    assert "result_ref" not in final
    assert "report_ref" not in final
    assistant = db_session.get(models.Message, final["message_id"])
    assert assistant.response_metadata["routing"]["entry_route"] == "reject"
    trace_index = db_session.query(models.ObservabilityTraceIndex).one()
    assert trace_index.status == "blocked"
    assert trace_index.entry_route == "reject"
    assert trace_index.metadata_json["execution_path"] == "reject"


def test_controlled_failure_retry_keeps_diagnosis_and_does_not_fabricate_sql_result(
    db_session, sample_dataset, monkeypatch
):
    """受控失败 retry 应保留诊断字段，且不把失败结果伪造成查询结果。"""

    monkeypatch.setattr(
        "app.api.chat.build_lead_agent_context",
        lambda *_args, **_kwargs: _lead_context(sample_dataset),
    )
    monkeypatch.setattr(
        "app.api.chat.route_query_intent",
        lambda *_args, **_kwargs: {
            "intent": "query",
            "entities": {"metrics": ["gmv"]},
            "entry_intent": "metric_query",
            "entry_route": "query_graph",
            "entry_reason": "acceptance_retry",
            "route_payload": {"kind": "metric_query"},
        },
    )
    monkeypatch.setattr("app.api.chat.build_workflow", lambda _db: object())
    monkeypatch.setattr("app.api.chat.DatasetSubAgent", _RetryFailureSubAgent)

    events = _collect_stream_events(
        {"question": "最近30日GMV趋势如何", "dataset_id": sample_dataset.id},
        db_session,
    )

    final = events[-1]
    assert final["type"] == "final"
    assert final["sql_result"] is None
    assert final["sql_diagnosis"]["code"] == "COLUMN_NOT_FOUND"
    assert final["sql_retry_trace"] == [{"attempt": 1, "reason": "column_missing"}]
    assert any(event.get("node") == "sql_audit" for event in events)
    trace_index = db_session.query(models.ObservabilityTraceIndex).one()
    annotation = db_session.query(models.TraceAnnotationCandidate).one()
    assert trace_index.status == "failed"
    assert annotation.reason == "sql_failure"
    assert annotation.payload["sql_retry_trace"] == final["sql_retry_trace"]
