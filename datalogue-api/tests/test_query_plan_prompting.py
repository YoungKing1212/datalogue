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


def test_dsl_prompt_does_not_duplicate_reference_blueprint_from_dataset_prompt(monkeypatch):
    """当数据集级约束已包含蓝图上下文时，推断路径不应再次追加同一份文本。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = _base_state(
        schema_context="【语义层】\n数据集: 日志数据集",
        ddl_context="表: user_logs | 列: id (int), content (text)",
        metric_resolution={
            "all_matched": False,
            "unresolved": ["用户日志"],
            "metrics": [],
            "dimensions": [],
        },
        dataset_prompt_instructions=REFERENCE_BLUEPRINT,
    )

    nodes_module.dsl_generate_node(state, db=None)

    human_prompt = fake_llm.messages[1].content
    assert "【数据集级 LLM 约束（硬性要求）】" in human_prompt
    assert human_prompt.count(REFERENCE_BLUEPRINT) == 1
    assert "查询规划" in human_prompt
    assert "blueprint_as_reference" in human_prompt


def test_dsl_prompt_includes_task_capsule_without_raw_sql(monkeypatch):
    """DSL prompt 应追加任务胶囊摘要，但不能泄露 SQL 或结果行。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = _base_state(
        schema_context="【数据源真实表结构】\n表: user_logs | 列: id (int), content (text)",
        query_task_capsule={
            "turn_type": "followup",
            "base_task_ref": {
                "task_id": "task-1",
                "type": "last_success_task",
                "raw_sql": "select secret_token from audit_log",
                "result_rows": [{"secret_token": "abc123"}],
                "records": [{"password": "hidden"}],
                "data": [{"payload": "full row"}],
            },
            "base_main_table": "user_logs",
            "standalone_question": "查询最近7天的用户日志",
            "base_question": "查询用户日志",
            "raw_sql": "select password from users",
        },
    )

    nodes_module.dsl_generate_node(state, db=None)

    human_prompt = fake_llm.messages[1].content
    assert "【任务胶囊】" in human_prompt
    assert "turn_type: followup" in human_prompt
    assert 'base_task_ref: {"task_id": "task-1", "type": "last_success_task"}' in human_prompt
    assert "base_main_table: user_logs" in human_prompt
    assert "standalone_question: 查询最近7天的用户日志" in human_prompt
    assert "base_question: 查询用户日志" in human_prompt
    assert "select secret_token" not in human_prompt
    assert "select password" not in human_prompt
    assert "abc123" not in human_prompt
    assert "hidden" not in human_prompt
    assert "full row" not in human_prompt


def test_dsl_prompt_drops_sensitive_task_capsule_values(monkeypatch):
    """任务胶囊允许字段的 value 被污染时，也不能进入 DSL prompt。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = _base_state(
        schema_context="【数据源真实表结构】\n表: user_logs | 列: id (int), content (text)",
        query_task_capsule={
            "turn_type": "followup",
            "base_task_ref": {"task_id": "task-1"},
            "base_main_table": "user_logs where password = 'hidden'",
            "standalone_question": "查询日志；SELECT password FROM users",
            "base_question": '{"dsl": {"fields": ["secret"]}, "rows": [{"password": "hidden"}]}',
        },
    )

    nodes_module.dsl_generate_node(state, db=None)

    human_prompt = fake_llm.messages[1].content
    assert "【任务胶囊】" in human_prompt
    assert "turn_type: followup" in human_prompt
    assert 'base_task_ref: {"task_id": "task-1"}' in human_prompt
    assert "base_main_table:" not in human_prompt
    assert "standalone_question:" not in human_prompt
    assert "base_question:" not in human_prompt
    assert "SELECT password" not in human_prompt
    assert "where password" not in human_prompt
    assert '"dsl"' not in human_prompt
    assert '"rows"' not in human_prompt
    assert "hidden" not in human_prompt


def test_dsl_prompt_does_not_duplicate_task_capsule(monkeypatch):
    """当任务胶囊文本已在 prompt 中时，不应再次追加同一段。"""
    from app.graph import nodes as nodes_module

    task_capsule_text = (
        "【任务胶囊】\n"
        "turn_type: followup\n"
        "base_main_table: user_logs\n"
        "standalone_question: 查询最近7天的用户日志\n"
        "base_question: 查询用户日志"
    )
    fake_llm = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = _base_state(
        schema_context=(
            "【数据源真实表结构】\n"
            "表: user_logs | 列: id (int), content (text)\n\n"
            f"{task_capsule_text}"
        ),
        query_task_capsule={
            "turn_type": "followup",
            "base_main_table": "user_logs",
            "standalone_question": "查询最近7天的用户日志",
            "base_question": "查询用户日志",
        },
    )

    nodes_module.dsl_generate_node(state, db=None)

    human_prompt = fake_llm.messages[1].content
    assert human_prompt.count("【任务胶囊】") == 1


def test_semantic_prompt_uses_progressive_disclosure(monkeypatch):
    """语义层确定性路径应使用渐进式披露，避免重复灌入完整 schema_context。"""
    from app.graph import nodes as nodes_module

    fake_llm = _FakeLLMResponse(
        '{"fields": [{"name": "rzrq", "asset_type": "field", "asset_id": 1}], "limit": 10}'
    )
    monkeypatch.setattr(nodes_module, "get_llm", lambda **_kwargs: fake_llm)

    state = _base_state(
        schema_context=(
            "【语义层】\n"
            "数据集: 生产经营管理系统日志数据集\n\n"
            "【所选表字段与样例】\n"
            "- plan_task_daily_record.rzrq (date) 名称=日志日期\n"
            "- hy_tenant_user.tenant_user_id (varchar) 名称=在当前租户的用户id\n"
        ),
        schema_structured={
            "dataset_name": "生产经营管理系统日志数据集",
            "metrics": [],
            "dimensions": [],
            "terms": [],
            "blueprints": [],
            "fields": [
                {
                    "id": 1,
                    "name": "rzrq",
                    "column_name": "rzrq",
                    "table_name": "plan_task_daily_record",
                    "data_type": "date",
                    "display_name": "日志日期",
                    "semantic_role": "time_field",
                },
                {
                    "id": 2,
                    "name": "zt",
                    "column_name": "zt",
                    "table_name": "plan_task_daily_record",
                    "data_type": "varchar",
                    "display_name": "状态",
                    "semantic_role": "dimension_candidate",
                },
                {
                    "id": 3,
                    "name": "tenant_user_id",
                    "column_name": "tenant_user_id",
                    "table_name": "hy_tenant_user",
                    "data_type": "varchar",
                    "display_name": "在当前租户的用户id",
                    "semantic_role": "id_field",
                },
            ],
        },
        metric_resolution={"all_matched": True, "metrics": [], "dimensions": []},
        query_plan={
            "query_type": "detail_query",
            "execution_strategy": "query_graph",
            "planner_source": "deterministic",
            "selected_assets": [
                {
                    "asset_type": "field",
                    "name": "rzrq",
                    "metadata": {
                        "table_name": "plan_task_daily_record",
                        "column_name": "rzrq",
                    },
                }
            ],
            "debug": {"selected_main_table": "plan_task_daily_record"},
        },
        dataset_context_debug={
            "asset_counts": {"fields": 3},
            "retained_counts": {"fields": 2},
        },
    )

    nodes_module.dsl_generate_node(state, db=None)

    human_prompt = fake_llm.messages[1].content
    assert "【渐进式语义层上下文】" in human_prompt
    assert "【L0 数据集与任务】" in human_prompt
    assert "【L1 硬约束】" in human_prompt
    assert "【L2 相关语义资产】" in human_prompt
    assert "plan_task_daily_record" in human_prompt
    assert "rzrq" in human_prompt
    assert "hy_tenant_user.tenant_user_id" not in human_prompt
    assert "【所选表字段与样例】" not in human_prompt


def test_format_query_plan_for_prompt_ignores_invalid_or_empty_plan():
    """helper 只在 query_plan 有有效规划字段时输出提示词片段。"""
    from app.graph.nodes import _format_query_plan_for_prompt

    assert _format_query_plan_for_prompt(None) == ""
    assert _format_query_plan_for_prompt([]) == ""
    assert _format_query_plan_for_prompt({}) == ""
