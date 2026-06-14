# ============================================================
# File Name   : test_multiturn_regression.py
# Description:
#   多轮对话 Phase 8 回归矩阵测试。
#
# Responsibilities:
#   - 固化 25 条多轮回归场景，覆盖控制面、数据面、澄清、胶囊、锁和 feature flag。
#   - 验证 MULTITURN_ENABLED 关闭时保持单轮链路等价。
#   - 为灰度前的多轮能力提供可重复执行的最小验收网。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app import models, schemas
from app.graph.nodes import build_out_capsule, merge_prior_context_node
from app.services.conversation_store import ConversationStore


MULTITURN_REGRESSION_CASES = [
    {"id": "refine_filter", "coverage": "refine"},
    {"id": "refine_time", "coverage": "refine"},
    {"id": "refine_limit", "coverage": "refine"},
    {"id": "drill_region", "coverage": "drill"},
    {"id": "drill_category", "coverage": "drill"},
    {"id": "compare_yoy", "coverage": "compare"},
    {"id": "compare_mom", "coverage": "compare"},
    {"id": "new_query_downgrade", "coverage": "new_query"},
    {"id": "result_digest_compact", "coverage": "result_digest"},
    {"id": "interpret_digest", "coverage": "interpret"},
    {"id": "blueprint_shortcut_hit", "coverage": "blueprint_shortcut"},
    {"id": "blueprint_shortcut_disabled", "coverage": "blueprint_shortcut"},
    {"id": "dataset_switch_keeps_capsules", "coverage": "dataset_switch"},
    {"id": "dataset_choice_selected_dataset_id", "coverage": "clarification"},
    {"id": "dataset_choice_index", "coverage": "clarification"},
    {"id": "dataset_pending_topic_switch", "coverage": "clarification"},
    {"id": "term_injection", "coverage": "clarification"},
    {"id": "term_topic_switch", "coverage": "clarification"},
    {"id": "schema_stale", "coverage": "schema_invalidation"},
    {"id": "damaged_capsule", "coverage": "capsule_damage"},
    {"id": "unsupported_capsule_version", "coverage": "capsule_damage"},
    {"id": "turn_lock_blocks_concurrent", "coverage": "turn_lock"},
    {"id": "stale_turn_reset", "coverage": "turn_lock"},
    {"id": "compaction_keeps_recent_two_turns", "coverage": "compaction"},
    {"id": "flag_off_singleturn_equivalence", "coverage": "feature_flag"},
]


def test_regression_matrix_has_required_25_cases():
    """Phase 8 必须固定 25 条多轮回归场景。"""

    case_ids = [item["id"] for item in MULTITURN_REGRESSION_CASES]
    coverage = {item["coverage"] for item in MULTITURN_REGRESSION_CASES}

    assert len(MULTITURN_REGRESSION_CASES) == 25
    assert len(case_ids) == len(set(case_ids))
    assert {
        "refine",
        "drill",
        "compare",
        "interpret",
        "dataset_switch",
        "clarification",
        "schema_invalidation",
        "capsule_damage",
        "turn_lock",
        "compaction",
        "feature_flag",
    }.issubset(coverage)


@pytest.mark.parametrize("case", MULTITURN_REGRESSION_CASES, ids=lambda item: item["id"])
def test_multiturn_regression_case_executes(case, db_session, monkeypatch):
    """逐条执行 Phase 8 回归场景，确保矩阵不是静态文档。"""

    globals()[f"_check_{case['id']}"](db_session, monkeypatch)


def _prior_capsule(**query_context):
    context = {
        "metrics": ["gmv"],
        "time_range": {"raw": "最近30天"},
    }
    context.update(query_context)
    return {
        "capsule_version": "subagent.v1",
        "dataset_id": 10,
        "schema_version": "schema-a",
        "question": "最近30天GMV是多少",
        "query_context": context,
        "result_digest": {
            "row_count": 1,
            "columns": [{"name": "gmv", "type": "number"}],
            "numeric_summary": {"gmv": {"min": 100, "max": 100, "sum": 100}},
        },
    }


def _merge(question, *, prior_capsule=None, lead_context=None, turn_type=None):
    state = {
        "question": question,
        "prior_capsule": prior_capsule or _prior_capsule(),
    }
    if lead_context is not None:
        state["lead_agent_context"] = lead_context
    if turn_type is not None:
        state["turn_type"] = turn_type
    return merge_prior_context_node(state)


def _check_refine_filter(_db_session, _monkeypatch):
    result = _merge("只看华东")
    merged = result["multiturn_context"]["merged_query_context"]

    assert result["turn_type"] == "continue"
    assert result["multiturn_context"]["delta_type"] == "refine"
    assert merged["metrics"] == ["gmv"]
    assert merged["filters"] == [{"raw": "华东", "source": "question_delta"}]


def _check_refine_time(_db_session, _monkeypatch):
    result = _merge("再看上个月")
    merged = result["multiturn_context"]["merged_query_context"]

    assert result["turn_type"] == "continue"
    assert result["multiturn_context"]["delta"]["time_range"] == {
        "raw": "上个月",
        "kind": "relative_named",
    }
    assert merged["time_range"]["raw"] == "上个月"


def _check_refine_limit(_db_session, _monkeypatch):
    result = _merge("再看前5")
    merged = result["multiturn_context"]["merged_query_context"]

    assert result["multiturn_context"]["delta_type"] == "refine"
    assert result["multiturn_context"]["delta"]["limit"] == 5
    assert merged["limit"] == 5


def _check_drill_region(_db_session, _monkeypatch):
    result = _merge("按地区拆分看前5")

    assert result["multiturn_context"]["delta_type"] == "drill"
    assert result["multiturn_context"]["merged_query_context"]["dimensions"] == ["地区"]
    assert result["multiturn_context"]["merged_query_context"]["limit"] == 5


def _check_drill_category(_db_session, _monkeypatch):
    result = _merge("按品类分组统计")

    assert result["multiturn_context"]["delta_type"] == "drill"
    assert result["multiturn_context"]["merged_query_context"]["dimensions"] == ["品类"]


def _check_compare_yoy(_db_session, _monkeypatch):
    result = _merge("再看同比")

    assert result["multiturn_context"]["delta_type"] == "compare"
    assert result["multiturn_context"]["delta"]["comparison"] == "同比"
    assert result["multiturn_context"]["merged_query_context"]["metrics"] == ["gmv"]


def _check_compare_mom(_db_session, _monkeypatch):
    result = _merge("再看环比")

    assert result["multiturn_context"]["delta_type"] == "compare"
    assert result["multiturn_context"]["delta"]["comparison"] == "环比"
    assert result["multiturn_context"]["merged_query_context"]["metrics"] == ["gmv"]


def _check_new_query_downgrade(_db_session, _monkeypatch):
    result = merge_prior_context_node(
        {
            "question": "按地区拆分",
            "prior_capsule": {"query_context": {"dimensions": ["门店"]}},
        }
    )

    assert result["turn_type"] == "new"
    assert result["multiturn_context"]["turn_type"] == "new_query"
    assert result["merge_debug"]["reason"] == "merged_metrics_empty_downgraded_to_new_query"


def _check_result_digest_compact(_db_session, _monkeypatch):
    capsule = build_out_capsule(
        {
            "dataset_id": 10,
            "manifest_version": "v1",
            "bound_schema_version": "schema-a",
            "question": "最近30天GMV是多少",
            "turn_type": "continue",
            "multiturn_context": {
                "merged_query_context": {"metrics": ["gmv"], "dimensions": ["地区"]},
            },
            "sql": "SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region",
            "sql_list": ["SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region"],
        },
        {
            "answer": "华东 100，华南 80。",
            "sql_result": {
                "columns": ["region", "gmv"],
                "rows": [{"region": "华东", "gmv": 100}, {"region": "华南", "gmv": 80}],
                "row_count": 2,
            },
            "sql_audit_result": {"audit_id": "audit-1"},
        },
    )

    digest = capsule["result_digest"]
    assert digest["row_count"] == 2
    assert digest["columns"] == [{"name": "region", "type": "string"}, {"name": "gmv", "type": "number"}]
    assert digest["numeric_summary"]["gmv"]["sum"] == 180.0
    assert "sample_rows" not in digest


def _check_interpret_digest(_db_session, _monkeypatch):
    result = _merge(
        "上面这个结果是什么意思",
        lead_context={
            "multiturn_classification": {"intent": "interpret"},
            "dispatch": {
                "capsule": {
                    "execution_mode": "interpret_result",
                    "should_generate_query": False,
                }
            },
        },
    )

    assert result["entry_route"] == "interpret_result"
    assert result["merge_debug"]["generated_query"] is False
    assert "不会重新生成 SQL" in result["answer"]


def _check_blueprint_shortcut_hit(_db_session, monkeypatch):
    class Settings:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = True

    monkeypatch.setattr("app.graph.nodes.get_settings", lambda: Settings())
    result = _merge(
        "只看华东",
        prior_capsule=_prior_capsule(routing_path="blueprint", blueprint_id="42"),
    )

    assert result["entry_route"] == "analysis_blueprint"
    assert result["blueprint_id"] == 42
    assert result["multiturn_context"]["blueprint_shortcut"]["enabled"] is True


def _check_blueprint_shortcut_disabled(_db_session, monkeypatch):
    class Settings:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = False

    monkeypatch.setattr("app.graph.nodes.get_settings", lambda: Settings())
    result = _merge(
        "只看华东",
        prior_capsule=_prior_capsule(routing_path="blueprint", blueprint_id="42"),
    )

    assert result["multiturn_context"]["blueprint_shortcut"]["enabled"] is True
    assert result.get("entry_route") != "analysis_blueprint"


def _check_dataset_switch_keeps_capsules(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="case-switch", user_id="u1")
    state.subagent_capsules = {"10": _prior_capsule()}
    db_session.add(state)
    db_session.commit()
    db_session.refresh(state)

    capsules = store.with_updated_capsule(
        state,
        dataset_id=11,
        capsule=_prior_capsule(dataset_id=11, metrics=["order_count"]),
    )

    assert sorted(capsules.keys()) == ["10", "11"]
    assert capsules["10"]["query_context"]["metrics"] == ["gmv"]
    assert capsules["11"]["query_context"]["metrics"] == ["order_count"]


def _pending_dataset_state(store, session_id):
    state = store.load_or_create(session_id=session_id, user_id="u1")
    state.pending_clarification = {
        "kind": "dataset_choice",
        "candidates": [
            {"index": 1, "dataset_id": 10, "dataset_name": "销售数据集"},
            {"index": 2, "dataset_id": 11, "dataset_name": "库存数据集"},
        ],
    }
    store.db.add(state)
    store.db.commit()
    store.db.refresh(state)
    return state


def _check_dataset_choice_selected_dataset_id(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _pending_dataset_state(store, "case-dataset-selected")

    result = store.resolve_pending_clarification(
        state,
        question="选销售数据集",
        clarification_response={"selected_dataset_id": 11},
    )

    assert result["status"] == "resolved"
    assert result["dataset_id"] == 11


def _check_dataset_choice_index(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _pending_dataset_state(store, "case-dataset-index")

    result = store.resolve_pending_clarification(
        state,
        question="选择 2",
        clarification_response=None,
    )

    assert result["status"] == "resolved"
    assert result["dataset_id"] == 11


def _check_dataset_pending_topic_switch(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _pending_dataset_state(store, "case-dataset-switch-topic")

    result = store.resolve_pending_clarification(
        state,
        question="换个问题，查订单数",
        clarification_response=None,
    )

    assert result["status"] == "cleared"
    assert result["reason"] == "user_changed_topic"


def _term_pending_state(store, session_id):
    state = store.load_or_create(session_id=session_id, user_id="u1")
    state.pending_clarification = {
        "kind": "term_conflict_clarification",
        "conversation_id": 88,
        "dataset_id": 10,
        "clarification_id": 7,
        "candidates": [{"index": 1, "term_id": 3, "display_name": "GMV"}],
    }
    store.db.add(state)
    store.db.commit()
    store.db.refresh(state)
    return state


def _check_term_injection(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _term_pending_state(store, "case-term-inject")

    result = store.resolve_pending_clarification(
        state,
        question="GMV",
        clarification_response=None,
    )

    assert result["status"] == "inject"
    assert result["conversation_id"] == 88
    assert result["dataset_id"] == 10
    assert result["clarification_response"] == {
        "clarification_id": 7,
        "selected_text": "GMV",
    }


def _check_term_topic_switch(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _term_pending_state(store, "case-term-switch-topic")

    result = store.resolve_pending_clarification(
        state,
        question="取消，重新查订单数",
        clarification_response=None,
    )

    assert result["status"] == "cleared"
    assert result["reason"] == "user_changed_topic"


def _capsule_state(store, session_id, capsule):
    state = store.load_or_create(session_id=session_id, user_id="u1")
    state.subagent_capsules = {"10": capsule}
    store.db.add(state)
    store.db.commit()
    store.db.refresh(state)
    return state


def _check_schema_stale(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _capsule_state(store, "case-schema-stale", _prior_capsule())

    capsule, status = store.valid_prior_capsule(
        state,
        dataset_id=10,
        expected_schema_version="schema-b",
    )

    assert capsule is None
    assert status["status"] == "stale"
    assert status["reason"] == "schema_version_mismatch"


def _check_damaged_capsule(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = _capsule_state(store, "case-damaged-capsule", "not-a-dict")

    capsule, status = store.valid_prior_capsule(
        state,
        dataset_id=10,
        expected_schema_version="schema-a",
    )

    assert capsule is None
    assert status["status"] == "missing"
    assert status["reason"] == "no_capsule"


def _check_unsupported_capsule_version(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    capsule = _prior_capsule()
    capsule["capsule_version"] = "subagent.v0"
    state = _capsule_state(store, "case-unsupported-capsule", capsule)

    capsule, status = store.valid_prior_capsule(
        state,
        dataset_id=10,
        expected_schema_version="schema-a",
    )

    assert capsule is None
    assert status["status"] == "invalid"
    assert status["reason"] == "unsupported_capsule_version"


def _check_turn_lock_blocks_concurrent(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    store.load_or_create(session_id="case-lock", user_id="u1")

    assert store.acquire_turn_lock(
        session_id="case-lock",
        lock_owner="worker-a",
        ttl_seconds=300,
    )
    assert not store.acquire_turn_lock(
        session_id="case-lock",
        lock_owner="worker-b",
        ttl_seconds=300,
    )


def _check_stale_turn_reset(db_session, _monkeypatch):
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="case-stale-lock", user_id="u1")
    state.status = "turn_pending"
    state.lock_owner = "worker-a"
    state.locked_until = datetime.utcnow() - timedelta(seconds=600)
    db_session.add(state)
    db_session.commit()

    assert store.reset_stale_turns(older_than_seconds=300) == 1
    db_session.refresh(state)
    assert state.status == "idle"
    assert state.lock_owner is None
    assert state.locked_until is None


def _check_compaction_keeps_recent_two_turns(db_session, monkeypatch):
    class Settings:
        MULTITURN_COMPACTION_ENABLED = True
        MULTITURN_COMPACTION_TOKEN_THRESHOLD = 1

    class Prompt:
        def compile(self, **variables):
            assert "第一轮问题" in variables["messages_json"]
            return "summary prompt"

    class PromptManager:
        def get_text_prompt(self, name, *, fallback):
            assert name == "datalogue-compaction"
            assert fallback
            return Prompt()

    class FakeLLM:
        def invoke(self, _messages):
            response = MagicMock()
            response.content = "旧会话摘要：用户持续分析销售经营问题。"
            return response

    class DummyTracer:
        def start_span(self, *_args, **_kwargs):
            pass

        def end_span(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr("app.services.conversation_store.get_settings", lambda: Settings())
    monkeypatch.setattr("app.services.conversation_store.get_prompt_manager", lambda: PromptManager())
    monkeypatch.setattr("app.services.conversation_store.get_llm", lambda **_kwargs: FakeLLM())
    monkeypatch.setattr("app.services.conversation_store.get_observability_tracer", lambda: DummyTracer())

    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="case-compact", user_id="u1")
    state.messages = [
        {"turn": 1, "role": "user", "content": "第一轮问题：" + "销售额" * 40},
        {"turn": 1, "role": "assistant", "content": "第一轮回答：" + "100" * 40},
        {"turn": 2, "role": "user", "content": "第二轮问题"},
        {"turn": 2, "role": "assistant", "content": "第二轮回答"},
    ]
    state.turn_index = 2
    db_session.add(state)
    db_session.commit()

    saved = store.append_completed_turn(
        session_id="case-compact",
        question="第三轮问题",
        answer="第三轮回答",
        conversation_id=1,
        active_dataset_id=10,
    )

    assert "旧会话摘要" in saved.compacted_summary
    assert [item["turn"] for item in saved.messages] == [2, 2, 3, 3]


def _check_flag_off_singleturn_equivalence(db_session, monkeypatch):
    class Settings:
        MULTITURN_ENABLED = False

    seen = {}

    async def fake_singleturn(payload, db):
        seen["payload"] = payload
        seen["db"] = db
        yield {
            "data": json.dumps(
                {
                    "type": "final",
                    "answer": "ok",
                    "sql": None,
                    "sql_list": [],
                }
            )
        }

    monkeypatch.setattr("app.api.chat.get_settings", lambda: Settings())
    monkeypatch.setattr("app.api.chat._stream_chat_singleturn", fake_singleturn)

    from app.api.chat import _stream_chat

    async def collect():
        return [
            json.loads(event["data"])
            async for event in _stream_chat(
                schemas.ChatRequest(
                    question="最近30天GMV是多少",
                    session_id="case-flag-off",
                    conversation_id=123,
                ),
                db_session,
            )
        ]

    events = asyncio.run(collect())

    assert events == [{"type": "final", "answer": "ok", "sql": None, "sql_list": []}]
    assert seen["payload"].session_id == "case-flag-off"
    assert db_session.get(models.ConversationState, "case-flag-off") is None
