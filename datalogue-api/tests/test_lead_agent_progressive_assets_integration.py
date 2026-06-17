# ============================================================
# File Name   : test_lead_agent_progressive_assets_integration.py
# Description:
#   LeadAgent 渐进式语义资产注入的端到端集成测试。
#
# Responsibilities:
#   - 验证 plan_tool_calls_with_llm 在开关开启且已锁定数据集时，
#     能把候选资产注入 skill_input / planner_input。
#   - 验证开关关闭或召回失败时，candidate_assets 降级为空资产，
#     不影响主链路返回工具计划。
#   - 验证 tracer metadata 中记录了候选资产观测字段。
#
# Author      : yangkai
# Created On  : 2026-06-17
# ============================================================

import json

from app.core.config import Settings
from app.prompts.lead_agent import (
    LEAD_AGENT_SKILL_SELECTOR_SYSTEM,
    LEAD_AGENT_TOOL_PLANNER_SYSTEM,
)
from app.services.lead_agent import plan_tool_calls_with_llm


class _FakePrompt:
    content = "planner prompt"
    version = "v-test"
    source = "local"


class _FakePromptManager:
    def get_text_prompt(self, *_args, **_kwargs):
        return _FakePrompt()


class _FakeLLM:
    model = "lead-model"

    def __init__(self):
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        if self.calls == 1:
            return _make_response(
                '{"reasoning_summary":"选择路由技能",' '"selected_skills":["DatasetRoutingSkill"]}',
                total_tokens=9,
            )
        return _make_response(
            '{"reasoning_summary":"规划控制面工具",'
            '"selected_skills":["DatasetRoutingSkill"],'
            '"tool_calls":[{"tool":"manifest_router","reason":"路由到锁定数据集"}]}',
            total_tokens=11,
        )


def _make_response(content: str, total_tokens: int):
    return type(
        "Response",
        (),
        {"content": content, "usage_metadata": {"total_tokens": total_tokens}},
    )()


class _FakeTracer:
    def __init__(self):
        self.started = []
        self.ended = []

    def start_generation(self, **kwargs):
        self.started.append(kwargs)
        return object()

    def end_generation(self, handle, **kwargs):
        self.ended.append({"handle": handle, **kwargs})


def _enabled_settings():
    """返回开启渐进式资产注入的 Settings 实例（其余字段使用默认值）。"""
    return Settings(
        LEAD_AGENT_USE_PROGRESSIVE_ASSETS=True,
        LEAD_AGENT_PLANNER_USE_PROJECTION=False,
    )


def _disabled_settings():
    """返回关闭渐进式资产注入的 Settings 实例。"""
    return Settings(
        LEAD_AGENT_USE_PROGRESSIVE_ASSETS=False,
        LEAD_AGENT_PLANNER_USE_PROJECTION=False,
    )


def _patch_common_dependencies(monkeypatch, db_session, settings):
    """统一 monkeypatch 掉 LLM、PromptManager、配置和可用性检查。"""

    monkeypatch.setattr(
        "app.services.lead_agent._lead_agent_llm_available",
        lambda _db: {"available": True, "reason": None},
    )
    monkeypatch.setattr("app.services.lead_agent.get_prompt_manager", lambda: _FakePromptManager())
    fake_llm = _FakeLLM()
    monkeypatch.setattr("app.services.lead_agent.get_llm", lambda **_kwargs: fake_llm)
    monkeypatch.setattr("app.services.lead_agent.get_settings", lambda: settings)


def _call_planner(db_session, sample_dataset, settings):
    """构造默认输入并调用 plan_tool_calls_with_llm。"""

    tracer = _FakeTracer()
    plan = plan_tool_calls_with_llm(
        db_session,
        question="按地区看一下 GMV",
        conversation_summary={
            "multiturn_classification": {
                "intent": "continue",
                "should_inherit_dataset": True,
            },
            "multiturn_context": {
                "inheritance_summary": "上一轮查询了整体 GMV。",
            },
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
            "dataset_lock_source": "multiturn_active",
            "explicit_dataset_locked": False,
            "inherited_dataset_locked": True,
        },
        skills=[
            {
                "name": "ConversationContinuitySkill",
                "purpose": "处理会话上下文",
                "allowed_tools": ["thread_context"],
            },
            {
                "name": "DatasetRoutingSkill",
                "purpose": "路由数据集",
                "allowed_tools": ["manifest_router"],
            },
        ],
        tracer=tracer,
        trace_context=object(),
    )
    return plan, tracer


def test_progressive_assets_injected_when_enabled_and_dataset_locked(
    monkeypatch, db_session, sample_dataset
):
    """开关开启且锁定数据集时，skill_input / planner_input 都应携带候选资产。"""

    settings = _enabled_settings()
    _patch_common_dependencies(monkeypatch, db_session, settings)

    plan, tracer = _call_planner(db_session, sample_dataset, settings)

    assert plan["planner_fallback"] is False
    assert plan["tool_calls"]

    skill_payload = json.loads(tracer.started[0]["messages"][1].content)
    assert skill_payload["candidate_assets"]["assets"]
    assert skill_payload["candidate_assets"]["summary"]["total"] > 0
    assert skill_payload["candidate_assets"]["stage"] == "skill_selection"

    tool_payload = json.loads(tracer.started[1]["messages"][1].content)
    assert tool_payload["candidate_assets"]["assets"]
    assert tool_payload["candidate_assets"]["summary"]["total"] > 0
    assert tool_payload["candidate_assets"]["stage"] == "tool_planning"

    skill_meta = tracer.started[0]["metadata"]
    assert skill_meta["candidate_asset_recall_called"] is True
    assert skill_meta["candidate_asset_count"] == len(skill_payload["candidate_assets"]["assets"])
    assert "counts_by_type" in skill_meta["candidate_asset_summary"]

    tool_meta = tracer.started[1]["metadata"]
    assert tool_meta["candidate_asset_recall_called"] is True
    assert tool_meta["candidate_asset_count"] == len(tool_payload["candidate_assets"]["assets"])


def test_progressive_assets_empty_when_disabled(monkeypatch, db_session, sample_dataset):
    """总开关关闭时，candidate_assets 降级为空资产，主链路仍正常返回计划。"""

    settings = _disabled_settings()
    _patch_common_dependencies(monkeypatch, db_session, settings)

    plan, tracer = _call_planner(db_session, sample_dataset, settings)

    assert plan["planner_fallback"] is False

    skill_payload = json.loads(tracer.started[0]["messages"][1].content)
    assert skill_payload["candidate_assets"]["assets"] == []
    assert skill_payload["candidate_assets"]["summary"] == {}

    tool_payload = json.loads(tracer.started[1]["messages"][1].content)
    assert tool_payload["candidate_assets"]["assets"] == []
    assert tool_payload["candidate_assets"]["summary"] == {}

    skill_meta = tracer.started[0]["metadata"]
    assert skill_meta["candidate_asset_recall_called"] is False
    assert skill_meta["candidate_asset_count"] == 0


def test_progressive_assets_empty_when_recall_fails(monkeypatch, db_session, sample_dataset):
    """召回层抛异常时，应降级为空资产且不影响主链路。"""

    settings = _enabled_settings()
    _patch_common_dependencies(monkeypatch, db_session, settings)

    def _failing_recall(*_args, **_kwargs):
        raise RuntimeError("模拟召回失败")

    monkeypatch.setattr(
        "app.services.lead_agent.recall_candidate_assets",
        _failing_recall,
    )

    plan, tracer = _call_planner(db_session, sample_dataset, settings)

    assert plan["planner_fallback"] is False

    skill_payload = json.loads(tracer.started[0]["messages"][1].content)
    assert skill_payload["candidate_assets"]["assets"] == []

    tool_payload = json.loads(tracer.started[1]["messages"][1].content)
    assert tool_payload["candidate_assets"]["assets"] == []

    # 虽然召回失败了，但仍然标记为“已尝试召回”，便于观测降级事件。
    skill_meta = tracer.started[0]["metadata"]
    assert skill_meta["candidate_asset_recall_called"] is True
    assert skill_meta["candidate_asset_count"] == 0


def test_skill_selector_prompt_mentions_candidate_assets():
    """Skill Selector 的 system prompt 必须说明 candidate_assets 字段及使用规则。"""
    assert "candidate_assets" in LEAD_AGENT_SKILL_SELECTOR_SYSTEM
    assert "asset_type" in LEAD_AGENT_SKILL_SELECTOR_SYSTEM
    assert "confidence" in LEAD_AGENT_SKILL_SELECTOR_SYSTEM
    assert "blueprint" in LEAD_AGENT_SKILL_SELECTOR_SYSTEM


def test_tool_planner_prompt_mentions_candidate_assets():
    """Tool Planner 的 system prompt 必须说明 candidate_assets 字段及使用规则。"""
    assert "candidate_assets" in LEAD_AGENT_TOOL_PLANNER_SYSTEM
    assert "asset_type" in LEAD_AGENT_TOOL_PLANNER_SYSTEM
    assert "confidence" in LEAD_AGENT_TOOL_PLANNER_SYSTEM
    assert "subagent_dispatch" in LEAD_AGENT_TOOL_PLANNER_SYSTEM
