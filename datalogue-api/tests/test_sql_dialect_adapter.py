from app.domains.query_execution.dialect.adapter import adapt_sql_for_execution


def test_sql_dialect_adapter_accepts_current_sqlite_readonly_sql():
    result = adapt_sql_for_execution(
        "SELECT id FROM user_logs",
        dialect="sqlite",
        query_constraints={"enabled": True, "default_limit": 20, "max_limit": 100},
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is True
    assert result["dialect"] == "sqlite"
    assert result["execution_source"] == "tool_compiler"
    assert result["sql_guard"]["ok"] is True
    assert result["sql"].lower().startswith("select")
    assert "limit" in result["sql"].lower()


def test_sql_dialect_adapter_fails_closed_for_unknown_dialect():
    result = adapt_sql_for_execution("SELECT id FROM user_logs", dialect="snowflake")

    assert result["ok"] is False
    assert result["code"] == "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"
    assert result["sql"] is None
    assert result["execution_source"] == "tool_compiler"


def test_sql_dialect_adapter_rejects_target_dialect_mismatch():
    result = adapt_sql_for_execution(
        "SELECT id FROM user_logs",
        dialect="mysql",
        current_datasource_dialect="sqlite",
    )

    assert result["ok"] is False
    assert result["code"] == "DIALECT_UNSUPPORTED_FOR_CURRENT_DATASOURCE"
    assert result["sql"] is None


def test_sql_dialect_adapter_keeps_guard_readonly_boundary():
    result = adapt_sql_for_execution("DROP TABLE user_logs", dialect="sqlite")

    assert result["ok"] is False
    assert result["sql"] is None
    assert result["sql_guard"]["ok"] is False
    assert result["sql_guard"]["code"] in {"FORBIDDEN_KEYWORD", "NOT_READONLY"}


def test_sql_dialect_adapter_accepts_oracle_readonly_sql_with_fetch_first():
    result = adapt_sql_for_execution(
        "SELECT id FROM user_logs FETCH FIRST 20 ROWS ONLY",
        dialect="oracle",
        query_constraints={"enabled": True, "default_limit": 20, "max_limit": 100},
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is True
    assert result["dialect"] == "oracle"
    assert "FETCH FIRST 20 ROWS ONLY" in result["sql"]


def test_sql_dialect_adapter_normalizes_doris_to_mysql_execution_dialect():
    result = adapt_sql_for_execution(
        "SELECT id FROM user_logs",
        dialect="doris",
        current_datasource_dialect="doris",
        query_constraints={"enabled": True, "default_limit": 20, "max_limit": 100},
        allowed_tables=["user_logs"],
    )

    assert result["ok"] is True
    assert result["dialect"] == "mysql"
    assert "LIMIT" in result["sql"]
