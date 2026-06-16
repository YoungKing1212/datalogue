# ============================================================
# File Name   : test_multiturn.py
# Description:
#   SubAgent 数据面多轮上下文合并与输出胶囊测试。
#
# Responsibilities:
#   - 验证 prior_capsule 到 multiturn_context 的确定性合并。
#   - 验证 DSL 生成可消费多轮查询上下文。
#   - 验证 out_capsule / ResultDigest 的基础结构。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

import json
import asyncio
from unittest.mock import MagicMock, patch

from app import models, schemas
from app.graph.nodes import build_out_capsule, dsl_generate_node
from app.services.conversation_store import (
    ConversationStore,
    pending_clarification_from_final_payload,
    session_key,
)
from app.services.lead_agent import merge_multiturn_decision_for_chat
from app.services.runner import DatasetSubAgentRequest, InProcessDatasetSubAgentRunner


def _call_merge(state):
    """模拟原 merge_prior_context_node 输出的 dict 形态（Phase 2 上提后由 services 接管）。"""
    decision = merge_multiturn_decision_for_chat(
        state=state, out_capsule_factory=build_out_capsule
    )
    if decision.interpret_payload is not None:
        return dict(decision.interpret_payload)
    output = {
        "turn_type": decision.turn_type,
        "multiturn_context": decision.multiturn_context,
        "merge_debug": decision.merge_debug,
    }
    if decision.synthesized_question is not None:
        output["question"] = decision.synthesized_question
    blueprint_shortcut = decision.blueprint_shortcut
    if blueprint_shortcut and blueprint_shortcut.get("settings_enabled"):
        output.update(
            {
                "entry_intent": "analysis_blueprint",
                "entry_route": "analysis_blueprint",
                "blueprint_id": blueprint_shortcut.get("blueprint_id"),
                "route_payload": {"kind": "analysis_blueprint", **blueprint_shortcut},
            }
        )
    return output


def test_chat_request_accepts_session_id():
    """ChatRequest 应可接收业务多轮 session_id，且不影响既有 conversation_id。"""
    payload = schemas.ChatRequest(
        question="最近30天GMV是多少",
        session_id="session-a",
        conversation_id=123,
    )

    assert payload.session_id == "session-a"
    assert payload.conversation_id == 123
    assert session_key(payload.session_id, payload.conversation_id) == "session-a"


def test_conversation_store_lock_and_complete_turn(db_session):
    """ConversationStore 应支持加载、抢锁、完成写回和释放锁。"""
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="session-a", user_id="u1")

    assert state.session_id == "session-a"
    assert state.status == "idle"
    assert store.acquire_turn_lock(
        session_id="session-a",
        lock_owner="worker-a",
        ttl_seconds=300,
    ) is True
    assert store.acquire_turn_lock(
        session_id="session-a",
        lock_owner="worker-b",
        ttl_seconds=300,
    ) is False

    saved = store.append_completed_turn(
        session_id="session-a",
        question="看销售额",
        answer="销售额为 100。",
        conversation_id=1,
        active_dataset_id=10,
        resolved_time_context={"detected_time_range": {"label": "近30天"}},
    )

    assert saved.status == "idle"
    assert saved.turn_index == 1
    assert saved.active_dataset_id == "10"
    assert len(saved.messages) == 2
    assert saved.resolved_time_context["detected_time_range"]["label"] == "近30天"


def test_conversation_state_registered_in_metadata(db_session):
    """ConversationState 必须注册到 Base metadata，SQLite 测试才能自动建表。"""
    state = models.ConversationState(
        session_id="session-meta",
        user_id="u1",
        messages=[],
        facts=[],
        subagent_capsules={},
    )
    db_session.add(state)
    db_session.commit()

    assert db_session.get(models.ConversationState, "session-meta").user_id == "u1"


def test_conversation_store_valid_prior_capsule_checks_schema(db_session):
    """读取 prior capsule 时应按 dataset/schema 校验，过期胶囊降级为首轮。"""
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="session-capsule", user_id="u1")
    state.subagent_capsules = {
        "10": {
            "capsule_version": "subagent.v1",
            "dataset_id": 10,
            "bound_schema_version": "schema-a",
            "query_context": {"metrics": ["gmv"]},
        }
    }
    db_session.add(state)
    db_session.commit()
    db_session.refresh(state)

    capsule, status = store.valid_prior_capsule(
        state,
        dataset_id=10,
        expected_schema_version="schema-a",
    )
    assert status["status"] == "loaded"
    assert capsule["query_context"]["metrics"] == ["gmv"]

    stale_capsule, stale_status = store.valid_prior_capsule(
        state,
        dataset_id=10,
        expected_schema_version="schema-b",
    )
    assert stale_capsule is None
    assert stale_status["status"] == "stale"


def test_stream_chat_consumes_store_active_dataset_and_prior_capsule(db_session, monkeypatch):
    """真实 _stream_chat 包装层应消费 ConversationStore 的 active_dataset_id 与 prior_capsule。"""

    class Settings:
        MULTITURN_ENABLED = True
        MULTITURN_LOCK_TTL_SECONDS = 300

    seen = {}
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="assistant-session-1", user_id="1")
    state.active_dataset_id = "10"
    state.subagent_capsules = {
        "10": {
            "capsule_version": "subagent.v1",
            "dataset_id": 10,
            "schema_version": "schema-a",
            "question": "最近30天GMV是多少",
            "query_context": {"metrics": ["gmv"], "time_range": {"raw": "最近30天"}},
            "result_digest": {"row_count": 1, "columns": [{"name": "gmv", "type": "number"}]},
        }
    }
    db_session.add(state)
    db_session.commit()

    def fake_build_lead_agent_context(
        _db,
        *,
        question,
        conversation,
        payload_dataset_id,
        multiturn_context,
        **_kwargs,
    ):
        seen["lead_multiturn_context"] = multiturn_context
        assert payload_dataset_id is None
        assert conversation.dataset_id is None
        assert multiturn_context["active_dataset_id"] == "10"
        return {
            "tool_policy": {},
            "selected_skills": [],
            "planned_tool_calls": [],
            "executed_tool_calls": [],
            "system_inferred_tool_calls": [],
            "policy_violations": [],
            "original_question": question,
            "resolved_question": question,
            "multiturn_context": multiturn_context,
            "multiturn_classification": {
                "intent": "continue",
                "should_inherit_dataset": True,
            },
            "time_context": {},
            "thread_context": {
                "active_dataset_id": 10,
                "locked_dataset_id": 10,
                "dataset_lock_source": "multiturn_active",
            },
            "route_decision": {
                "decision": "locked",
                "dataset_id": 10,
                "dataset_name": "销售数据集",
                "manifest_version": "v1",
                "bound_schema_version": "schema-a",
                "score": 1,
                "candidates": [],
                "reason": "继承 active_dataset_id",
            },
            "schema_status": {"status": "ok", "stale": False, "dataset_id": 10},
            "clarification": None,
            "dispatch": {"dataset_id": 10},
            "audit_trace": {"dispatched": True},
            "should_continue": True,
            "effective_dataset_id": 10,
        }

    class FakeRunner:
        def __init__(self, _graph, _db):
            pass

        async def run(self, request, _trace_context, initial_state, **_kwargs):
            seen["subagent_request"] = request
            seen["initial_state"] = initial_state
            assert request.prior_capsule["query_context"]["metrics"] == ["gmv"]
            assert request.prior_capsule_status["status"] == "loaded"
            assert initial_state["prior_capsule"]["query_context"]["metrics"] == ["gmv"]
            yield {
                "event": "on_chain_end",
                "metadata": {"langgraph_node": "merge_prior_context"},
                "data": {
                    "output": {
                        "turn_type": "continue",
                        "question": "基于上一轮问题「最近30天GMV是多少」，按地区拆分",
                        "multiturn_context": {
                            "turn_type": "continue",
                            "prior_query_context": {"metrics": ["gmv"]},
                            "merged_query_context": {"metrics": ["gmv"], "dimensions": ["地区"]},
                        },
                        "merge_debug": {"used_prior": True},
                    }
                },
            }
            yield {
                "event": "on_chain_end",
                "metadata": {},
                "data": {
                    "output": {
                        "answer": "已按地区拆分。",
                        "sql": "SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region",
                        "sql_list": ["SELECT region, SUM(amount) AS gmv FROM orders GROUP BY region"],
                        "sql_result": {
                            "columns": ["region", "gmv"],
                            "rows": [{"region": "华东", "gmv": 100}],
                            "row_count": 1,
                        },
                        "dsl": {"metrics": ["gmv"], "dimensions": ["region"]},
                        "generation_mode": "semantic",
                        "out_capsule": {
                            "capsule_version": "subagent.v1",
                            "dataset_id": 10,
                            "schema_version": "schema-a",
                            "query_context": {"metrics": ["gmv"], "dimensions": ["地区"]},
                        },
                    }
                },
            }

    monkeypatch.setattr("app.api.chat.get_settings", lambda: Settings())
    monkeypatch.setattr("app.api.chat.build_lead_agent_context", fake_build_lead_agent_context)
    monkeypatch.setattr("app.api.chat.build_workflow", lambda _db: object())
    monkeypatch.setattr("app.api.chat.InProcessDatasetSubAgentRunner", FakeRunner)

    from app.api.chat import _stream_chat

    async def collect():
        return [
            json.loads(event["data"])
            async for event in _stream_chat(
                schemas.ChatRequest(
                    question="按地区拆分",
                    session_id="assistant-session-1",
                ),
                db_session,
            )
        ]

    events = asyncio.run(collect())
    final = [event for event in events if event.get("type") == "final"][-1]
    saved = store.load("assistant-session-1")

    assert final["turn_type"] == "continue"
    assert final["prior_capsule_status"]["status"] == "loaded"
    assert final["merge_debug"]["used_prior"] is True
    assert seen["subagent_request"].dataset_id == 10
    assert saved.active_dataset_id == "10"
    assert saved.subagent_capsules["10"]["query_context"]["dimensions"] == ["地区"]


def test_conversation_store_resolves_dataset_pending_clarification(db_session):
    """数据集级挂起澄清应支持下一轮按序号恢复 active dataset。"""
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="session-dataset-pending", user_id="u1")
    state.pending_clarification = {
        "kind": "dataset_choice",
        "original_question": "查询销售明细",
        "candidates": [
            {"index": 1, "dataset_id": 10, "dataset_name": "销售数据集"},
            {"index": 2, "dataset_id": 11, "dataset_name": "库存数据集"},
        ],
    }
    db_session.add(state)
    db_session.commit()
    db_session.refresh(state)

    result = store.resolve_pending_clarification(
        state,
        question="选第一个",
        clarification_response=None,
    )

    assert result["status"] == "resolved"
    assert result["type"] == "dataset"
    assert result["dataset_id"] == 10
    assert result["original_question"] == "查询销售明细"
    assert result["clear_pending"] is True


def test_conversation_store_injects_term_pending_clarification(db_session):
    """术语级挂起澄清应注入 clarification_response 和原 conversation_id。"""
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="session-term-pending", user_id="u1")
    state.pending_clarification = {
        "kind": "term_conflict_clarification",
        "conversation_id": 123,
        "dataset_id": 10,
        "clarification_id": 99,
        "candidates": [{"index": 1, "term_id": 7, "display_name": "GMV"}],
    }
    db_session.add(state)
    db_session.commit()
    db_session.refresh(state)

    result = store.resolve_pending_clarification(
        state,
        question="GMV",
        clarification_response=None,
    )

    assert result["status"] == "inject"
    assert result["conversation_id"] == 123
    assert result["dataset_id"] == 10
    assert result["clarification_response"] == {
        "clarification_id": 99,
        "selected_text": "GMV",
    }


def test_conversation_store_clears_pending_on_completed_turn(db_session):
    """恢复成功后 append_completed_turn 应可清理 pending_clarification。"""
    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="session-clear-pending", user_id="u1")
    state.pending_clarification = {"kind": "dataset_choice"}
    db_session.add(state)
    db_session.commit()

    saved = store.append_completed_turn(
        session_id="session-clear-pending",
        question="选第一个",
        answer="已选择销售数据集。",
        conversation_id=1,
        active_dataset_id=10,
        clear_pending_clarification=True,
    )

    assert saved.pending_clarification is None


def test_conversation_store_compacts_old_messages_when_enabled(db_session, monkeypatch):
    """消息超过阈值时应压缩旧轮次，只保留最近 2 轮原文。"""

    class Settings:
        MULTITURN_COMPACTION_ENABLED = True
        MULTITURN_COMPACTION_TOKEN_THRESHOLD = 10

    class Prompt:
        name = "datalogue-compaction"
        version = "test"
        source = "test"

        def compile(self, **variables):
            assert "第一轮问题" in variables["messages_json"]
            return f"summary prompt: {variables['existing_summary']}"

    class PromptManager:
        def __init__(self):
            self.names = []

        def get_text_prompt(self, name, *, fallback):
            self.names.append(name)
            assert fallback
            return Prompt()

    class FakeLLM:
        def invoke(self, messages):
            response = MagicMock()
            response.content = "旧会话摘要：用户持续分析销售经营问题；偏好中文简洁回答；无未解决问题。"
            return response

    class DummyTracer:
        def __init__(self):
            self.calls = []

        def start_span(self, trace_context, **kwargs):
            self.calls.append(("start", kwargs))

        def end_span(self, trace_context, **kwargs):
            self.calls.append(("end", kwargs))

    prompt_manager = PromptManager()
    tracer = DummyTracer()
    monkeypatch.setattr("app.services.conversation_store.get_settings", lambda: Settings())
    monkeypatch.setattr("app.services.conversation_store.get_prompt_manager", lambda: prompt_manager)
    monkeypatch.setattr("app.services.conversation_store.get_llm", lambda **_kwargs: FakeLLM())
    monkeypatch.setattr("app.services.conversation_store.get_observability_tracer", lambda: tracer)

    store = ConversationStore(db_session)
    state = store.load_or_create(session_id="session-compact", user_id="u1")
    state.messages = [
        {"turn": 1, "role": "user", "content": "第一轮问题：" + "销售额" * 80},
        {"turn": 1, "role": "assistant", "content": "第一轮回答：" + "100" * 80},
        {"turn": 2, "role": "user", "content": "第二轮问题"},
        {"turn": 2, "role": "assistant", "content": "第二轮回答"},
    ]
    state.turn_index = 2
    state.compacted_summary = "旧摘要"
    db_session.add(state)
    db_session.commit()

    saved = store.append_completed_turn(
        session_id="session-compact",
        question="第三轮问题",
        answer="第三轮回答",
        conversation_id=1,
        active_dataset_id=10,
        trace_context=object(),
    )

    assert prompt_manager.names == ["datalogue-compaction"]
    assert any(call[1].get("node") == "context-compaction" for call in tracer.calls)
    assert "旧会话摘要" in saved.compacted_summary
    assert [item["turn"] for item in saved.messages] == [2, 2, 3, 3]
    assert all("第一轮" not in item["content"] for item in saved.messages)


def test_pending_clarification_from_final_payload_enriches_context():
    """final payload 应压缩成下一轮可恢复的 ConversationState pending。"""
    pending = pending_clarification_from_final_payload(
        {
            "conversation_id": 88,
            "route_payload": {
                "kind": "manifest_route",
                "decision": "ambiguous",
                "candidates": [{"dataset_id": 10, "dataset_name": "销售数据集"}],
            },
        },
        original_question="查销售额",
    )

    assert pending["kind"] == "dataset_choice"
    assert pending["conversation_id"] == 88
    assert pending["original_question"] == "查销售额"
    assert pending["candidates"][0]["dataset_id"] == 10


def test_runner_injects_prior_capsule_into_initial_state(db_session):
    """Runner 应把 request.prior_capsule 注入 SubAgent 初始状态。"""

    class DummyGraph:
        def __init__(self):
            self.seen_state = None

        async def astream_events(self, initial_state, **_kwargs):
            self.seen_state = initial_state
            yield {"event": "on_chain_end", "metadata": {}, "data": {"output": initial_state}}

    graph = DummyGraph()
    runner = InProcessDatasetSubAgentRunner(graph, db_session)
    request = DatasetSubAgentRequest(
        question="按地区拆分",
        dataset_id=10,
        manifest_version="v1",
        bound_schema_version="schema-a",
        thread_id="thread-1",
        time_context={},
        thread_context={},
        route_decision={"dataset_id": 10},
        schema_status={},
        lead_agent_context={},
        prior_capsule={"query_context": {"metrics": ["gmv"]}},
        prior_capsule_status={"status": "loaded"},
    )

    async def collect():
        return [event async for event in runner.run(request, None, {"question": "按地区拆分"})]

    events = asyncio.run(collect())
    assert events
    assert graph.seen_state["prior_capsule"]["query_context"]["metrics"] == ["gmv"]
    assert graph.seen_state["prior_capsule_status"]["status"] == "loaded"


def test_merge_prior_context_continue_merges_query_context():
    """继续追问应复用上一轮 query_context，并把本轮 delta 合并进去。"""
    prior_capsule = {
        "question": "最近30天GMV是多少",
        "query_context": {
            "metrics": ["gmv"],
            "time_range": {"raw": "最近30天"},
            "limit": 100,
        },
        "result_digest": {"row_count": 1, "columns": ["gmv"]},
    }

    result = _call_merge(
        {
            "question": "按地区拆分看前5",
            "prior_capsule": prior_capsule,
        }
    )

    assert result["turn_type"] == "continue"
    assert result["question"] == "基于上一轮问题「最近30天GMV是多少」，按地区拆分看前5"
    merged = result["multiturn_context"]["merged_query_context"]
    assert merged["metrics"] == ["gmv"]
    assert merged["dimensions"] == ["地区"]
    assert merged["limit"] == 5
    assert result["multiturn_context"]["delta_type"] == "drill"
    assert result["merge_debug"]["used_prior"] is True


def test_merge_prior_context_compare_marks_compare_delta():
    """同比/环比追问应被识别为 compare delta，并保留上一轮指标。"""
    prior_capsule = {
        "question": "最近30天GMV是多少",
        "query_context": {"metrics": ["gmv"], "time_range": {"raw": "最近30天"}},
    }

    result = _call_merge(
        {
            "question": "再看同比",
            "prior_capsule": prior_capsule,
        }
    )

    assert result["turn_type"] == "continue"
    assert result["multiturn_context"]["delta_type"] == "compare"
    assert result["multiturn_context"]["delta"]["comparison"] == "同比"
    assert result["multiturn_context"]["merged_query_context"]["metrics"] == ["gmv"]


def test_merge_prior_context_empty_metrics_downgrades_to_new_query():
    """合并后没有指标时应降级为 new_query，避免带着空指标继续生成 SQL。"""
    result = _call_merge(
        {
            "question": "按地区拆分",
            "prior_capsule": {"query_context": {"dimensions": ["门店"]}},
        }
    )

    assert result["turn_type"] == "new"
    assert result["multiturn_context"]["turn_type"] == "new_query"
    assert result["multiturn_context"]["merged_query_context"] is None
    assert result["merge_debug"]["reason"] == "merged_metrics_empty_downgraded_to_new_query"


def test_merge_prior_context_interpret_uses_result_digest_without_query():
    """解释轮次应基于 prior ResultDigest 直接回答，不进入 SQL 生成。"""
    result = _call_merge(
        {
            "question": "上面这个结果是什么意思",
            "prior_capsule": {
                "query_context": {"metrics": ["gmv"]},
                "result_digest": {
                    "row_count": 2,
                    "columns": [{"name": "gmv", "type": "number"}],
                    "numeric_summary": {"gmv": {"min": 10, "max": 20, "sum": 30}},
                    "sql_audit_id": "audit-1",
                },
            },
            "lead_agent_context": {
                "multiturn_classification": {"intent": "interpret"},
                "dispatch": {
                    "capsule": {
                        "execution_mode": "interpret_result",
                        "should_generate_query": False,
                    }
                },
            },
        }
    )

    assert result["turn_type"] == "interpret"
    assert result["entry_route"] == "interpret_result"
    assert result["merge_debug"]["generated_query"] is False
    assert "不会重新生成 SQL" in result["answer"]
    assert result["out_capsule"]["result_digest"]["has_answer"] is True


def test_merge_prior_context_blueprint_shortcut_when_enabled(monkeypatch):
    """蓝图换参仍在上一轮参数空间内时，可在开关下直接进入蓝图执行捷径。"""

    class Settings:
        MULTITURN_BLUEPRINT_SHORTCUT_ENABLED = True

    monkeypatch.setattr("app.services.multiturn_context.get_settings", lambda: Settings())

    result = _call_merge(
        {
            "question": "只看华东",
            "prior_capsule": {
                "question": "最近30天GMV是多少",
                "query_context": {
                    "metrics": ["gmv"],
                    "routing_path": "blueprint",
                    "blueprint_id": "42",
                    "filters": [],
                },
            },
        }
    )

    assert result["entry_route"] == "analysis_blueprint"
    assert result["blueprint_id"] == 42
    assert result["multiturn_context"]["blueprint_shortcut"]["enabled"] is True


def test_merge_prior_context_without_continue_signal_keeps_new_turn():
    """有 prior 但当前问题不是追问时，不应强行合并上一轮上下文。"""
    result = _call_merge(
        {
            "question": "最近30天订单数是多少",
            "prior_capsule": {"query_context": {"metrics": ["gmv"]}},
        }
    )

    assert result["turn_type"] == "new"
    assert result["multiturn_context"]["merged_query_context"] is None
    assert result["merge_debug"]["used_prior"] is False


def test_dsl_generate_includes_multiturn_context_in_prompt():
    """DSL 生成节点应把多轮合并结果注入 prompt，供模型按合并后的上下文生成 DSL。"""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {
            "metrics": ["gmv"],
            "dimensions": ["region"],
            "filters": [],
            "limit": 5,
        },
        ensure_ascii=False,
    )
    mock_response.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    mock_llm.invoke.return_value = mock_response

    state = {
        "question": "基于上一轮问题「最近30天GMV是多少」，按地区拆分看前5",
        "schema_context": "【语义层】\n- gmv: 成交金额\n- region: 地区",
        "schema_structured": {
            "metrics": [{"id": 1, "name": "gmv", "display_name": "GMV"}],
            "dimensions": [{"id": 2, "name": "region", "display_name": "地区"}],
            "fields": [],
        },
        "metric_resolution": {"all_matched": True, "metrics": [], "dimensions": []},
        "query_constraints": {"enabled": False},
        "multiturn_context": {
            "turn_type": "continue",
            "prior_query_context": {"metrics": ["gmv"]},
            "delta": {"dimensions": ["地区"], "limit": 5},
            "merged_query_context": {"metrics": ["gmv"], "dimensions": ["地区"], "limit": 5},
        },
        "token_usage": None,
    }

    with patch("app.graph.nodes.get_llm", return_value=mock_llm):
        result = dsl_generate_node(state)

    messages = mock_llm.invoke.call_args.args[0]
    human_content = messages[1].content
    assert "【多轮查询上下文】" in human_content
    assert "merged_query_context" in human_content
    assert result["dsl"]["metrics"][0]["name"] == "gmv"
    assert result["dsl"]["dimensions"][0]["name"] == "region"
    assert result["generation_mode"] == "semantic"


def test_build_out_capsule_contains_query_context_and_result_digest():
    """输出胶囊应携带下一轮可复用的 query_context 和紧凑 ResultDigest。"""
    state = {
        "dataset_id": 10,
        "manifest_version": "v1",
        "bound_schema_version": "schema-a",
        "question": "最近30天GMV是多少",
        "turn_type": "continue",
        "multiturn_context": {
            "merged_query_context": {"metrics": ["gmv"], "limit": 5},
        },
        "sql": "SELECT 1 AS gmv",
        "sql_list": ["SELECT 1 AS gmv"],
    }
    updates = {
        "answer": "最近30天GMV为 1。",
        "sql_result": {
            "columns": ["gmv"],
            "rows": [{"gmv": 1}],
            "row_count": 1,
        },
    }

    capsule = build_out_capsule(state, updates)

    assert capsule["capsule_version"] == "subagent.v1"
    assert capsule["query_context"]["metrics"] == ["gmv"]
    assert capsule["result_digest"]["status"] == "ok"
    assert capsule["result_digest"]["row_count"] == 1
    assert capsule["result_digest"]["columns"] == [{"name": "gmv", "type": "number"}]
    assert capsule["result_digest"]["numeric_summary"]["gmv"]["sum"] == 1.0
    assert "sample_rows" not in capsule["result_digest"]
    assert capsule["result_digest"]["has_answer"] is True
    assert capsule["schema_version"] == "schema-a"
