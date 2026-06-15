# ============================================================
# File Name   : test_query_plan_prompting.py
# Description:
#   验证 QueryGraph DSL 生成提示词会携带查询规划和参考蓝图上下文。
#
# Responsibilities:
#   - 覆盖四条 DSL prompt 构造路径的 query_plan 注入。
#   - 覆盖 blueprint_as_reference 场景下蓝图只能参考、不能原样执行的提示词约束。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

import pytest


REFERENCE_BLUEPRINT = "【参考蓝图（非直接执行）】\n不能原样执行\nselect * from daily_report"
QUERY_PLAN = {
    "query_type": "detail_query",
    "execution_strategy": "blueprint_as_reference",
    "explanation": {"summary": "蓝图仅参考"},
}


class _FakeLLMResponse:
    """记录 DSL 节点发给 LLM 的 messages，并返回指定 JSON。"""

    def __init__(self, content='{"sql": "select id from user_logs limit 10"}'):
        self.messages = None
        self.content = content
        self.usage_metadata = None

    def invoke(self, messages):
        self.messages = messages
        return self


def _base_state(**overrides):
    state = {
        "question": "查询10条用户日志",
        "query_constraints": {"enabled": False},
        "multiturn_context": None,
        "error": None,
        "query_plan": QUERY_PLAN,
        "blueprint_context": REFERENCE_BLUEPRINT,
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("case_name", "state", "llm_content"),
    [
        (
            "real_schema",
            _base_state(
                schema_context="【数据源真实表结构】\n表: user_logs | 列: id (int), content (text)",
            ),
            '{"sql": "select id from user_logs limit 10"}',
        ),
        (
            "ddl_inferred",
            _base_state(
                schema_context="【语义层】\n数据集: 日志数据集",
                ddl_context="表: user_logs | 列: id (int), content (text)",
                metric_resolution={
                    "all_matched": False,
                    "unresolved": ["用户日志"],
                    "metrics": [],
                    "dimensions": [],
                },
            ),
            '{"sql": "select id from user_logs limit 10"}',
        ),
        (
            "semantic",
            _base_state(
                schema_context="【语义层】\n指标: 日志条数\n维度: 日志ID",
                schema_structured={"metrics": [], "dimensions": [], "fields": []},
                metric_resolution={"all_matched": True, "metrics": [], "dimensions": []},
            ),
            '{"metrics": [], "dimensions": [], "filters": [], "time_range": null, "limit": 10}',
        ),
        (
            "no_schema",
            _base_state(schema_context=""),
            '{"sql": "select id from user_logs limit 10"}',
        ),
    ],
)
def test_dsl_prompt_includes_query_plan_for_all_paths(monkeypatch, case_name, state, llm_content):
    """四条 DSL prompt 构造路径都应消费 query_plan 和 blueprint_context。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse(llm_content)
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    result = nodes_module.dsl_generate_node(state, db=None)

    assert fake_llm.messages is not None, case_name
    human_prompt = fake_llm.messages[1].content
    assert "查询规划" in human_prompt
    assert "blueprint_as_reference" in human_prompt
    assert "参考蓝图" in human_prompt
    assert "不能原样执行" in human_prompt
    if case_name != "semantic":
        assert result["sql"] == "select id from user_logs limit 10"


def test_dsl_prompt_does_not_duplicate_reference_blueprint(monkeypatch):
    """当 schema_context 已经包含蓝图上下文时，DSL prompt 不应再次追加同一份文本。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = _base_state(
        schema_context=(
            "【数据源真实表结构】\n"
            "表: user_logs | 列: id (int), content (text)\n\n"
            f"{REFERENCE_BLUEPRINT}"
        ),
    )

    nodes_module.dsl_generate_node(state, db=None)

    human_prompt = fake_llm.messages[1].content
    assert human_prompt.count(REFERENCE_BLUEPRINT) == 1
    assert "查询规划" in human_prompt
    assert "blueprint_as_reference" in human_prompt


def test_format_query_plan_for_prompt_ignores_invalid_or_empty_plan():
    """helper 只在 query_plan 有有效规划字段时输出提示词片段。"""
    from app.graph.nodes import _format_query_plan_for_prompt

    assert _format_query_plan_for_prompt(None) == ""
    assert _format_query_plan_for_prompt([]) == ""
    assert _format_query_plan_for_prompt({}) == ""
