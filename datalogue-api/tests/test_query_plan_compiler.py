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

from app.domains.query_execution.compiler import compile_query_plan_to_sql


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
    compiled = _compile(dialect="snowflake")

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
    assert "LIKE :filter_0" in compiled["sql"]
    assert compiled["params"]["filter_0"] == "%foo%"


def test_contains_operator_escapes_percent_literal():
    """值中的 % 字符必须被转义，避免被当作 LIKE 通配符。"""
    plan = _base_plan()
    plan["filters"] = [{"field": "order_id", "operator": "contains", "value": "50%"}]

    compiled = _compile(plan=plan)

    assert compiled["ok"] is True
    # 转义后的 % 只能存在于绑定参数中，不能重新内联进 SQL。
    assert "\\%" not in compiled["sql"]
    assert compiled["params"]["filter_0"] == "%50\\%%"
    assert "ESCAPE '\\'" in compiled["sql"]


def test_filter_value_with_backslash_and_quote_remains_bound_parameter():
    """过滤值中的反斜杠与引号不能因 Guard/数据库解析差异改写 WHERE 语义。"""

    attack_value = "\\' OR 1=1 --"
    plan = _base_plan()
    plan["filters"] = [{"field": "order_id", "operator": "=", "value": attack_value}]

    compiled = _compile(plan=plan)

    assert compiled["ok"] is True
    assert attack_value not in compiled["sql"]
    assert compiled["params"]["filter_0"] == attack_value


# ---- join_requirements 编译契约（改动 C 新增）----


def _join_context() -> dict:
    """构造 orders + departments 两表 schema，供 JOIN 相关用例复用。"""
    return {
        "table_schemas": [
            {
                "table_name": "orders",
                "fields": [{"column_name": "order_id"}, {"column_name": "dept_id"}],
            },
            {
                "table_name": "departments",
                "fields": [{"column_name": "id"}, {"column_name": "name"}],
            },
        ],
    }


def test_compiles_inner_join_from_join_requirements():
    """join_requirements 声明的 INNER JOIN 应被编译进最终 SQL。"""
    plan = _base_plan()
    plan["join_requirements"] = [
        {
            "left_alias": "main",
            "right_alias": "dept",
            "left_table": "orders",
            "right_table": "departments",
            "relationship_ref": "dataset_selected:orders.dept",
            "join_type": "inner",
            "required": True,
            "reason": "补齐部门信息",
            "join_keys": [{"left_field": "dept_id", "right_field": "id"}],
        }
    ]

    compiled = _compile(
        plan=plan,
        context=_join_context(),
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is True
    assert 'INNER JOIN "departments" ON "orders"."dept_id" = "departments"."id"' in compiled["sql"]


def test_compiles_left_join_with_multiple_join_keys():
    """多组 join_keys 应通过 AND 拼接在同一 ON 子句里。"""
    plan = _base_plan()
    plan["join_requirements"] = [
        {
            "left_alias": "main",
            "right_alias": "dept",
            "left_table": "orders",
            "right_table": "departments",
            "relationship_ref": "dataset_selected:orders.dept",
            "join_type": "left",
            "required": True,
            "reason": "多字段联合关联",
            "join_keys": [
                {"left_field": "dept_id", "right_field": "id"},
                {"left_field": "order_id", "right_field": "name"},
            ],
        }
    ]

    compiled = _compile(
        plan=plan,
        context=_join_context(),
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is True
    assert 'LEFT JOIN "departments" ON' in compiled["sql"]
    # 两个 ON 条件必须 AND 拼接，避免退化为仅使用其中一个 key
    assert (
        '"orders"."dept_id" = "departments"."id" AND ' '"orders"."order_id" = "departments"."name"'
    ) in compiled["sql"]


def test_fails_closed_when_join_missing_join_keys():
    """join_keys 为空时 fail-closed，避免退化为笛卡尔积。"""
    plan = _base_plan()
    plan["join_requirements"] = [
        {
            "left_alias": "main",
            "right_alias": "dept",
            "left_table": "orders",
            "right_table": "departments",
            "relationship_ref": "dataset_selected:orders.dept",
            "join_type": "inner",
            "required": True,
            "reason": "缺 join 条件",
            "join_keys": [],
        }
    ]

    compiled = _compile(
        plan=plan,
        context=_join_context(),
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is False
    assert compiled["code"] == "PLAN_NOT_COMPILABLE"


def test_fails_closed_when_join_table_not_in_allowed_tables():
    """右表不在白名单里时 fail-closed，避免绕过 SQL Guard。"""
    plan = _base_plan()
    plan["join_requirements"] = [
        {
            "left_alias": "main",
            "right_alias": "dept",
            "left_table": "orders",
            "right_table": "departments",
            "relationship_ref": "dataset_selected:orders.dept",
            "join_type": "inner",
            "required": True,
            "reason": "白名单外表",
            "join_keys": [{"left_field": "dept_id", "right_field": "id"}],
        }
    ]

    compiled = _compile(
        plan=plan,
        context=_join_context(),
        allowed_tables=["orders"],  # 仅允许 orders，departments 被拦截
    )

    assert compiled["ok"] is False
    assert compiled["code"] == "PLAN_NOT_COMPILABLE"


def test_fails_closed_when_join_type_unsupported():
    """join_type 只允许 inner/left；其它类型 fail-closed。"""
    plan = _base_plan()
    plan["join_requirements"] = [
        {
            "left_alias": "main",
            "right_alias": "dept",
            "left_table": "orders",
            "right_table": "departments",
            "relationship_ref": "dataset_selected:orders.dept",
            "join_type": "cross",  # 非法 join 类型
            "required": True,
            "reason": "非法 join 类型",
            "join_keys": [{"left_field": "dept_id", "right_field": "id"}],
        }
    ]

    compiled = _compile(
        plan=plan,
        context=_join_context(),
        allowed_tables=["orders", "departments"],
    )

    assert compiled["ok"] is False
    assert compiled["code"] == "PLAN_NOT_COMPILABLE"


def test_no_join_when_join_requirements_empty():
    """join_requirements 缺失或为空时正常出 SQL，且不含 JOIN 关键字。"""
    plan = _base_plan()
    # 显式设为空列表，验证不会 fail-closed 也不会产生 JOIN 子句
    plan["join_requirements"] = []

    compiled = _compile(plan=plan)

    assert compiled["ok"] is True
    # SELECT 语法不含其它 JOIN 关键字，所以这里可以直接断言不出现
    assert "JOIN" not in compiled["sql"]


def test_compiles_oracle_limit_as_fetch_first():
    """Oracle 查询计划编译器必须渲染 FETCH FIRST，不能生成 LIMIT。"""
    plan = _base_plan()
    plan["limit"] = 25

    compiled = _compile(
        plan=plan,
        dialect="oracle",
        current_datasource_dialect="oracle",
        query_constraints={"enabled": True, "default_limit": 25, "max_limit": 100},
    )

    assert compiled["ok"] is True
    assert compiled["dialect"] == "oracle"
    assert "FETCH FIRST 25 ROWS ONLY" in compiled["sql"]
    assert " LIMIT " not in compiled["sql"]


def test_compiles_doris_stale_dialect_as_mysql_limit():
    """Doris 第一阶段只作为产品 db_type，执行方言统一归一化为 MySQL。"""
    plan = _base_plan()
    plan["limit"] = 30

    compiled = _compile(plan=plan, dialect="doris", current_datasource_dialect="doris")

    assert compiled["ok"] is True
    assert compiled["dialect"] == "mysql"
    assert "`orders`.`order_id`" in compiled["sql"]
    assert "LIMIT 30" in compiled["sql"]
