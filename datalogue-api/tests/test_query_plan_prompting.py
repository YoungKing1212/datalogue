# ============================================================
# File Name   : test_query_plan_prompting.py
# Description:
#   验证 QueryGraph DSL 生成提示词会携带查询规划和参考蓝图上下文。
#
# Responsibilities:
#   - 覆盖 blueprint_as_reference 场景下蓝图只能参考、不能原样执行的提示词约束。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================


class _FakeLLMResponse:
    """记录 DSL 节点发给 LLM 的 messages，并返回指定 SQL JSON。"""

    def __init__(self):
        self.messages = None
        self.content = '{"sql": "select id from user_logs limit 10"}'
        self.usage_metadata = None

    def invoke(self, messages):
        self.messages = messages
        return self


def test_dsl_prompt_includes_query_plan_and_reference_blueprint(monkeypatch):
    """真实 schema 路径应把查询规划和参考蓝图一起放入 human prompt。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = {
        "question": "查询10条用户日志",
        "schema_context": "【数据源真实表结构】\n表: user_logs | 列: id (int), content (text)",
        "query_constraints": {"enabled": False},
        "multiturn_context": None,
        "error": None,
        "query_plan": {
            "query_type": "detail_query",
            "execution_strategy": "blueprint_as_reference",
            "explanation": {"summary": "蓝图仅参考"},
        },
        "blueprint_context": "【参考蓝图（非直接执行）】\n不能原样执行\nselect * from daily_report",
    }

    result = nodes_module.dsl_generate_node(state, db=None)

    assert fake_llm.messages is not None
    human_prompt = fake_llm.messages[1].content
    assert "查询规划" in human_prompt
    assert "blueprint_as_reference" in human_prompt
    assert "参考蓝图" in human_prompt
    assert "不能原样执行" in human_prompt
    assert result["sql"] == "select id from user_logs limit 10"
