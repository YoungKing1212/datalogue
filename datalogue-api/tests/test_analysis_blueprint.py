# ============================================================
# File Name   : test_analysis_blueprint.py
# Description:
#   分析蓝图 API 和行为测试。
#
# Responsibilities:
#   - 验证蓝图增删改查、状态流转和执行记录。
#   - 验证 SQL 分析和蓝图试运行流程。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""分析蓝图 API 测试。"""

import json
from unittest.mock import MagicMock


def _mock_llm_response(payload: dict):
    """构造蓝图 AI 分析的 LLM 响应。"""
    response = MagicMock()
    response.content = json.dumps(payload, ensure_ascii=False)
    return response


def _ai_blueprint_payload():
    """AI 分析应返回的蓝图草案。"""
    return {
        "name": "月度毛利归因报表",
        "description": "分析各品类收入和毛利率变化，定位毛利下降原因。",
        "trigger_keywords": ["毛利", "毛利率", "品类收入"],
        "trigger_examples": ["为什么本月毛利下降", "各品类毛利率表现"],
        "when_to_use": "用户询问毛利变化、利润结构或品类收入表现时使用。",
        "parameters": [
            {
                "name": "start_date",
                "type": "date",
                "extract_hint": "分析开始日期",
                "default_expr": "MONTH_START",
                "required": True,
                "confidence": 0.91,
            },
            {
                "name": "end_date",
                "type": "date",
                "extract_hint": "分析结束日期",
                "default_expr": "TODAY",
                "required": True,
                "confidence": 0.9,
            },
        ],
        "implementation_type": "stored_procedure",
        "call_template": "",
        "output_schema": [
            {"column": "category", "semantic": "品类", "unit": "-", "role": "dimension", "confidence": 0.9},
            {"column": "revenue", "semantic": "收入", "unit": "元", "role": "metric", "confidence": 0.88},
            {"column": "margin_rate", "semantic": "毛利率", "unit": "%", "role": "metric", "confidence": 0.86},
        ],
        "steps": [
            {
                "step": 1,
                "name": "筛选分析周期",
                "purpose": "按开始和结束日期限定订单数据",
                "key_rules": ["使用日期参数裁剪数据"],
                "output_columns": [],
                "confidence": 0.88,
            },
            {
                "step": 2,
                "name": "品类毛利汇总",
                "purpose": "按品类汇总收入并输出毛利率",
                "key_rules": ["按 category 分组", "保留 margin_rate"],
                "output_columns": ["category", "revenue", "margin_rate"],
                "confidence": 0.86,
            },
        ],
        "attribution_hints": "优先关注毛利率下降的品类和收入贡献变化。",
        "raw_sql": "CREATE PROCEDURE sp_margin(...) SELECT ...",
        "ai_confidence": 0.89,
        "low_confidence_fields": [
            {"path": "output_schema.margin_rate", "confidence": 0.72, "reason": "需确认毛利率计算口径"}
        ],
    }


def _manual_blueprint_payload():
    """业务场景创建应返回的蓝图草案。"""
    return {
        "name": "毛利下降归因分析",
        "description": "分析毛利下降的主要业务原因，定位拖累利润的品类和区域。",
        "trigger_keywords": ["毛利下降", "利润变化", "品类盈利"],
        "trigger_examples": ["为什么本月毛利下降", "哪些品类拖累利润"],
        "when_to_use": "用户询问毛利、利润或品类盈利异常时使用。",
        "parameters": [
            {
                "name": "date_range",
                "type": "date",
                "extract_hint": "用户提到的分析周期",
                "default_expr": "MONTH_START",
                "required": False,
                "confidence": 0.84,
            }
        ],
        "implementation_type": "semantic_plan",
        "call_template": "",
        "output_schema": [
            {"column": "category", "semantic": "品类", "unit": "-", "role": "dimension", "confidence": 0.86},
            {"column": "margin_rate", "semantic": "毛利率", "unit": "%", "role": "metric", "confidence": 0.84},
        ],
        "steps": [
            {
                "step": 1,
                "name": "定位异常维度",
                "purpose": "识别毛利率下降明显的品类和区域",
                "key_rules": ["优先比较环比变化", "排除取消订单"],
                "output_columns": ["category", "margin_rate"],
                "confidence": 0.82,
            }
        ],
        "attribution_hints": "优先解释毛利率下降幅度和收入贡献同时较高的品类。",
        "raw_sql": "",
        "ai_confidence": 0.86,
        "low_confidence_fields": [
            {"path": "output_schema.margin_rate", "confidence": 0.7, "reason": "需确认毛利率口径"}
        ],
    }


def _patch_blueprint_ai(monkeypatch, payload: dict | None = None):
    """替换蓝图分析 LLM，避免测试访问真实模型。"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _mock_llm_response(payload or _ai_blueprint_payload())

    def _fake_get_llm(temperature=0.0):
        return mock_llm

    monkeypatch.setattr("app.services.blueprint_analyzer.get_llm", _fake_get_llm)
    return mock_llm


def _assert_done_analyze_task(task: dict) -> dict:
    """断言 AI 分析接口以单次请求返回最终结果。"""
    assert task["status"] == "done"
    assert task["result"]
    return task


def _blueprint_payload():
    return {
        "name": "月度毛利归因报表",
        "description": "计算指定时间范围内各品类毛利额和毛利率",
        "trigger_keywords": ["毛利", "毛利率", "利润结构"],
        "trigger_examples": ["为什么本月毛利下降", "各品类毛利情况"],
        "when_to_use": "用户询问毛利归因时使用",
        "parameters": [
            {
                "name": "start_date",
                "type": "date",
                "required": True,
                "default_expr": "MONTH_START",
            },
            {
                "name": "end_date",
                "type": "date",
                "required": True,
                "default_expr": "TODAY",
            },
        ],
        "implementation_type": "sql_template",
        "call_template": (
            "SELECT :start_date AS start_date, :end_date AS end_date, "
            "'电子' AS category, 0.31 AS margin_rate"
        ),
        "output_schema": [
            {"column": "category", "semantic": "品类", "role": "dimension"},
            {"column": "margin_rate", "semantic": "毛利率", "role": "metric"},
        ],
        "steps": [{"step": 1, "name": "订单汇总", "key_rules": ["只含已支付订单"]}],
        "attribution_hints": "优先关注毛利率变化",
        "raw_sql": "SELECT '电子' AS category, 0.31 AS margin_rate",
        "ai_confidence": 0.82,
    }


def test_extract_blueprint_params_from_chinese_year_and_person():
    """蓝图执行参数：从中文年份和姓名问法中提取日期范围与人员。"""
    from app.models.dataset import AnalysisBlueprint
    from app.services.analysis_blueprint import extract_blueprint_params

    bp = AnalysisBlueprint(
        parameters=[
            {"name": "person_name", "type": "string", "required": True},
            {"name": "start_date", "type": "date", "required": True},
            {"name": "end_date", "type": "date", "required": True},
        ]
    )

    params, missing = extract_blueprint_params(bp, "我要查询2024年杨凯的日报")

    assert missing == []
    assert params["person_name"] == "杨凯"
    assert params["start_date"] == "2024-01-01"
    assert params["end_date"] == "2024-12-31"


def test_extract_blueprint_params_from_chinese_month_range():
    """蓝图执行参数：从中文月份问法中提取月初和月末。"""
    from app.models.dataset import AnalysisBlueprint
    from app.services.analysis_blueprint import extract_blueprint_params

    bp = AnalysisBlueprint(
        parameters=[
            {"name": "person_name", "type": "string", "required": True},
            {"name": "start_date", "type": "date", "required": True},
            {"name": "end_date", "type": "date", "required": True},
        ]
    )

    params, missing = extract_blueprint_params(bp, "查询2024年2月杨凯的日报")

    assert missing == []
    assert params["person_name"] == "杨凯"
    assert params["start_date"] == "2024-02-01"
    assert params["end_date"] == "2024-02-29"


def test_create_and_list_blueprints(client, sample_dataset):
    resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "月度毛利归因报表"
    assert data["status"] == "draft"
    assert data["version"] == 0
    assert data["creation_source"] == "manual"
    assert data["ai_generated"] is False
    assert data["ai_generation_type"] is None

    list_resp = client.get(f"/api/dataset/{sample_dataset.id}/blueprints")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_analyze_sql_returns_task_result(client, sample_dataset, monkeypatch):
    mock_llm = _patch_blueprint_ai(monkeypatch)
    resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/analyze-sql",
        json={
            "sql": (
                "CREATE PROCEDURE sp_margin(IN p_start DATE, IN p_end DATE) "
                "SELECT category, SUM(revenue) AS revenue, margin_rate "
                "FROM margin_report WHERE dt BETWEEN :start_date AND :end_date "
                "GROUP BY category, margin_rate;"
            )
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    data = _assert_done_analyze_task(data)
    assert mock_llm.invoke.called
    assert data["result"]["name"] == "月度毛利归因报表"
    assert {p["name"] for p in data["result"]["parameters"]} == {"start_date", "end_date"}
    assert [c["column"] for c in data["result"]["output_schema"]] == [
        "category",
        "revenue",
        "margin_rate",
    ]
    assert "毛利下降原因" in data["result"]["description"]
    assert data["result"]["call_template"] == ""
    assert data["result"]["analysis_engine"] == "llm"
    assert data["result"]["creation_source"] == "sql_ai_analysis"
    assert data["result"]["ai_generated"] is True
    assert data["result"]["ai_generation_type"] == "sql_analysis"
    timing = data["result"]["analysis_timing_ms"]
    assert set(timing) >= {
        "preprocess",
        "prompt_build",
        "llm_client",
        "llm_invoke",
        "llm_total",
        "parse_json",
        "merge",
        "total",
        "prompt_chars",
        "sql_chars",
    }

    task_resp = client.get(
        f"/api/dataset/{sample_dataset.id}/blueprints/analyze-sql/{data['task_id']}"
    )
    assert task_resp.status_code == 200
    assert task_resp.json()["result"]["parameters"]


def test_analyze_description_returns_manual_ai_draft(client, sample_dataset, monkeypatch):
    mock_llm = _patch_blueprint_ai(monkeypatch, _manual_blueprint_payload())

    resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/analyze-description",
        json={
            "name": "毛利下降归因分析",
            "business_scenario": "当用户询问毛利下降、利润变化、品类盈利异常时使用。",
            "example_questions": ["为什么本月毛利下降", "哪些品类拖累利润"],
            "expected_output": "按品类、区域解释收入、成本和毛利率变化。",
            "business_rules": "只看已支付订单，排除退款和取消订单。",
        },
    )

    assert resp.status_code == 200
    data = _assert_done_analyze_task(resp.json())
    assert mock_llm.invoke.called
    result = data["result"]
    assert result["name"] == "毛利下降归因分析"
    assert result["implementation_type"] == "semantic_plan"
    assert result["call_template"] == ""
    assert result["raw_sql"] == ""
    assert result["analysis_source"] == "business_description"
    assert result["creation_source"] == "manual_ai_draft"
    assert result["ai_generated"] is True
    assert result["ai_generation_type"] == "description_analysis"
    assert "为什么本月毛利下降" in result["trigger_examples"]
    prompt_messages = mock_llm.invoke.call_args.args[0]
    prompt_text = prompt_messages[1].content
    assert "测试数据集" in prompt_text
    assert "GMV" in prompt_text


def test_create_blueprint_persists_ai_source_fields(client, sample_dataset):
    """保存 AI 分析草稿后，应能在蓝图列表和详情中区分来源。"""
    payload = {
        **_blueprint_payload(),
        "creation_source": "sql_ai_analysis",
        "ai_generated": True,
        "ai_generation_type": "sql_analysis",
    }

    resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["creation_source"] == "sql_ai_analysis"
    assert data["ai_generated"] is True
    assert data["ai_generation_type"] == "sql_analysis"

    list_resp = client.get(f"/api/dataset/{sample_dataset.id}/blueprints")
    assert list_resp.status_code == 200
    listed = list_resp.json()[0]
    assert listed["creation_source"] == "sql_ai_analysis"
    assert listed["ai_generated"] is True


def test_re_analyze_sql_returns_ai_diff(client, sample_dataset, monkeypatch):
    mock_llm = _patch_blueprint_ai(
        monkeypatch,
        {
            **_ai_blueprint_payload(),
            "name": "区域订单分析蓝图",
            "implementation_type": "sql_template",
            "call_template": "SELECT region, COUNT(*) AS order_count FROM orders GROUP BY region",
            "output_schema": [
                {
                    "column": "region",
                    "semantic": "区域",
                    "unit": "-",
                    "role": "dimension",
                    "confidence": 0.9,
                },
                {
                    "column": "order_count",
                    "semantic": "订单数",
                    "unit": "笔",
                    "role": "metric",
                    "confidence": 0.88,
                },
            ],
            "steps": [
                {
                    "step": 1,
                    "name": "区域订单汇总",
                    "purpose": "按区域统计订单数",
                    "key_rules": ["按 region 分组"],
                    "output_columns": ["region", "order_count"],
                    "confidence": 0.88,
                }
            ],
        },
    )
    create_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload()
    )
    bid = create_resp.json()["id"]

    resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/re-analyze",
        json={
            "sql": (
                "SELECT region, COUNT(*) AS order_count "
                "FROM orders WHERE order_date BETWEEN :start_date AND :end_date "
                "GROUP BY region"
            )
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    data = _assert_done_analyze_task(data)
    assert mock_llm.invoke.called
    assert data["result"]["implementation_type"] == "sql_template"
    assert data["result"]["call_template"].lower().startswith("select region")
    assert data["result"]["analysis_engine"] == "llm"
    assert data["result"]["diff_summary"]["step_count_after"] >= 1


def test_analyze_sql_replaces_variables_and_hides_values(client, sample_dataset, monkeypatch):
    mock_llm = _patch_blueprint_ai(
        monkeypatch,
        {
            **_ai_blueprint_payload(),
            "implementation_type": "sql_template",
            "description": "按 start_date 和 region=华东 分析 2026-05-01 的订单。",
            "trigger_keywords": ["region", "华东", ":start_date", "订单"],
            "trigger_examples": [
                "查看 2026-05-01 华东 region 的订单",
                "按 start_date 到 end_date 分析订单",
                "订单表现怎么样",
            ],
            "when_to_use": "用户提到 region 或 :start_date 时使用。",
            "call_template": (
                "SET @start_date = '2026-05-01'; "
                "SELECT * FROM orders WHERE dt >= @start_date "
                "AND dt <= :end_date AND region = '${region}'"
            ),
            "raw_sql": (
                "SET @start_date = '2026-05-01'; "
                "SELECT * FROM orders WHERE dt >= @start_date "
                "AND dt <= :end_date AND region = '${region}'"
            ),
            "parameters": [
                {
                    "name": "start_date",
                    "type": "date",
                    "extract_hint": "开始日期",
                    "default_expr": "2026-05-01",
                    "required": True,
                    "confidence": 0.9,
                },
                {
                    "name": "region",
                    "type": "string",
                    "extract_hint": "区域",
                    "default_expr": "华东",
                    "required": False,
                    "confidence": 0.82,
                },
            ],
            "steps": [
                {
                    "step": 1,
                    "name": "按 region 筛选",
                    "purpose": "使用 start_date 和 华东 限定订单",
                    "key_rules": ["region = 华东", "dt >= :start_date", "订单汇总"],
                    "output_columns": ["region", "order_count"],
                    "confidence": 0.8,
                }
            ],
            "attribution_hints": "重点解释 region=华东 在 2026-05-01 的变化。",
            "low_confidence_fields": [
                {
                    "path": "parameters.region",
                    "confidence": 0.6,
                    "reason": "region 来自 SQL 参数",
                }
            ],
        },
    )

    resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/analyze-sql",
        json={
            "sql": (
                "SET @start_date = '2026-05-01'; "
                "SET @region = '华东'; "
                "SELECT * FROM orders WHERE dt >= @start_date "
                "AND dt <= :end_date AND region = '${region}'"
            )
        },
    )

    assert resp.status_code == 200
    task = _assert_done_analyze_task(resp.json())
    data = task["result"]
    prompt_messages = mock_llm.invoke.call_args.args[0]
    prompt_text = prompt_messages[1].content
    assert "2026-05-01" not in prompt_text
    assert "'${region}'" not in prompt_text
    assert ":start_date" in prompt_text
    assert ":region" in prompt_text
    assert "2026-05-01" not in data["call_template"]
    assert "华东" not in str(data["parameters"])
    assert "SET @start_date" not in data["raw_sql"]
    assert ":start_date" in data["call_template"]
    assert ":region" in data["call_template"]
    defaults = {item["name"]: item["default_expr"] for item in data["parameters"]}
    assert defaults["start_date"] == "MONTH_START"
    assert defaults["region"] == "NULL"

    natural_language_fields = {
        "description": data["description"],
        "trigger_keywords": data["trigger_keywords"],
        "trigger_examples": data["trigger_examples"],
        "when_to_use": data["when_to_use"],
        "steps": data["steps"],
        "attribution_hints": data["attribution_hints"],
        "low_confidence_fields": data["low_confidence_fields"],
    }
    text = json.dumps(natural_language_fields, ensure_ascii=False)
    assert "2026-05-01" not in text
    assert "华东" not in text
    assert "start_date" not in text
    assert "end_date" not in text
    assert "region" not in text.lower()
    assert ":start_date" not in text


def test_publish_without_test_creates_version(client, sample_dataset):
    create_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload()
    )
    bid = create_resp.json()["id"]

    publish_resp = client.patch(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/status",
        json={"action": "publish", "change_summary": "直接发布"},
    )
    assert publish_resp.status_code == 200
    assert publish_resp.json()["status"] == "active"
    assert publish_resp.json()["version"] == 1

    versions = client.get(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/versions")
    assert versions.status_code == 200
    assert versions.json()[0]["version"] == 1
    assert versions.json()[0]["snapshot"]["name"] == "月度毛利归因报表"


def test_blueprint_test_remains_optional_validation(client, sample_dataset):
    create_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload()
    )
    bid = create_resp.json()["id"]

    test_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {"start_date": "2026-05-01", "end_date": "2026-05-31"}},
    )
    assert test_resp.status_code == 200
    assert test_resp.json()["ok"] is True
    assert test_resp.json()["row_count"] == 1
    assert test_resp.json()["diagnosis"] is None
    assert test_resp.json()["masking_summary"] == {"masked_cells": 0, "masked_columns": []}
    assert test_resp.json()["rows"][0]["category"] == "电子"


def test_rollback_creates_new_version(client, sample_dataset):
    create_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload()
    )
    bid = create_resp.json()["id"]
    client.post(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test", json={"params": {}})
    client.patch(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/status",
        json={"action": "publish"},
    )
    client.put(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}",
        json={"name": "已修改蓝图"},
    )

    rollback = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/rollback",
        json={"version": 1},
    )
    assert rollback.status_code == 200
    assert rollback.json()["name"] == "月度毛利归因报表"
    assert rollback.json()["version"] == 2


def test_usage_stats_after_test(client, sample_dataset):
    create_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload()
    )
    bid = create_resp.json()["id"]
    client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {}, "question": "为什么本月毛利下降"},
    )

    stats = client.get(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/usage-stats")
    assert stats.status_code == 200
    assert stats.json()["total_logs"] == 1
    assert stats.json()["execution_success_rate"] == 1

    logs = client.get(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/usage-logs")
    assert logs.status_code == 200
    assert logs.json()[0]["question"] == "为什么本月毛利下降"
    assert logs.json()[0]["row_count"] == 1
    assert logs.json()[0]["diagnosis"] is None


def test_blueprint_test_blocks_unsafe_sql(client, sample_dataset):
    payload = _blueprint_payload()
    payload["call_template"] = "DELETE FROM orders"
    create_resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=payload)
    bid = create_resp.json()["id"]

    test_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {"start_date": "2026-05-01", "end_date": "2026-05-31"}},
    )

    assert test_resp.status_code == 200
    assert test_resp.json()["ok"] is False
    assert "delete" in test_resp.json()["error_message"].lower()
    assert test_resp.json()["row_count"] == 0
    assert test_resp.json()["diagnosis"]["code"] == "UNSAFE_SQL"

    logs = client.get(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/usage-logs")
    assert logs.status_code == 200
    assert logs.json()[0]["row_count"] == 0
    assert logs.json()[0]["diagnosis"]["code"] == "UNSAFE_SQL"


def test_blueprint_test_missing_params_returns_diagnosis(client, sample_dataset):
    payload = _blueprint_payload()
    payload["parameters"] = [
        {
            "name": "required_region",
            "type": "string",
            "required": True,
        }
    ]
    payload["call_template"] = "SELECT :required_region AS region"
    create_resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=payload)
    bid = create_resp.json()["id"]

    test_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {}},
    )

    assert test_resp.status_code == 200
    data = test_resp.json()
    assert data["ok"] is False
    assert data["row_count"] == 0
    assert data["diagnosis"]["code"] == "MISSING_PARAMS"
    assert "required_region" in data["diagnosis"]["detail"]


def test_blueprint_test_execution_error_writes_diagnosis(client, sample_dataset):
    payload = _blueprint_payload()
    payload["call_template"] = "SELECT missing_column FROM missing_table"
    create_resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=payload)
    bid = create_resp.json()["id"]

    test_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {"start_date": "2026-05-01", "end_date": "2026-05-31"}},
    )

    assert test_resp.status_code == 200
    data = test_resp.json()
    assert data["ok"] is False
    assert data["row_count"] == 0
    assert data["diagnosis"]["code"] == "EXECUTION_ERROR"

    logs = client.get(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/usage-logs")
    assert logs.status_code == 200
    assert logs.json()[0]["row_count"] == 0
    assert logs.json()[0]["diagnosis"]["code"] == "EXECUTION_ERROR"


def test_blueprint_test_masks_sensitive_rows(client, sample_dataset):
    payload = _blueprint_payload()
    payload["parameters"] = []
    payload["call_template"] = (
        "SELECT '13812345678' AS phone, 'yangkai@example.com' AS email, "
        "'110105199001011234' AS id_card, "
        "'abcdefghijklmnopqrstuvwxyz123456' AS access_token"
    )
    create_resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=payload)
    bid = create_resp.json()["id"]

    test_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {}},
    )

    assert test_resp.status_code == 200
    data = test_resp.json()
    assert data["ok"] is True
    row = data["rows"][0]
    assert row["phone"] == "138****5678"
    assert row["email"] == "yan***@example.com"
    assert row["id_card"] == "110105********1234"
    assert row["access_token"] == "abcd***3456"
    assert data["masking_summary"]["masked_cells"] == 4
    assert data["masking_summary"]["masked_columns"] == [
        "access_token",
        "email",
        "id_card",
        "phone",
    ]


def test_execute_blueprint_timeout_returns_diagnosis(db_session, sample_dataset, monkeypatch):
    from app.models.dataset import AnalysisBlueprint, BlueprintUsageLog
    from app.services.analysis_blueprint import BlueprintExecutionTimeout, execute_analysis_blueprint

    bp = AnalysisBlueprint(
        dataset_id=sample_dataset.id,
        name="超时蓝图",
        description="模拟数据库超时",
        trigger_keywords=["超时"],
        parameters=[],
        implementation_type="sql_template",
        call_template="SELECT 1 AS value",
        timeout_seconds=1,
        status="active",
    )
    db_session.add(bp)
    db_session.commit()
    db_session.refresh(bp)

    class FakeConnection:
        connection = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            raise BlueprintExecutionTimeout("statement timeout")

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            return None

    monkeypatch.setattr(
        "app.services.analysis_blueprint.create_engine_for_datasource",
        lambda datasource: FakeEngine(),
    )

    result = execute_analysis_blueprint(
        db_session,
        bp,
        question="测试超时",
        require_active=True,
    )

    assert result["ok"] is False
    assert result["row_count"] == 0
    assert result["diagnosis"]["code"] == "TIMEOUT"
    log = db_session.query(BlueprintUsageLog).filter_by(blueprint_id=bp.id).one()
    assert log.row_count == 0
    assert log.diagnosis["code"] == "TIMEOUT"
