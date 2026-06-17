# ============================================================
# File Name   : test_task_capsule.py
# Description:
#   Thread Memory 与 QueryTaskCapsule 的单元测试。
#
# Responsibilities:
#   - 验证明细查询、指标查询和追问胶囊的结构化状态。
#   - 验证线程状态固定写入 ConversationState.subagent_capsules["_thread"]。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.multiturn.last_success_task import (
    CapsuleSizeExceededError,
    LastSuccessTask,
    build_last_success_task,
)
from app.services.conversation_store import ConversationStore
from app.services.task_capsule import (
    build_query_task_capsule,
    build_success_task_state,
    has_query_target,
)


def _make_store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return engine, session, ConversationStore(session)


def test_detail_query_has_target_without_metrics_when_fields_exist():
    assert has_query_target(
        {
            "query_type": "detail_query",
            "fields": [{"name": "rzrq"}],
            "metrics": [],
        }
    ) is True


def test_detail_query_has_target_without_metrics_when_main_table_exists():
    assert has_query_target(
        {
            "query_type": "detail_query",
            "main_table": "plan_task_daily_record",
            "metrics": [],
        }
    ) is True


def test_detail_query_has_target_without_metrics_when_query_plan_exists():
    assert has_query_target(
        {
            "query_type": "detail_query",
            "metrics": [],
            "query_plan": {"query_type": "detail_query"},
        }
    ) is True


def test_detail_query_has_target_when_only_dsl_exists():
    task = {
        "query_type": "detail_query",
        "metrics": [],
        "dsl": {"fields": [{"name": "rzrq"}]},
    }

    assert has_query_target(task) is True


def test_metric_query_without_metrics_has_no_target():
    task = {
        "query_type": "metric_query",
        "fields": [{"name": "rzrq"}],
        "metrics": [],
    }

    assert has_query_target(task) is False


def test_build_success_task_state_keeps_only_minimal_snapshot():
    query_plan = {
        "query_type": "detail_query",
        "execution_strategy": "query_graph",
        "planner_source": "deterministic",
        "selected_assets": [
            {
                "asset_type": "field",
                "name": "rzrq",
                "display_name": "日志日期",
                "metadata": {
                    "table_name": "plan_task_daily_record",
                    "column_name": "rzrq",
                    "sample_values": ["2024-01-01"],
                    "ai_description": "large metadata should not persist",
                },
                "match_signals": [{"kind": "keyword"}],
            }
        ],
        "rejected_assets": [{"metadata": {"call_template": "SELECT ..."}}],
        "decision_factors": [{"reason": "debug only"}],
        "debug": {
            "selected_main_table": "plan_task_daily_record",
            "join_hints": [
                {
                    "left_table": "plan_task_daily_record",
                    "left_column": "account",
                    "right_table": "eas_personofile",
                    "right_column": "person_card",
                }
            ],
        },
    }
    dsl = {"fields": [{"name": "rzrq"}]}
    sql = "SELECT rzrq FROM plan_task_daily_record LIMIT 10"

    state = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan=query_plan,
        dsl=dsl,
        sql=sql,
        sql_result={"columns": ["rzrq"], "rows": [{"rzrq": "2024-01-01"}], "row_count": 1},
        schema_version="schema-v1",
        manifest_version="v1",
        turn_index=2,
    )

    assert state["capsule_version"] == "last_success_task.v1"
    assert state["dataset_id"] == 10
    assert state["query_type"] == "detail_query"
    assert state["main_table"] == "plan_task_daily_record"
    assert state["schema_version"] == "schema-v1"
    assert state["manifest_version"] == "v1"
    assert state["turn_index"] == 2
    assert "query_plan" not in state
    assert "dsl" not in state
    assert "sql" not in state
    assert "rejected_assets" not in json.dumps(state, ensure_ascii=False)
    assert "sample_values" not in json.dumps(state, ensure_ascii=False)
    assert state["selected_field_refs"] == [
        {
            "table": "plan_task_daily_record",
            "column": "rzrq",
            "role": "select_only",
            "alias": "日志日期",
        }
    ]
    assert state["join_topology"][0]["left_table"] == "plan_task_daily_record"
    assert state["result_digest"] == {
        "row_count": 1,
        "columns": ["rzrq"],
    }


def test_build_success_task_state_prefers_debug_selected_main_table():
    state = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "main_table": "wrong_top_level_table",
            "debug": {"selected_main_table": "plan_task_daily_record"},
        },
        dsl={"fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": [], "row_count": 0},
    )

    assert state["main_table"] == "plan_task_daily_record"


def test_build_success_task_state_falls_back_to_query_plan_main_table():
    state = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "main_table": "plan_task_daily_record",
        },
        dsl={"main_table": "wrong_dsl_table", "fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": [], "row_count": 0},
    )

    assert state["main_table"] == "plan_task_daily_record"


def test_build_success_task_state_falls_back_to_dsl_main_table():
    state = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={"query_type": "detail_query", "execution_strategy": "query_graph"},
        dsl={"main_table": "plan_task_daily_record", "fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": [], "row_count": 0},
    )

    assert state["main_table"] == "plan_task_daily_record"


def test_build_success_task_state_omits_sample_rows():
    state = build_success_task_state(
        question="查询金额",
        dataset_id=10,
        query_plan={"query_type": "detail_query", "execution_strategy": "query_graph"},
        dsl={"fields": [{"name": "amount"}]},
        sql="SELECT amount, created_at FROM payment",
        sql_result={
            "columns": ["amount", "created_at"],
            "rows": [
                {
                    "amount": Decimal("12.34"),
                    "created_at": datetime(2026, 6, 15, 10, 30, 0),
                }
            ],
            "row_count": 1,
        },
    )

    json.dumps(state["result_digest"])
    assert state["result_digest"] == {"row_count": 1, "columns": ["amount", "created_at"]}


def test_build_success_task_state_omits_sample_rows():
    rows = [{"idx": idx} for idx in range(6)]

    state = build_success_task_state(
        question="查询日志",
        dataset_id=10,
        query_plan={"query_type": "detail_query", "execution_strategy": "query_graph"},
        dsl={"fields": [{"name": "idx"}]},
        sql="SELECT idx FROM logs LIMIT 6",
        sql_result={"columns": ["idx"], "rows": rows, "row_count": 6},
    )

    assert state["result_digest"]["row_count"] == 6
    assert "sample_rows" not in state["result_digest"]


def test_last_success_task_forbids_extra_fields():
    with pytest.raises(ValidationError):
        LastSuccessTask.model_validate(
            {
                "capsule_version": "last_success_task.v1",
                "question": "查询日志",
                "query_type": "detail_query",
                "main_table": "plan_task_daily_record",
                "selected_field_refs": [],
                "query_plan": {"debug": "should not be allowed"},
            }
        )


def test_last_success_task_size_guard_raises():
    with pytest.raises(CapsuleSizeExceededError):
        build_last_success_task(
            question="查询日志",
            dataset_id=10,
            query_plan={
                "query_type": "detail_query",
                "execution_strategy": "query_graph",
                "debug": {"selected_main_table": "plan_task_daily_record"},
            },
            dsl={"fields": [{"name": "idx"}]},
            sql="SELECT idx FROM logs",
            sql_result={"columns": ["idx"], "rows": []},
            max_tokens=1,
        )


def test_followup_capsule_uses_prior_detail_query_context():
    last_success_task = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "planner_source": "deterministic",
            "debug": {
                "selected_main_table": "plan_task_daily_record",
                "join_hints": [
                    {
                        "left_table": "plan_task_daily_record",
                        "left_column": "account",
                        "right_table": "eas_personofile",
                        "right_column": "person_card",
                    }
                ],
            },
        },
        dsl={"fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": []},
        schema_version="schema-v1",
        manifest_version="v1",
    )
    capsule = build_query_task_capsule(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine", "delta_intent": "add_filter"},
        active_dataset_id=10,
        last_success_task=last_success_task,
    )

    assert capsule["turn_type"] == "followup_refine"
    assert capsule["dataset_id"] == 10
    assert capsule["base_main_table"] == "plan_task_daily_record"
    assert capsule["base_query_plan"]["query_type"] == "detail_query"
    assert "selected_assets" not in capsule["base_query_plan"]
    assert capsule["base_query_plan"]["debug"]["selected_main_table"] == "plan_task_daily_record"
    assert capsule["base_question"] == "查询10条用户日志"
    assert capsule["inheritance_status"]["status"] == "loaded"
    assert "查询10条用户日志" in capsule["standalone_question"]
    assert "只看汤杰" in capsule["standalone_question"]


def test_followup_refine_does_not_inherit_when_dataset_mismatches():
    last_success_task = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=11,
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "debug": {"selected_main_table": "plan_task_daily_record"},
        },
        dsl={"fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": []},
    )
    capsule = build_query_task_capsule(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine", "delta_intent": "add_filter"},
        active_dataset_id=10,
        last_success_task=last_success_task,
    )

    assert capsule["standalone_question"] == "只看汤杰"
    assert capsule["base_task_ref"] is None
    assert capsule["base_question"] is None
    assert capsule["base_main_table"] is None
    assert capsule["base_query_plan"] is None
    assert capsule["inheritance_status"]["reason"] == "dataset_mismatch"


def test_followup_refine_does_not_inherit_legacy_last_success_task():
    capsule = build_query_task_capsule(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine", "delta_intent": "add_filter"},
        active_dataset_id=10,
        last_success_task={
            "question": "查询10条用户日志",
            "dataset_id": 10,
            "query_type": "detail_query",
            "main_table": "plan_task_daily_record",
            "query_plan": {"selected_assets": [{"metadata": {"huge": "payload"}}]},
        },
    )

    assert capsule["base_task_ref"] is None
    assert capsule["base_query_plan"] is None
    assert capsule["inheritance_status"]["reason"] == "unsupported_capsule_version"


def test_followup_refine_does_not_inherit_when_prior_has_no_query_target():
    capsule = build_query_task_capsule(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine", "delta_intent": "add_filter"},
        active_dataset_id=10,
        last_success_task={
            "question": "查询10条用户日志",
            "dataset_id": 10,
            "query_type": "metric_query",
            "metrics": [],
        },
    )

    assert capsule["standalone_question"] == "只看汤杰"
    assert capsule["base_task_ref"] is None
    assert capsule["base_main_table"] is None
    assert capsule["base_query_plan"] is None


def test_followup_explain_capsule_does_not_inherit_prior_query_context():
    capsule = build_query_task_capsule(
        question="解释一下刚才的结果",
        turn_event={"event_type": "followup_explain"},
        active_dataset_id=10,
        last_success_task={
            "question": "查询10条用户日志",
            "main_table": "plan_task_daily_record",
            "query_plan": {"query_type": "detail_query"},
        },
    )

    assert capsule["turn_type"] == "followup_explain"
    assert capsule["standalone_question"] == "解释一下刚才的结果"
    assert capsule["base_task_ref"] is None
    assert capsule["base_main_table"] is None
    assert capsule["base_query_plan"] is None


def test_thread_state_is_stored_under_reserved_subagent_capsule_key():
    engine, session, store = _make_store()
    try:
        updated = store.update_thread_state(
            "session-task-capsule",
            {
                "last_success_task": {"question": "查询10条用户日志"},
                "active_task": {"turn_type": "followup_refine"},
            },
        )

        assert updated["last_success_task"]["question"] == "查询10条用户日志"
        assert store.get_thread_state("session-task-capsule") == updated

        state = store.load("session-task-capsule")
        assert state is not None
        assert state.subagent_capsules["_thread"] == updated
    finally:
        session.close()
        engine.dispose()


def test_update_thread_state_shallow_merges_and_preserves_existing_keys():
    engine, session, store = _make_store()
    try:
        first = store.update_thread_state(
            "session-merge",
            {
                "last_success_task": {"question": "查询10条用户日志"},
                "active_task": {"turn_type": "new_query"},
            },
        )
        second = store.update_thread_state(
            "session-merge",
            {
                "active_task": {"turn_type": "followup_refine"},
                "fallback_reason": "template_missed",
            },
        )

        assert first["last_success_task"]["question"] == "查询10条用户日志"
        assert second["last_success_task"]["question"] == "查询10条用户日志"
        assert second["active_task"]["turn_type"] == "followup_refine"
        assert second["fallback_reason"] == "template_missed"
    finally:
        session.close()
        engine.dispose()


def test_thread_state_json_encodes_non_sample_fields():
    engine, session, store = _make_store()
    try:
        updated = store.update_thread_state(
            "session-json-thread",
            {
                "last_success_task": {
                    "question": "查询金额",
                    "generated_at": datetime(2026, 6, 15, 11, 0, 0),
                    "threshold": Decimal("9.8"),
                }
            },
        )

        json.dumps(updated)
        task = updated["last_success_task"]
        assert task["generated_at"] == "2026-06-15T11:00:00"
        assert task["threshold"] == 9.8
    finally:
        session.close()
        engine.dispose()


def test_capsule_metas_skips_reserved_thread_state_key():
    engine, session, store = _make_store()
    try:
        store.update_thread_state("session-thread-meta", {"last_success_task": {"question": "查询"}})

        state = store.load("session-thread-meta")
        assert state is not None
        assert state.subagent_capsules["_thread"]["last_success_task"]["question"] == "查询"
        assert store.capsule_metas(state) == {}
    finally:
        session.close()
        engine.dispose()


def test_capsule_metas_preserves_real_dataset_capsules_with_thread_state():
    engine, session, store = _make_store()
    try:
        store.update_thread_state("session-real-capsule", {"active_task": {"turn_type": "new_query"}})
        state = store.load("session-real-capsule")
        assert state is not None
        capsules = dict(state.subagent_capsules or {})
        capsules["10"] = {
            "capsule_version": "1.0",
            "dataset_id": 10,
            "schema_version": "v1",
            "updated_turn": 3,
        }
        state.subagent_capsules = capsules
        session.add(state)
        session.commit()
        session.refresh(state)

        metas = store.capsule_metas(state)
        assert "_thread" not in metas
        assert metas["10"]["dataset_id"] == "10"
        assert metas["10"]["updated_turn"] == 3
    finally:
        session.close()
        engine.dispose()


def test_lead_multiturn_context_exposes_thread_last_success_task():
    engine, session, store = _make_store()
    try:
        store.update_thread_state(
            "session-lead-context",
            {
                "last_success_task": {
                    "question": "查询10条用户日志",
                    "query_type": "detail_query",
                    "main_table": "plan_task_daily_record",
                },
                "active_task": {"turn_type": "followup_refine"},
            },
        )
        state = store.load("session-lead-context")

        context = store.lead_multiturn_context(state)

        assert context["last_success_task"]["question"] == "查询10条用户日志"
        assert context["active_task"]["turn_type"] == "followup_refine"
        assert context["capsule_metas"] == {}
    finally:
        session.close()
        engine.dispose()


def test_update_thread_state_uses_chat_default_user_id_when_creating_state():
    engine, session, store = _make_store()
    try:
        store.update_thread_state("session-default-user", {"active_task": {"turn_type": "new_query"}})

        state = store.load("session-default-user")
        assert state is not None
        assert state.user_id == "1"
    finally:
        session.close()
        engine.dispose()


def test_update_thread_state_accepts_explicit_user_id_when_creating_state():
    engine, session, store = _make_store()
    try:
        store.update_thread_state(
            "session-explicit-user",
            {"active_task": {"turn_type": "new_query"}},
            user_id="ken",
        )

        state = store.load("session-explicit-user")
        assert state is not None
        assert state.user_id == "ken"
    finally:
        session.close()
        engine.dispose()
