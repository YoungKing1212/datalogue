# ============================================================
# File Name   : test_sql_audit.py
# Description:
#   SQL 审核和失败诊断测试。
#
# Responsibilities:
#   - 验证审核分类和修复建议。
#   - 覆盖重试决策和终止失败路径。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
SQL 审计节点（sql_audit_node）单元测试 — mock LLM + 样例数据查询
"""

import json
from unittest.mock import MagicMock

import pytest


# 通用 state 模板
def _make_state(**overrides):
    state = {
        "question": "今年退款总金额",
        "dsl": {
            "metrics": ["退款金额"],
            "time_range": {"field": "create_date", "start": "2025-01-01", "end": "2025-12-31"},
        },
        "sql": "SELECT SUM(refund_amt) AS 退款金额 FROM t_refund WHERE `create_date` >= '2025-01-01'",
        "error": "Unknown column 'create_date' in 'where clause'",
        "schema_context": "【语义层】\n- 退款金额: 表达式=SUM(refund_amt) 表=t_refund 时间字段=apply_time",
        "ddl_context": "【所选表结构】\n表: t_refund\n  - id (BIGINT)\n  - refund_amt (DECIMAL)\n  - apply_time (DATETIME)",
        "schema_structured": {
            "dataset_name": "退款数据集",
            "tables_json": {"tables": [{"name": "t_refund"}], "joins": []},
            "metrics": [
                {
                    "name": "退款金额",
                    "display_name": "退款金额",
                    "expr": "SUM(refund_amt)",
                    "table_name": "t_refund",
                    "time_field": "apply_time",
                    "filter_sql": None,
                    "synonyms": [],
                }
            ],
            "dimensions": [],
        },
        "metric_resolution": {
            "metrics": [],
            "dimensions": [],
            "all_matched": True,
            "unresolved": [],
        },
        "dataset_id": 4,
        "max_retry_count": 3,
        "sql_retry_trace": [],
        "token_usage": None,
    }
    state.update(overrides)
    return state


def _mock_llm_response(content: str, usage: dict | None = None):
    """构造一个 LLM 响应 mock。"""
    response = MagicMock()
    response.content = content
    response.usage_metadata = usage or {
        "input_tokens": 200,
        "output_tokens": 100,
        "total_tokens": 300,
    }
    return response


def _patch_get_llm(monkeypatch, response: MagicMock):
    """monkeypatch get_llm：让 nodes.get_llm 返回一个 invoke 直接给 response 的对象。"""

    def _fake_get_llm(temperature=0.0, **kwargs):
        llm = MagicMock()
        llm.invoke.return_value = response
        return llm

    monkeypatch.setattr("app.graph.nodes.get_llm", _fake_get_llm)


def _patch_fetch_sample_rows(
    monkeypatch, text: str = "【样例数据】\n表 t_refund:\n  - id=1, refund_amt=100.0"
):
    """monkeypatch fetch_sample_rows（模块内的 _fetch_sample_rows）。"""

    def _fake_fetch(db, table_names, per_table=2, datasource=None):
        return text

    monkeypatch.setattr("app.graph.nodes._fetch_sample_rows", _fake_fetch)


# ── 测试 1: fixable → should_retry=True，error 字段被重写 ─────────


class TestSqlDiagnosisClassifier:
    """确定性 SQL 执行错误分类测试。"""

    @pytest.mark.parametrize(
        ("error", "sql", "expected_code", "expected_retryable"),
        [
            ("Unknown column 'create_date' in 'where clause'", "SELECT create_date FROM orders", "FIELD_NOT_FOUND", True),
            ("no such table: missing_orders", "SELECT * FROM missing_orders", "TABLE_NOT_SELECTED", False),
            ("no such table: orders", "SELECT * FROM orders", "TABLE_NOT_FOUND", False),
            ("column must appear in the GROUP BY clause", "SELECT region, SUM(amount) FROM orders", "AGGREGATION_ERROR", True),
            ("operator does not exist: integer = text", "SELECT * FROM orders WHERE id = 'abc'", "TYPE_ERROR", True),
            ("permission denied for table orders", "SELECT * FROM orders", "PERMISSION_DENIED", False),
            ("syntax error at or near \"LIMIT\"", "SELECT * FROM orders LIMIT", "SYNTAX_OR_DIALECT", True),
            ("statement timeout", "SELECT * FROM orders", "TIMEOUT", False),
            ("database server closed the connection unexpectedly", "SELECT * FROM orders", "UNKNOWN_EXECUTION_ERROR", True),
        ],
    )
    def test_classify_error_categories(self, error, sql, expected_code, expected_retryable):
        from app.utils import classify_sql_execution_error

        diagnosis = classify_sql_execution_error(
            error=error,
            sql=sql,
            schema_structured={"tables_json": {"tables": [{"name": "orders"}]}},
            datasource_dialect="postgres",
        )

        assert diagnosis["code"] == expected_code
        assert diagnosis["retryable"] is expected_retryable
        assert diagnosis["category"]
        assert diagnosis["title"]
        assert diagnosis["suggested_action"]
        assert diagnosis["original_error"] == error

    def test_semantic_asset_missing_field_is_field_mapping_drift(self):
        from app.utils import classify_sql_execution_error

        diagnosis = classify_sql_execution_error(
            error="Unknown column 'refund_amt' in 'field list'",
            sql="SELECT SUM(refund_amt) FROM t_refund",
            schema_structured={
                "tables_json": {"tables": [{"name": "t_refund"}]},
                "metrics": [{"name": "退款金额", "expr": "SUM(refund_amt)", "table_name": "t_refund"}],
            },
        )

        assert diagnosis["code"] == "FIELD_MAPPING_DRIFT"
        assert diagnosis["severity"] == "fixable"
        assert diagnosis["retryable"] is True
        assert "字段映射" in diagnosis["detail"]


class TestSqlAuditNode:
    """sql_audit_node 行为测试。"""

    def test_fixable_should_retry_and_rewrite_error(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        llm_response = _mock_llm_response(
            json.dumps(
                {
                    "root_cause": "time_range.field 错填 DDL 列名",
                    "wrong_field": "create_date",
                    "suggested_fix": "应改用指标'退款金额'的 time_field 'apply_time'",
                    "severity": "fixable",
                },
                ensure_ascii=False,
            )
        )
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        # db.get / db.query 都返回 None → dataset/datasource 都为 None
        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        node = sql_audit_node(db)
        state = _make_state()

        result = node(state)

        assert result["sql_audit_result"]["severity"] == "fixable"
        assert result["sql_audit_result"]["wrong_field"] == "create_date"
        assert result["sql_diagnosis"]["code"] == "FIELD_NOT_FOUND"
        assert result["should_retry"] is True
        assert result["sql_retry_trace"][0]["attempt"] == 1
        assert result["sql_retry_trace"][0]["original_sql"] == state["sql"]
        assert result["sql_retry_trace"][0]["status"] == "pending"
        assert "apply_time" in result["sql_retry_trace"][0]["repair_reason"]
        assert result["repair_plan"]["schema_version"] == "repair_plan.v1"
        assert result["repair_plan"]["failure_class"] == "FIELD_NOT_FOUND"
        assert result["repair_plan"]["status"] == "plan_created"
        assert result["repair_status"] == "plan_created"
        assert result["repair_attempts"] == 1
        assert result["repair_requires_user_confirmation"] is False
        assert result["repair_plan"]["actions"][0]["action_type"] == "replace_field"
        assert "select" not in json.dumps(result["repair_plan"], ensure_ascii=False).lower()
        # error 字段被改写为诊断友好文本
        assert "SQL 执行失败诊断" in result["error"]
        assert "time_range.field" in result["error"]
        # token_usage 累加
        assert result["token_usage"]["total_tokens"] == 300

    def test_repair_plan_validation_failure_blocks_workflow_retry(self, monkeypatch):
        from app.graph.nodes import sql_audit_node
        from app.graph.workflow import _sql_audit_router
        from app.services.repair_plan import RepairPlanValidationError

        llm_response = _mock_llm_response(
            json.dumps(
                {
                    "root_cause": "time_range.field 错填 DDL 列名",
                    "wrong_field": "create_date",
                    "suggested_fix": "应改用指标'退款金额'的 time_field 'apply_time'",
                    "severity": "fixable",
                },
                ensure_ascii=False,
            )
        )
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        def _reject_plan(**kwargs):
            raise RepairPlanValidationError("attempt limit exceeded")

        monkeypatch.setattr("app.graph.nodes.build_repair_plan_from_diagnosis", _reject_plan)

        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        result = sql_audit_node(db)(_make_state())

        assert result["should_retry"] is False
        assert result["sql_audit_result"]["retryable"] is False
        assert result["sql_audit_result"]["retry_decision"]["will_retry"] is False
        assert result["repair_status"] == "blocked"
        assert result["sql_retry_trace"] == []
        assert _sql_audit_router(result) == "end"

    # ── 测试 2: 字段映射漂移 → RepairPlan 接管重跑 ─────────

    def test_field_mapping_drift_should_retry_even_when_llm_calls_architectural(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        llm_response = _mock_llm_response(
            json.dumps(
                {
                    "root_cause": "指标 expr 引用了 DDL 中不存在的列",
                    "wrong_field": "refund_amt",
                    "suggested_fix": "在语义层把 expr 改为 SUM(refund_apply_amt)",
                    "severity": "architectural",
                },
                ensure_ascii=False,
            )
        )
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        node = sql_audit_node(db)
        state = _make_state(
            sql="SELECT SUM(refund_amt) AS 退款金额 FROM t_refund",
            error="Unknown column 'refund_amt' in 'field list'",
        )

        result = node(state)

        assert result["sql_audit_result"]["severity"] == "fixable"
        assert result["sql_audit_result"]["retryable"] is True
        assert result["sql_audit_result"]["code"] == "FIELD_MAPPING_DRIFT"
        assert result["should_retry"] is True
        assert result["sql_retry_trace"][0]["status"] == "pending"
        assert result["repair_plan"]["failure_class"] == "FIELD_MAPPING_DRIFT"
        assert result["repair_status"] == "plan_created"
        assert "SQL 执行失败诊断" in result["error"]
        assert "字段映射" in result["error"]

    def test_retry_exhausted_should_explain_unable_to_fix(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        llm_response = _mock_llm_response(
            json.dumps(
                {
                    "root_cause": "字段名仍然错误",
                    "wrong_field": "create_date",
                    "suggested_fix": "应改用 apply_time",
                },
                ensure_ascii=False,
            )
        )
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        result = sql_audit_node(db)(
            _make_state(
                retry_count=3,
                max_retry_count=3,
                sql_retry_trace=[
                    {"attempt": 1, "status": "failed"},
                    {"attempt": 2, "status": "failed"},
                    {"attempt": 3, "status": "failed"},
                ],
            )
        )

        assert result["should_retry"] is False
        assert result["sql_diagnosis"]["retry_decision"]["will_retry"] is False
        assert result["sql_diagnosis"]["retry_decision"]["reason"] == "已达到自动修复重试上限"
        assert "已达到自动修复重试上限（3 次）" in result["error"]
        assert len(result["sql_retry_trace"]) == 3

    # ── 测试 3: LLM 返回非 JSON → fallback fixable ─────────

    def test_llm_returns_non_json_fallback_fixable(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        # LLM 返回一段乱码（非 JSON）
        llm_response = _mock_llm_response("抱歉，我无法诊断这条 SQL 的错误。")
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        node = sql_audit_node(db)
        state = _make_state()

        result = node(state)

        # safe_json_parse 返回 {}，severity 默认 fixable
        assert result["sql_audit_result"]["severity"] == "fixable"
        assert result["should_retry"] is True
        assert result["sql_audit_result"]["code"] == "FIELD_NOT_FOUND"
        assert result["sql_audit_result"]["root_cause"]
        assert result["sql_retry_trace"][0]["result"] == "等待自动修复重试"
        # error 字段在 fixable 路径下被重写
        assert "SQL 执行失败诊断" in result["error"]

    # ── 测试 4: LLM 异常 → fallback fixable + 原始 error ─────────

    def test_llm_raises_exception_fallback_fixable(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        def _exploding_get_llm(temperature=0.0, **kwargs):
            llm = MagicMock()
            llm.invoke.side_effect = RuntimeError("LLM 服务不可用")
            return llm

        monkeypatch.setattr("app.graph.nodes.get_llm", _exploding_get_llm)
        _patch_fetch_sample_rows(monkeypatch)

        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        node = sql_audit_node(db)
        state = _make_state()

        result = node(state)

        # 异常兜底：使用确定性诊断，不依赖 LLM。
        assert result["sql_audit_result"]["severity"] == "fixable"
        assert result["sql_audit_result"]["code"] == "FIELD_NOT_FOUND"
        assert result["should_retry"] is True
        assert result["sql_retry_trace"][0]["diagnosis_code"] == "FIELD_NOT_FOUND"
        assert "SQL 执行失败诊断" in result["error"]
        assert "Unknown column 'create_date'" in result["error"]

    # ── 测试 5: LLM 返回非法 severity → 兜底 fixable ─────────

    def test_invalid_severity_fallback_to_fixable(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        llm_response = _mock_llm_response(
            json.dumps(
                {
                    "root_cause": "未知",
                    "wrong_field": None,
                    "suggested_fix": None,
                    "severity": "magic",  # 非法值
                },
                ensure_ascii=False,
            )
        )
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        node = sql_audit_node(db)
        state = _make_state()

        result = node(state)

        # 非法 severity 不覆盖确定性诊断。
        assert result["sql_audit_result"]["severity"] == "fixable"
        assert result["sql_audit_result"]["retryable"] is True
        assert result["should_retry"] is True

    def test_finish_latest_sql_retry_trace_records_result(self):
        from app.graph.nodes import _finish_latest_sql_retry_trace

        state = _make_state(
            sql="SELECT SUM(refund_amt) FROM t_refund WHERE apply_time >= '2025-01-01'",
            sql_retry_trace=[
                {
                    "attempt": 1,
                    "original_sql": "SELECT SUM(refund_amt) FROM t_refund WHERE create_date >= '2025-01-01'",
                    "repair_reason": "改用 apply_time",
                    "status": "pending",
                }
            ],
        )
        trace = _finish_latest_sql_retry_trace(
            state,
            status="success",
            result="自动修复后执行成功，返回 1 行",
            row_count=1,
        )

        assert trace[0]["status"] == "success"
        assert trace[0]["repaired_sql"] == state["sql"]
        assert trace[0]["row_count"] == 1

    def test_write_sql_diagnosis_log_best_effort(self, monkeypatch, db_session, sample_dataset):
        from app.graph.nodes import sql_audit_node
        from app.models import Conversation, SQLDiagnosisLog

        conv = Conversation(title="SQL 诊断测试", thread_id="thread-sql-diagnosis", user_id=1)
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        llm_response = _mock_llm_response(
            json.dumps(
                {
                    "root_cause": "time_range.field 错填 DDL 列名",
                    "wrong_field": "create_date",
                    "suggested_fix": "应改用 apply_time",
                },
                ensure_ascii=False,
            )
        )
        _patch_get_llm(monkeypatch, llm_response)
        _patch_fetch_sample_rows(monkeypatch)

        state = _make_state(
            conversation_id=conv.id,
            dataset_id=sample_dataset.id,
            retry_count=1,
        )
        result = sql_audit_node(db_session)(state)

        log = (
            db_session.query(SQLDiagnosisLog)
            .filter(SQLDiagnosisLog.conversation_id == conv.id)
            .one()
        )
        assert log.dataset_id == sample_dataset.id
        assert log.retry_count == 1
        assert log.sql == state["sql"]
        assert log.diagnosis["code"] == result["sql_diagnosis"]["code"]
        assert log.diagnosis["suggested_action"] == "应改用 apply_time"

    # ── 测试 6: _collect_audit_table_names 边界 ─────────


class TestCollectAuditTableNames:
    """辅助函数：收集审计相关表名。"""

    def test_collect_from_dsl_metrics(self):
        from app.graph.nodes import _collect_audit_table_names

        dsl = {"metrics": ["退款金额", "订单数"]}
        structured = {
            "metrics": [
                {"name": "退款金额", "table_name": "t_refund"},
                {"name": "订单数", "table_name": "t_order"},
            ]
        }
        names = _collect_audit_table_names(dsl, structured, None)
        assert set(names) == {"t_refund", "t_order"}

    def test_collect_from_sql_when_dsl_empty(self):
        from app.graph.nodes import _collect_audit_table_names

        # 没有 dsl / structured 的直接 SQL 路径
        names = _collect_audit_table_names({}, None, "SELECT * FROM t_order WHERE id = 1")
        assert names == ["t_order"]

    def test_collect_returns_empty_when_nothing(self):
        from app.graph.nodes import _collect_audit_table_names

        names = _collect_audit_table_names(None, None, None)
        assert names == []


# ── 路由测试: _sql_audit_router ─────────


class TestSqlAuditRouter:
    """workflow.py 内的 _sql_audit_router 行为。"""

    def test_architectural_routes_to_end(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "architectural", "retryable": False, "root_cause": "DDL 缺列"},
            "retry_count": 0,
        }
        assert _sql_audit_router(state) == "end"

    def test_retryable_false_routes_to_end(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "fixable", "retryable": False},
            "retry_count": 0,
        }
        assert _sql_audit_router(state) == "end"

    def test_fixable_routes_to_retry(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "fixable", "retryable": True, "root_cause": "time_field 错填"},
            "retry_count": 1,
        }
        assert _sql_audit_router(state) == "retry"

    def test_retry_exhausted_routes_to_end(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "fixable", "retryable": True},
            "retry_count": 3,
            "max_retry_count": 3,
        }
        assert _sql_audit_router(state) == "end"

    def test_custom_max_retry_count_routes_to_end(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "fixable", "retryable": True},
            "retry_count": 2,
            "max_retry_count": 2,
        }
        assert _sql_audit_router(state) == "end"

    def test_no_audit_state_routes_to_retry(self):
        from app.graph.workflow import _sql_audit_router

        # audit 字段缺失（如 LLM 异常时 audit 仍被写入，但 severity 兜底 fixable）
        state = {"sql_audit": None, "retry_count": 0}
        assert _sql_audit_router(state) == "retry"
