from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from app.core.config import Settings
from app.services.lead_agent import available_lead_skills, build_tool_policy
from app.services.lead_agent_planner_projection import (
    PROJECTION_SCHEMA_VERSION,
    SkillBrief,
    build_projection_metrics,
    build_skill_selector_input,
    build_tool_planner_input,
    project_tools_for_planner,
    project_skills_for_selector,
)


@dataclass(frozen=True)
class DataclassSkill:
    name: str
    description: str


def test_projection_feature_flag_defaults_off():
    assert Settings.model_fields["LEAD_AGENT_PLANNER_USE_PROJECTION"].default is False


def test_projection_recent_context_uses_configured_prior_turn_limit(monkeypatch):
    monkeypatch.setattr(
        "app.services.lead_agent_planner_projection.get_settings",
        lambda: SimpleNamespace(LEAD_AGENT_PLANNER_PROJECTION_MAX_PRIOR_TURNS=1),
    )

    projected = build_skill_selector_input(
        question="查询日志",
        candidate_skills=[],
        recent_context={
            "prior_turns": [
                {"question": "第一轮", "row_count": 1},
                {"question": "第二轮", "row_count": 2},
            ]
        },
    )

    assert projected["recent_context"]["prior_turns"] == [{"question": "第二轮", "row_count": 2}]


def test_project_skills_for_selector_keeps_only_stable_fields():
    projected = project_skills_for_selector(
        [
            {
                "name": "query_dataset",
                "description": "查询数据集",
                "parameters": {
                    "question": {
                        "type": "string",
                        "description": "用户问题",
                        "examples": ["很长的样例不会进入投影"],
                    }
                },
                "raw_context": "不应泄露",
            },
            DataclassSkill(name="clarify", description="澄清问题"),
            "invalid",
        ]
    )

    assert projected == [
        {
            "name": "query_dataset",
            "description": "查询数据集",
            "parameters": {"question": {"type": "string", "description": "用户问题"}},
        },
        {"name": "clarify", "description": "澄清问题", "parameters": {}},
    ]


def test_project_skills_for_selector_preserves_real_lead_skill_purpose():
    skills = available_lead_skills(build_tool_policy(payload_dataset_id=10))

    projected = project_skills_for_selector(skills)

    assert projected
    assert all(item["description"] for item in projected)
    assert {item["name"]: item["description"] for item in projected}[
        "ConversationContinuitySkill"
    ] == "处理会话上下文和显式数据集锁定。"


def test_project_skills_for_selector_rejects_non_collection_inputs():
    assert project_skills_for_selector("query_dataset") == []
    assert project_skills_for_selector({"name": "query_dataset"}) == []
    assert project_skills_for_selector(None) == []


def test_skill_selector_input_projects_context_without_raw_payload():
    projected = build_skill_selector_input(
        question="统计上个月各区域合同额",
        candidate_skills=[SkillBrief(name="query_dataset", description="查询数据集")],
        recent_context={
            "dataset_id": 10,
            "routing_path": "dataset_subagent",
            "raw_schema": "不应进入投影",
            "turn_policy": {
                "intent": "continue",
                "should_inherit_dataset": True,
                "dataset_lock_source": "multiturn_active",
                "explicit_dataset_locked": False,
                "inherited_dataset_locked": True,
                "allowed_tools": ["不应进入投影"],
            },
            "prior_turns": [
                {"question": "先看整体", "routing_path": "dataset_subagent", "row_count": 8},
                {"resolved_question": "再按区域拆分", "result_summary": {"row_count": 3}},
            ],
        },
    )

    assert projected["projection_schema_version"] == PROJECTION_SCHEMA_VERSION
    assert projected["question"] == "统计上个月各区域合同额"
    assert projected["candidate_skills"][0]["name"] == "query_dataset"
    assert projected["recent_context"] == {
        "dataset_id": 10,
        "routing_path": "dataset_subagent",
        "turn_policy": {
            "intent": "continue",
            "dataset_lock_source": "multiturn_active",
            "should_inherit_dataset": True,
            "explicit_dataset_locked": False,
            "inherited_dataset_locked": True,
        },
        "prior_turns": [
            {"question": "先看整体", "routing_path": "dataset_subagent", "row_count": 8},
            {"question": "再按区域拆分", "row_count": 3},
        ],
    }
    assert "raw_schema" not in projected["recent_context"]
    assert "allowed_tools" not in projected["recent_context"]["turn_policy"]


def test_tool_planner_input_projects_selected_skill_and_tools():
    projected = build_tool_planner_input(
        question="按部门汇总销售额",
        selected_skills=["query_dataset"],
        candidate_tools=[
            {
                "name": "run_dataset_query",
                "purpose": "生成并执行 SQL",
                "inputs": ["question", "route_decision"],
                "raw_schema": "不应泄露",
            }
        ],
        recent_context={"dataset_id": 11, "history": [{"user_query": "先看销售额"}]},
    )

    assert projected["projection_schema_version"] == PROJECTION_SCHEMA_VERSION
    assert projected["selected_skills"] == ["query_dataset"]
    assert projected["candidate_tools"] == [
        {
            "name": "run_dataset_query",
            "description": "生成并执行 SQL",
            "inputs": ["question", "route_decision"],
        }
    ]
    assert projected["recent_context"] == {
        "dataset_id": 11,
        "prior_turns": [{"question": "先看销售额"}],
    }
    assert "raw_schema" not in projected["candidate_tools"][0]


def test_project_tools_for_planner_preserves_real_tool_schema_shape():
    projected = project_tools_for_planner(
        [
            {"name": "time", "purpose": "解析用户问题中的时间线索。", "inputs": ["question"]},
            {
                "name": "subagent_dispatch",
                "purpose": "数据集明确后生成 SubAgent 调度上下文。",
                "inputs": ["route_decision", "time_context", "thread_context", "schema_status"],
            },
            {
                "tool": "audit_trace",
                "description": "记录 LeadAgent 工具规划和执行摘要。",
                "inputs": [],
            },
        ]
    )

    assert projected == [
        {"name": "time", "description": "解析用户问题中的时间线索。", "inputs": ["question"]},
        {
            "name": "subagent_dispatch",
            "description": "数据集明确后生成 SubAgent 调度上下文。",
            "inputs": ["route_decision", "time_context", "thread_context", "schema_status"],
        },
        {"name": "audit_trace", "description": "记录 LeadAgent 工具规划和执行摘要。", "inputs": []},
    ]


def test_recent_context_limits_prior_turns_to_latest_three():
    projected = build_skill_selector_input(
        question="继续",
        candidate_skills=[],
        recent_context={
            "prior_turns": [
                {"question": "第一轮"},
                {"question": "第二轮"},
                {"question": "第三轮"},
                {"question": "第四轮"},
            ]
        },
    )

    assert projected["recent_context"]["prior_turns"] == [
        {"question": "第二轮"},
        {"question": "第三轮"},
        {"question": "第四轮"},
    ]


def test_long_prior_turn_question_keeps_route_and_row_count():
    projected = build_skill_selector_input(
        question="继续",
        candidate_skills=[],
        recent_context={
            "prior_turns": [
                {
                    "resolved_question": "很长" * 300,
                    "routing_path": "blueprint",
                    "row_count": 12,
                }
            ]
        },
    )

    brief = projected["recent_context"]["prior_turns"][0]
    assert brief["question"].endswith("…")
    assert brief["routing_path"] == "blueprint"
    assert brief["row_count"] == 12


def test_build_prior_turn_brief_preserves_inheritance_summary():
    projected = build_skill_selector_input(
        question="继续",
        candidate_skills=[],
        recent_context={
            "prior_turns": [
                {
                    "question": "华东上月 GMV 是多少",
                    "routing_path": "dataset_subagent",
                    "inheritance_summary": "上一轮查询了华东上月 GMV",
                    "row_count": 1,
                }
            ]
        },
    )

    brief = projected["recent_context"]["prior_turns"][0]
    assert brief["question"] == "华东上月 GMV 是多少"
    assert brief["routing_path"] == "dataset_subagent"
    assert brief["inheritance_summary"] == "上一轮查询了华东上月 GMV"
    assert brief["row_count"] == 1


def test_project_skills_for_selector_empty_parameters_not_fallback_to_args_schema():
    projected = project_skills_for_selector(
        [
            {
                "name": "no_param_skill",
                "description": "无参 skill",
                "parameters": {},
                "args_schema": {"question": {"type": "string", "description": "问题"}},
            }
        ]
    )

    assert projected == [{"name": "no_param_skill", "description": "无参 skill", "parameters": {}}]


def test_project_recent_context_empty_prior_turns_not_fallback_to_history():
    projected = build_skill_selector_input(
        question="继续",
        candidate_skills=[],
        recent_context={
            "prior_turns": [],
            "history": [{"question": "不应被选中"}],
        },
    )

    assert projected["recent_context"]["prior_turns"] == []


def test_json_chars_handles_circular_reference_without_crashing():
    raw: dict[str, Any] = {}
    raw["self"] = raw

    metrics = build_projection_metrics(raw_payload=raw, projected_payload={})

    assert metrics["raw_chars"] > 0
    assert metrics["projected_chars"] == len("{}")
