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

    def _fake_get_llm(temperature=0.0):
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
        assert result["should_retry"] is True
        # error 字段被改写为审计友好文本（包含"上一轮 SQL 失败审计"）
        assert "上一轮 SQL 失败审计" in result["error"]
        assert "time_range.field" in result["error"]
        # token_usage 累加
        assert result["token_usage"]["total_tokens"] == 300

    # ── 测试 2: architectural → should_retry=False ─────────

    def test_architectural_should_not_retry(self, monkeypatch):
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
        state = _make_state()

        result = node(state)

        assert result["sql_audit_result"]["severity"] == "architectural"
        assert result["should_retry"] is False
        # architectural 时 error 字段保留原值（不带"上一轮 SQL 失败审计"）
        assert "上一轮 SQL 失败审计" not in result["error"]
        assert "Unknown column 'create_date'" in result["error"]

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
        # root_cause 为 None（LLM 没给）
        assert result["sql_audit_result"]["root_cause"] is None
        # error 字段在 fixable 路径下被重写
        assert "上一轮 SQL 失败审计" in result["error"]

    # ── 测试 4: LLM 异常 → fallback fixable + 原始 error ─────────

    def test_llm_raises_exception_fallback_fixable(self, monkeypatch):
        from app.graph.nodes import sql_audit_node

        def _exploding_get_llm(temperature=0.0):
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

        # 异常兜底：severity=fixable, 原始 error 保留（不被重写）
        assert result["sql_audit_result"]["severity"] == "fixable"
        assert "SQL审计节点异常" in result["sql_audit_result"]["root_cause"]
        assert result["should_retry"] is True
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

        # 非法 severity → 兜底 fixable
        assert result["sql_audit_result"]["severity"] == "fixable"
        assert result["should_retry"] is True

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
            "sql_audit_result": {"severity": "architectural", "root_cause": "DDL 缺列"},
            "retry_count": 0,
        }
        assert _sql_audit_router(state) == "end"

    def test_fixable_routes_to_retry(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "fixable", "root_cause": "time_field 错填"},
            "retry_count": 1,
        }
        assert _sql_audit_router(state) == "retry"

    def test_retry_exhausted_routes_to_end(self):
        from app.graph.workflow import _sql_audit_router

        state = {
            "sql_audit_result": {"severity": "fixable"},
            "retry_count": 3,
        }
        assert _sql_audit_router(state) == "end"

    def test_no_audit_state_routes_to_retry(self):
        from app.graph.workflow import _sql_audit_router

        # audit 字段缺失（如 LLM 异常时 audit 仍被写入，但 severity 兜底 fixable）
        state = {"sql_audit": None, "retry_count": 0}
        assert _sql_audit_router(state) == "retry"
