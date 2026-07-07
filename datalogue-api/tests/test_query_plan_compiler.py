# ============================================================
# File Name   : test_query_plan_compiler.py
# Description:
#   查询计划编译器的安全边界与 fail-closed 行为测试。
#
#   覆盖：
#   - 拒绝把 LLM 生成 SQL 作为执行依据（含嵌套 dict/list 场景）。
#   - 未识别方言 / 方言不匹配 fail-closed。
#   - 未支持执行策略 fail-closed。
#   - 未识别筛选算子 fail-closed，避免过滤条件静默丢失。
#   - contains 算子使用 ESCAPE 子句正确转义 % 与 _。
# ============================================================

from app.services.query_plan_compiler import compile_query_plan_to_sql


def _base_plan() -> dict:
    """返回可编译的最小查询计划。"""
    return {
        "execution_strategy": "query_graph",
        "selected_assets": [
            {
                "asset_type": "field",
                "name": "orders.order_id",
                "metadata": {"table_name": "orders", "column_name": "order_id"},
                "display_name": "订单号",
            }
        ],
    }


def _base_context(**overrides) -> dict:
    """返回最小可编译的语义资产上下文。"""
    context = {
        "table_schemas": [
            {"table_name": "orders", "fields": [{"column_name": "order_id"}]},
        ],
    }
    context.update(overrides)
    return context


def _compile(plan: dict | None = None, context: dict | None = None, **kwargs) -> dict:
    """封装公共编译入口的常用调用参数。"""
    return compile_query_plan_to_sql(
        query_plan=plan or _base_plan(),
        sql_generation_context=context or _base_context(),
        dialect=kwargs.pop("dialect", "sqlite"),
        allowed_tables=kwargs.pop("allowed_tables", ["orders"]),
        **kwargs,
    )


def test_rejects_llm_sql_in_context_top_level():
    """sql_generation_context 顶层出现 llm_sql 即拒绝执行。"""
    compiled = _compile(context=_base_context(llm_sql="SELECT * FROM orders"))

    assert compiled["ok"] is False
    assert compiled["code"] == "LLM_SQL_NOT_EXECUTABLE"


def test_rejects_llm_sql_nested_in_dict():
    """嵌套 dict 中的 sql 键也必须被识别并拒绝。"""
    compiled = _compile(
        context=_base_context(
            table_schemas=[
                {
                    "table_name": "orders",
                    "fields": [{"column_name": "order_id"}],
                    "metadata": {"sql": "SELECT 1"},
                }
            ]
        )
    )

    assert compiled["ok"] is False
    assert compiled["code"] == "LLM_SQL_NOT_EXECUTABLE"


def test_rejects_llm_sql_nested_in_list():
    """嵌套 list 中的 raw_sql 键也必须被识别并拒绝。"""
    compiled = _compile(
        context=_base_context(
            table_schemas=[
                {
                    "table_name": "orders",
                    "fields": [{"column_name": "order_id", "raw_sql": "SELECT 1"}],
                }
            ]
        )
    )

    assert compiled["ok"] is False
    assert compiled["code"] == "LLM_SQL_NOT_EXECUTABLE"


def test_rejects_unsupported_execution_strategy():
    """未支持的执行策略 fail-closed。"""
    plan = _base_plan()
    plan["execution_strategy"] = "unknown_strategy"

    compiled = _compile(plan=plan)

    assert compiled["ok"] is False
    assert compiled["code"] == "UNSUPPORTED_STRATEGY"


def test_fails_closed_for_unknown_dialect():
    """未识别的方言 fail-closed。"""
    compiled = _compile(dialect="oracle")

    assert compiled["ok"] is False
    assert compiled["code"] == "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"


def test_rejects_dialect_mismatch_with_current_datasource():
    """查询计划方言与当前数据源方言不一致时 fail-closed。"""
    compiled = _compile(dialect="mysql", current_datasource_dialect="sqlite")

    assert compiled["ok"] is False
    assert compiled["code"] == "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"


def test_rejects_unsupported_filter_operator():
    """未识别的筛选算子 fail-closed，避免过滤条件静默丢失导致返回过多行。"""
    plan = _base_plan()
    plan["filters"] = [{"field": "order_id", "operator": "like", "value": "%foo%"}]

    compiled = _compile(plan=plan)

    assert compiled["ok"] is False
    assert compiled["code"] == "PLAN_NOT_COMPILABLE"


def test_contains_operator_emits_escape_clause():
    """contains 算子必须生成 ESCAPE 子句，确保 SQLite 下 % 与 _ 转义生效。"""
    plan = _base_plan()
    plan["filters"] = [{"field": "order_id", "operator": "contains", "value": "foo"}]

    compiled = _compile(plan=plan)

    assert compiled["ok"] is True
    assert "ESCAPE '\\'" in compiled["sql"]
    assert "LIKE '%foo%'" in compiled["sql"]


def test_contains_operator_escapes_percent_literal():
    """值中的 % 字符必须被转义，避免被当作 LIKE 通配符。"""
    plan = _base_plan()
    plan["filters"] = [{"field": "order_id", "operator": "contains", "value": "50%"}]

    compiled = _compile(plan=plan)

    assert compiled["ok"] is True
    # 转义后的 % 应以 \% 形式出现在 SQL 中，且附带 ESCAPE 子句
    assert "\\%" in compiled["sql"]
    assert "ESCAPE '\\'" in compiled["sql"]
