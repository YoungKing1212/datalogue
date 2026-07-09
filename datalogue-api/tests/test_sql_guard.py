# ============================================================
# File Name   : test_sql_guard.py
# Description:
#   SQL 静态安全校验与方言规范化测试。
#
# Responsibilities:
#   - 验证只读 SQL、多语句和危险语法拦截。
#   - 验证执行前 LIMIT 补齐、裁剪和方言差异。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from app.domains.query_execution.sql_guard import guard_readonly_sql


def test_guard_allows_readonly_select_and_adds_limit():
    """普通 SELECT 会通过，并按默认约束补 LIMIT。"""
    result = guard_readonly_sql("SELECT id, name FROM users", dialect="mysql")

    assert result.ok is True
    assert result.normalized_sql == "SELECT id, name FROM users LIMIT 100"
    assert result.warnings


def test_guard_allows_readonly_with_query():
    """只读 WITH 查询允许执行。"""
    result = guard_readonly_sql(
        "WITH recent AS (SELECT id FROM orders) SELECT * FROM recent",
        dialect="postgres",
        query_constraints={"enabled": False},
    )

    assert result.ok is True
    assert result.normalized_sql == "WITH recent AS (SELECT id FROM orders) SELECT * FROM recent"


def test_guard_blocks_dml():
    """写操作关键字会被拦截。"""
    result = guard_readonly_sql("UPDATE users SET name = 'x'", dialect="mysql")

    assert result.ok is False
    assert result.code == "FORBIDDEN_KEYWORD"
    assert result.keyword == "update"


def test_guard_blocks_dml_inside_with():
    """WITH 中隐藏写操作也会被拦截。"""
    result = guard_readonly_sql(
        "WITH removed AS (DELETE FROM users RETURNING id) SELECT * FROM removed",
        dialect="postgres",
    )

    assert result.ok is False
    assert result.code == "FORBIDDEN_KEYWORD"
    assert result.keyword == "delete"


def test_guard_blocks_multi_statement():
    """多语句拼接会被拦截。"""
    result = guard_readonly_sql("SELECT * FROM users; SELECT * FROM orders", dialect="mysql")

    assert result.ok is False
    assert result.code == "MULTI_STATEMENT"


def test_guard_allows_trailing_semicolon():
    """单条查询末尾分号会被清理。"""
    result = guard_readonly_sql("SELECT * FROM users;", dialect="mysql")

    assert result.ok is True
    assert result.normalized_sql == "SELECT * FROM users LIMIT 100"


def test_guard_ignores_keywords_in_strings_and_comments():
    """字符串和注释里的危险词不应误杀。"""
    result = guard_readonly_sql(
        "SELECT 'drop table' AS label -- delete from users\nFROM audit_log",
        dialect="mysql",
    )

    assert result.ok is True
    assert "LIMIT 100" in result.normalized_sql


def test_guard_blocks_dangerous_function():
    """危险函数调用会被拦截。"""
    result = guard_readonly_sql("SELECT sleep(5)", dialect="mysql")

    assert result.ok is False
    assert result.code == "DANGEROUS_FUNCTION"
    assert result.keyword == "sleep"


def test_guard_blocks_into_outfile():
    """MySQL 文件导出语法会被拦截。"""
    result = guard_readonly_sql("SELECT * FROM users INTO OUTFILE '/tmp/a.csv'", dialect="mysql")

    assert result.ok is False
    assert result.code == "INTO_OUTFILE"


def test_guard_clamps_existing_limit():
    """超过上限的 LIMIT 会被裁剪。"""
    result = guard_readonly_sql(
        "SELECT * FROM users LIMIT 5000",
        dialect="mysql",
        query_constraints={"enabled": True, "default_limit": 100, "max_limit": 1000},
    )

    assert result.ok is True
    assert result.normalized_sql == "SELECT * FROM users LIMIT 1000"


def test_guard_oracle_uses_fetch_first():
    """Oracle 方言使用 FETCH FIRST 限制行数。"""
    result = guard_readonly_sql(
        "SELECT id FROM users",
        dialect="oracle",
        query_constraints={"enabled": True, "default_limit": 20, "max_limit": 100},
    )

    assert result.ok is True
    assert result.normalized_sql == "SELECT id FROM users FETCH FIRST 20 ROWS ONLY"


def test_guard_blocks_tables_outside_dataset_whitelist():
    """开启表白名单后，不允许查询当前数据集未选择的表。"""
    result = guard_readonly_sql(
        "SELECT id FROM payroll",
        dialect="mysql",
        allowed_tables=["orders", "customers"],
    )

    assert result.ok is False
    assert result.code == "SQL_GUARD_BLOCKED"
    assert "payroll" in result.error


def test_guard_allows_tables_inside_dataset_whitelist():
    """SQL 只访问授权表时允许继续规范化。"""
    result = guard_readonly_sql(
        "SELECT id FROM orders",
        dialect="postgres",
        allowed_tables=["orders"],
    )

    assert result.ok is True
    assert result.normalized_sql == "SELECT id FROM orders LIMIT 100"


def test_guard_does_not_treat_cte_names_as_unauthorized_tables():
    """WITH 查询白名单校验时，CTE 名称不能被当作物理表误杀。"""
    result = guard_readonly_sql(
        """
        WITH contract_stats AS (
            SELECT hzdw, COUNT(*) AS contract_count
            FROM project_contract_management
            GROUP BY hzdw
        ),
        supplier_scored AS (
            SELECT ps.GYSQC, cs.contract_count
            FROM project_supplier ps
            LEFT JOIN contract_stats cs ON ps.GYSQC = cs.hzdw
        )
        SELECT * FROM supplier_scored
        """,
        dialect="mysql",
        query_constraints={"enabled": False},
        allowed_tables=["project_contract_management", "project_supplier"],
    )

    assert result.ok is True
    assert result.normalized_sql
