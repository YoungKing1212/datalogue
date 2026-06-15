# ============================================================
# File Name   : test_lead_agent_tools.py
# Description:
#   LeadAgent 控制面工具测试。
#
# Responsibilities:
#   - 验证时间解析、Manifest 路由编排和 schema stale 标记。
#   - 确认 LeadAgent 只输出控制面上下文，不承接语义层内部解析。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

import json
from datetime import datetime

from app import models
from app.services.dataset_manifest import publish_manifest
from app.services.lead_agent import (
    build_lead_agent_context,
    build_resolved_question,
    build_tool_policy,
    merge_multiturn_decision_for_chat,
    plan_tool_calls_with_llm,
    resolve_time_context,
)


def _manual_fields():
    return {
        "description": (
            "订单销售数据集用于分析门店订单在日、周、月范围内的GMV、订单数、地区和品类表现，"
            "覆盖销售运营人员查看各区域成交趋势、品类结构、异常波动和门店经营质量，不覆盖库存、会员画像和售后工单。"
        ),
        "business_domain": ["销售运营"],
        "sample_questions": [
            "最近30日GMV趋势如何",
            "按地区统计本月订单数",
            "各品类销售额排名",
            "华东区域订单量是多少",
            "本周门店成交金额变化",
        ],
        "routing_negative_examples": [
            "库存周转率是多少",
            "会员画像年龄分布",
            "售后工单处理时长",
        ],
    }


def test_time_tool_detects_relative_and_explicit_ranges():
    """TimeTool 应解析常见相对时间和显式年份。"""

    now = datetime(2026, 6, 12, 9, 30)
    recent = resolve_time_context("最近30天GMV趋势如何", now=now)
    assert recent["detected_time_range"] == {
        "label": "最近30日",
        "start_date": "2026-05-14",
        "end_date": "2026-06-12",
        "granularity": "day",
        "source": "relative_recent_days",
    }

    explicit_year = resolve_time_context("我要查询2024年杨凯的日报", now=now)
    assert explicit_year["detected_time_range"]["label"] == "2024年"
    assert explicit_year["detected_time_range"]["start_date"] == "2024-01-01"
    assert explicit_year["detected_time_range"]["end_date"] == "2024-12-31"


def test_resolved_question_replaces_relative_year():
    """LeadAgent 应把相对时间改写成下游可消费的明确时间文本。"""

    time_context = resolve_time_context(
        "杨凯去年的日报记录有哪些",
        now=datetime(2026, 6, 12, 9, 30),
    )

    resolved = build_resolved_question("杨凯去年的日报记录有哪些", time_context)

    assert resolved == "杨凯2025年的日报记录有哪些"


def test_lead_agent_context_dispatches_selected_manifest(db_session, sample_dataset):
    """未显式选数据集时，LeadAgent 应通过 Manifest 路由生成 SubAgent 调度上下文。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    context = build_lead_agent_context(
        db_session,
        question="最近30日GMV趋势如何",
        now=datetime(2026, 6, 12, 9, 30),
    )

    assert context["should_continue"] is True
    assert context["route_decision"]["decision"] == "selected"
    assert context["effective_dataset_id"] == sample_dataset.id
    assert context["dispatch"]["dataset_id"] == sample_dataset.id
    assert context["schema_status"]["status"] == "ok"
    assert context["audit_trace"]["dispatched"] is True
    assert context["tool_policy"]["allowed_tools"]
    assert context["planned_tool_calls"]
    assert context["executed_tool_calls"]
    assert context["resolved_question"]
    assert "system_inferred_tool_calls" in context


def test_lead_agent_multiturn_continue_reuses_active_dataset(db_session, sample_dataset):
    """多轮续问应复用 LeadAgent active_dataset_id，并把继承摘要放入 SubAgent capsule。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    context = build_lead_agent_context(
        db_session,
        question="那按地区拆分一下",
        now=datetime(2026, 6, 12, 9, 30),
        multiturn_context={
            "active_dataset_id": sample_dataset.id,
            "inheritance_summary": "上一轮查询了最近30日GMV趋势。",
        },
    )

    assert context["multiturn_classification"]["intent"] == "continue"
    assert context["multiturn_classification"]["should_inherit_dataset"] is True
    assert context["tool_policy"]["dataset_lock_source"] == "multiturn_active"
    assert context["route_decision"]["decision"] == "locked"
    assert context["effective_dataset_id"] == sample_dataset.id
    assert context["dispatch"]["capsule"]["inheritance_summary"] == "上一轮查询了最近30日GMV趋势。"
    assert context["dispatch"]["capsule"]["multiturn_intent"] == "continue"


def test_lead_agent_multiturn_active_dataset_overrides_legacy_conversation_lock(
    db_session,
    sample_dataset,
):
    """开启多轮续问时，ConversationStore 的 active_dataset_id 优先于旧 conversation.dataset_id。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())
    conversation = models.Conversation(
        id=456,
        title="旧会话锁",
        thread_id="thread-legacy-lock",
        dataset_id=999,
    )

    context = build_lead_agent_context(
        db_session,
        question="那按地区拆分一下",
        conversation=conversation,
        now=datetime(2026, 6, 12, 9, 30),
        multiturn_context={
            "active_dataset_id": sample_dataset.id,
            "inheritance_summary": "上一轮查询了最近30日GMV趋势。",
        },
    )

    assert context["multiturn_classification"]["should_inherit_dataset"] is True
    assert context["tool_policy"]["dataset_lock_source"] == "multiturn_active"
    assert context["thread_context"]["locked_dataset_id"] == sample_dataset.id
    assert context["route_decision"]["decision"] == "locked"
    assert context["effective_dataset_id"] == sample_dataset.id


def test_lead_agent_multiturn_time_inherits_prior_range(db_session, sample_dataset):
    """相对时间续问应基于上一轮 resolved_time_context 推导。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    context = build_lead_agent_context(
        db_session,
        question="再看上个月",
        now=datetime(2026, 6, 12, 9, 30),
        multiturn_context={
            "active_dataset_id": sample_dataset.id,
            "inheritance_summary": "上一轮查询了2026年5月GMV。",
            "resolved_time_context": {
                "detected_time_range": {
                    "label": "2026年5月",
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-31",
                    "granularity": "month",
                    "source": "explicit_month",
                }
            },
        },
    )

    detected = context["time_context"]["detected_time_range"]
    assert detected["source"] == "prior_relative_last_month"
    assert detected["start_date"] == "2026-04-01"
    assert detected["end_date"] == "2026-04-30"
    assert context["time_context"]["inherited_from_prior_time"] is True
    assert context["resolved_question"] == "再看2026年4月"


def test_lead_agent_multiturn_switch_does_not_reuse_active_dataset(db_session, sample_dataset):
    """切换意图不能把旧 active_dataset_id 强行继承到本轮路由。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    context = build_lead_agent_context(
        db_session,
        question="切换到库存数据集看周转率",
        now=datetime(2026, 6, 12, 9, 30),
        multiturn_context={
            "active_dataset_id": sample_dataset.id,
            "inheritance_summary": "上一轮是销售运营数据集。",
        },
    )

    assert context["multiturn_classification"]["intent"] == "switch"
    assert context["multiturn_classification"]["should_inherit_dataset"] is False
    assert context["tool_policy"]["dataset_lock_source"] == "none"
    assert context["route_decision"]["decision"] == "no_match"
    assert context["dispatch"] is None
    assert context["should_continue"] is False


def test_lead_agent_multiturn_interpret_reuses_active_dataset(db_session, sample_dataset):
    """解释上一轮结果时应沿用 active_dataset_id，并标记 interpret intent。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    context = build_lead_agent_context(
        db_session,
        question="上面这个结果是什么意思",
        now=datetime(2026, 6, 12, 9, 30),
        multiturn_context={
            "active_dataset_id": sample_dataset.id,
            "inheritance_summary": "上一轮返回了GMV趋势和区域拆分。",
        },
    )

    assert context["multiturn_classification"]["intent"] == "interpret"
    assert context["route_decision"]["decision"] == "locked"
    assert context["dispatch"]["dataset_id"] == sample_dataset.id
    assert context["dispatch"]["capsule"]["multiturn_intent"] == "interpret"
    assert context["dispatch"]["capsule"]["execution_mode"] == "interpret_result"
    assert context["dispatch"]["capsule"]["should_generate_query"] is False
    assert context["dispatch"]["capsule"]["interpretation_source"] == "prior_capsule.result_digest"


def test_lead_agent_multiturn_chitchat_does_not_dispatch(db_session, sample_dataset):
    """闲聊轮次即使有 active_dataset_id，也不能误调度 SubAgent。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    context = build_lead_agent_context(
        db_session,
        question="谢谢",
        now=datetime(2026, 6, 12, 9, 30),
        multiturn_context={
            "active_dataset_id": sample_dataset.id,
            "inheritance_summary": "上一轮是销售问数。",
        },
    )

    assert context["multiturn_classification"]["intent"] == "chitchat"
    assert context["route_decision"]["decision"] == "chitchat"
    assert context["clarification"]["kind"] == "chitchat"
    assert context["dispatch"] is None
    assert context["should_continue"] is False
    assert context["effective_dataset_id"] is None


def test_lead_agent_blocks_when_no_current_manifest(db_session):
    """没有 current Manifest 且未显式选数据集时，LeadAgent 应生成数据集级澄清。"""

    context = build_lead_agent_context(
        db_session,
        question="最近30日GMV趋势如何",
        now=datetime(2026, 6, 12, 9, 30),
    )

    assert context["should_continue"] is False
    assert context["route_decision"]["decision"] == "no_match"
    assert context["clarification"]["kind"] == "dataset_missing"
    assert context["audit_trace"]["dispatched"] is False


def test_schema_status_marks_current_manifest_needs_review(db_session, sample_dataset):
    """schema hash 变化后，LeadAgent SchemaStatusTool 应标记 current Manifest 需 review。"""

    manifest = publish_manifest(db_session, sample_dataset.id, _manual_fields())
    db_session.add(
        models.SemanticMetric(
            dataset_id=sample_dataset.id,
            name="refund_amount",
            display_name="退款金额",
            expr="SUM(o.refund_amount)",
            description="订单退款金额",
        )
    )
    db_session.commit()

    context = build_lead_agent_context(
        db_session,
        question="最近30日GMV趋势如何",
        now=datetime(2026, 6, 12, 9, 30),
    )

    assert context["schema_status"]["status"] == "needs_review"
    refreshed = db_session.get(
        models.DatasetSubAgentManifest,
        (manifest.dataset_id, manifest.manifest_version),
    )
    assert refreshed.review_status == "needs_review"


def test_tool_policy_locks_explicit_dataset(sample_dataset):
    """显式选择数据集时，ToolPolicy 应记录锁定边界，禁止自动改选。"""

    conversation = models.Conversation(
        id=123,
        title="显式锁定",
        thread_id="thread-explicit-lock",
        dataset_id=None,
    )
    policy = build_tool_policy(
        conversation=conversation,
        payload_dataset_id=sample_dataset.id,
    )

    assert policy["explicit_dataset_locked"] is True
    assert policy["locked_dataset_id"] == sample_dataset.id
    assert "metric_resolution" in policy["blocked_tools"]
    assert "subagent_dispatch" in policy["allowed_tools"]


def test_planner_illegal_tool_is_blocked(monkeypatch, db_session, sample_dataset):
    """LLM Planner 计划非法工具时，ToolExecutor 不执行并记录 policy_violation。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    def fake_plan(*_args, **_kwargs):
        return {
            "reasoning_summary": "测试非法工具拦截",
            "selected_skills": ["DatasetRoutingSkill"],
            "tool_calls": [
                {"tool": "thread_context", "reason": "读取会话"},
                {"tool": "metric_resolution", "reason": "非法访问指标"},
                {"tool": "manifest_router", "reason": "路由数据集"},
                {"tool": "schema_status", "reason": "检查 schema"},
                {"tool": "subagent_dispatch", "reason": "调度 SubAgent"},
            ],
            "planner_fallback": False,
            "fallback_reason": None,
        }

    monkeypatch.setattr("app.services.lead_agent.plan_tool_calls_with_llm", fake_plan)

    context = build_lead_agent_context(
        db_session,
        question="最近30日GMV趋势如何",
        now=datetime(2026, 6, 12, 9, 30),
    )

    assert context["should_continue"] is True
    assert "metric_resolution" not in [item["tool"] for item in context["executed_tool_calls"]]
    assert {
        item["tool"]
        for item in context["policy_violations"]
        if item["reason"] == "tool_not_allowed_by_policy"
    } == {"metric_resolution"}


def test_incomplete_planner_plan_uses_fallback(monkeypatch, db_session, sample_dataset):
    """LLM Planner 输出不完整计划时，应启用安全降级计划。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    def fake_plan(*_args, **_kwargs):
        return {
            "reasoning_summary": "遗漏关键路由工具",
            "selected_skills": ["TimeUnderstandingSkill"],
            "tool_calls": [{"tool": "time", "reason": "只解析时间"}],
            "planner_fallback": False,
            "fallback_reason": None,
        }

    monkeypatch.setattr("app.services.lead_agent.plan_tool_calls_with_llm", fake_plan)

    context = build_lead_agent_context(
        db_session,
        question="最近30日GMV趋势如何",
        now=datetime(2026, 6, 12, 9, 30),
    )

    assert context["planner_fallback"] is True
    assert context["fallback_reason"] == "planner_incomplete_execution"
    assert context["should_continue"] is True
    assert context["route_decision"]["decision"] == "selected"


def test_tool_planner_fast_path_skips_llm_for_locked_detail_query(monkeypatch, db_session, sample_dataset):
    """锁定数据集的新明细查询应直接走确定性工具计划，不再调用两次 LLM。"""

    def fail_get_llm(*_args, **_kwargs):
        raise AssertionError("fast path should not call lead agent LLM")

    monkeypatch.setattr("app.services.lead_agent.get_llm", fail_get_llm)

    plan = plan_tool_calls_with_llm(
        db_session,
        question="查询10条用户日志",
        conversation_summary={
            "multiturn_classification": {
                "intent": "new_query",
                "should_inherit_dataset": False,
            }
        },
        tool_policy={
            "allowed_tools": [
                "thread_context",
                "manifest_router",
                "schema_status",
                "subagent_dispatch",
                "audit_trace",
            ],
            "blocked_tools": ["metric_resolution"],
            "locked_dataset_id": sample_dataset.id,
            "dataset_lock_source": "payload",
        },
        skills=[],
    )

    assert plan["planner_source"] == "deterministic"
    assert plan["fast_path_hit"] is True
    assert plan["llm_skipped_reason"] == "locked_dataset_self_contained_query"
    assert [item["tool"] for item in plan["tool_calls"]] == [
        "thread_context",
        "manifest_router",
        "schema_status",
        "subagent_dispatch",
        "audit_trace",
    ]


def test_tool_planner_fast_path_avoids_multiturn_continue(monkeypatch, db_session, sample_dataset):
    """多轮续问需要保留 LLM/兜底判断，不能被锁定数据集快路径误服务。"""

    monkeypatch.setattr(
        "app.services.lead_agent._lead_agent_llm_available",
        lambda _db: {"available": False, "reason": "lead_agent_llm_not_configured"},
    )

    plan = plan_tool_calls_with_llm(
        db_session,
        question="那按部门拆一下",
        conversation_summary={
            "multiturn_classification": {
                "intent": "continue",
                "should_inherit_dataset": True,
            }
        },
        tool_policy={
            "allowed_tools": ["thread_context", "manifest_router", "schema_status", "subagent_dispatch"],
            "locked_dataset_id": sample_dataset.id,
            "dataset_lock_source": "multiturn_active",
        },
        skills=[],
    )

    assert plan.get("fast_path_hit") is not True
    assert plan["planner_fallback"] is True
    assert plan["fallback_reason"] == "lead_agent_llm_not_configured"


def test_planner_records_langfuse_generation(monkeypatch, db_session):
    """LeadAgent Planner 应按 Skill -> Tool 两阶段渐进式披露并记录 generation。"""

    class FakePrompt:
        content = "planner prompt"
        version = "v-test"
        source = "local"

    class FakePromptManager:
        def get_text_prompt(self, *_args, **_kwargs):
            return FakePrompt()

    class FakeLLM:
        model = "lead-model"

        def __init__(self):
            self.calls = 0

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                return type(
                    "Response",
                    (),
                    {
                        "content": (
                            '{"reasoning_summary":"先选择路由能力",'
                            '"selected_skills":["ConversationContinuitySkill","DatasetRoutingSkill"]}'
                        ),
                        "usage_metadata": {
                            "input_tokens": 8,
                            "output_tokens": 4,
                            "total_tokens": 12,
                        },
                    },
                )()
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"reasoning_summary":"规划控制面工具","selected_skills":["DatasetRoutingSkill"],'
                        '"tool_calls":[{"tool":"thread_context","reason":"ctx"},'
                        '{"tool":"manifest_router","reason":"route"}]}'
                    ),
                    "usage_metadata": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                    },
                },
            )()

    class FakeTracer:
        def __init__(self):
            self.started = []
            self.ended = []

        def start_generation(self, **kwargs):
            self.started.append(kwargs)
            return object()

        def end_generation(self, handle, **kwargs):
            self.ended.append({"handle": handle, **kwargs})

    monkeypatch.setattr(
        "app.services.lead_agent._lead_agent_llm_available",
        lambda _db: {"available": True, "reason": None},
    )
    monkeypatch.setattr("app.services.lead_agent.get_prompt_manager", lambda: FakePromptManager())
    fake_llm = FakeLLM()
    monkeypatch.setattr("app.services.lead_agent.get_llm", lambda **_kwargs: fake_llm)

    tracer = FakeTracer()
    plan = plan_tool_calls_with_llm(
        db_session,
        question="最近30日GMV趋势如何",
        conversation_summary={},
        tool_policy={
            "allowed_tools": ["thread_context", "manifest_router"],
            "blocked_tools": ["metric_resolution"],
        },
        skills=[
            {
                "name": "ConversationContinuitySkill",
                "purpose": "会话上下文",
                "allowed_tools": ["thread_context"],
            },
            {
                "name": "DatasetRoutingSkill",
                "purpose": "路由数据集",
                "allowed_tools": ["manifest_router", "clarification"],
            },
        ],
        tracer=tracer,
        trace_context=object(),
    )

    assert plan["planner_fallback"] is False
    assert plan["progressive_disclosure"] is True
    assert plan["disclosed_tools"] == ["thread_context", "manifest_router"]
    assert tracer.started[0]["name"] == "llm.lead_agent_skill_selector"
    assert tracer.started[0]["metadata"]["prompt_name"] == "lead_agent_skill_selector"
    skill_input = json.loads(tracer.started[0]["messages"][1].content)
    assert "tool_schemas" not in skill_input
    assert tracer.started[1]["name"] == "llm.lead_agent_tool_planner"
    assert tracer.started[1]["metadata"]["prompt_name"] == "lead_agent_tool_planner"
    tool_input = json.loads(tracer.started[1]["messages"][1].content)
    assert [item["name"] for item in tool_input["tool_schemas"]] == [
        "thread_context",
        "manifest_router",
    ]
    assert "metric_resolution" not in json.dumps(tool_input["tool_schemas"], ensure_ascii=False)
    assert tracer.ended[0]["usage"]["total_tokens"] == 12
    assert tracer.ended[1]["usage"]["total_tokens"] == 15
    assert tracer.ended[1]["metadata"]["normalized_plan"]["tool_calls"]


def test_lead_agent_records_complete_control_plane_span(db_session, sample_dataset):
    """LeadAgent 应把最终控制面结果写入 Trace span，便于查看完整回复。"""

    publish_manifest(db_session, sample_dataset.id, _manual_fields())

    class FakeTracer:
        def __init__(self):
            self.spans_started = []
            self.spans_ended = []

        def start_span(self, context, **kwargs):
            self.spans_started.append({"context": context, **kwargs})

        def end_span(self, context, **kwargs):
            self.spans_ended.append({"context": context, **kwargs})

    tracer = FakeTracer()
    context = build_lead_agent_context(
        db_session,
        question="最近30日GMV趋势如何",
        now=datetime(2026, 6, 12, 9, 30),
        tracer=tracer,
        trace_context=object(),
    )

    assert tracer.spans_started[0]["node"] == "lead_agent_control_plane"
    output = tracer.spans_ended[0]["output_payload"]
    assert output["original_question"] == "最近30日GMV趋势如何"
    assert output["resolved_question"] == context["resolved_question"]
    assert output["planned_tool_calls"]
    assert output["executed_tool_calls"]
    assert "system_inferred_tool_calls" in output
    assert "policy_violations" in output


def test_planner_logs_prompt_and_response(monkeypatch, db_session, caplog):
    """LeadAgent Planner 的两阶段 LLM 调用应分别记录请求和返回摘要。"""

    class FakePrompt:
        content = "planner prompt"
        version = "v-test"
        source = "local"

    class FakePromptManager:
        def get_text_prompt(self, *_args, **_kwargs):
            return FakePrompt()

    class FakeLLM:
        model = "lead-model"

        def invoke(self, _messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"reasoning_summary":"ok",'
                        '"selected_skills":["DatasetRoutingSkill"],'
                        '"tool_calls":[{"tool":"manifest_router","reason":"r"}]}'
                    ),
                    "usage_metadata": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
                },
            )()

    monkeypatch.setattr(
        "app.services.lead_agent._lead_agent_llm_available",
        lambda _db: {"available": True, "reason": None},
    )
    monkeypatch.setattr("app.services.lead_agent.get_prompt_manager", lambda: FakePromptManager())
    monkeypatch.setattr("app.services.lead_agent.get_llm", lambda **_kwargs: FakeLLM())

    import logging

    with caplog.at_level(logging.INFO, logger="app.services.lead_agent"):
        plan_tool_calls_with_llm(
            db_session,
            question="查一下华东最近30天GMV",
            conversation_summary={},
            tool_policy={"allowed_tools": ["manifest_router"], "locked_dataset_id": 7},
            skills=[{"name": "DatasetRoutingSkill", "description": "路由数据集"}],
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("stage=skill_selector" in m for m in messages)
    assert any("stage=tool_planner" in m for m in messages)
    assert any("parse_ok=True" in m for m in messages)


def test_merge_multiturn_decision_uses_query_task_capsule_prior_context():
    """LeadAgent merge wrapper 应把 state 中的 query_task_capsule 交给 builder 兜底承接。"""
    decision = merge_multiturn_decision_for_chat(
        state={
            "question": "只看汤杰",
            "turn_type": "continue",
            "dataset_id": 10,
            "prior_capsule": {},
            "query_task_capsule": {
                "turn_type": "followup_refine",
                "dataset_id": 10,
                "base_task_ref": "last_success_task",
                "base_question": "查询10条用户日志",
                "standalone_question": "基于上一轮问题「查询10条用户日志」，只看汤杰",
                "base_main_table": "plan_task_daily_record",
                "base_query_plan": {
                    "query_type": "detail_query",
                    "select_fields": ["rzrq", "person_name"],
                },
            },
        }
    )

    assert decision.turn_type == "continue"
    merged = decision.multiturn_context["merged_query_context"]
    assert merged["main_table"] == "plan_task_daily_record"
    assert merged["query_plan"]["query_type"] == "detail_query"
