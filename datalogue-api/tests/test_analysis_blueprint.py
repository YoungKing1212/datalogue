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


def _blueprint_payload():
    return {
        "name": "月度毛利归因报表",
        "description": "计算指定时间范围内各品类毛利额和毛利率",
        "trigger_keywords": ["毛利", "毛利率", "利润结构"],
        "trigger_examples": ["为什么本月毛利下降", "各品类毛利情况"],
        "when_to_use": "用户询问毛利归因时使用",
        "parameters": [
            {"name": "start_date", "type": "date", "required": True},
            {"name": "end_date", "type": "date", "required": True},
        ],
        "implementation_type": "stored_procedure",
        "call_template": "SELECT * FROM sp_margin(:start_date, :end_date)",
        "output_schema": [
            {"column": "category", "semantic": "品类", "role": "dimension"},
            {"column": "margin_rate", "semantic": "毛利率", "role": "metric"},
        ],
        "steps": [{"step": 1, "name": "订单汇总", "key_rules": ["只含已支付订单"]}],
        "attribution_hints": "优先关注毛利率变化",
        "raw_sql": "CREATE PROCEDURE sp_margin() BEGIN SELECT 1; END",
        "ai_confidence": 0.82,
    }


def test_create_and_list_blueprints(client, sample_dataset):
    resp = client.post(f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "月度毛利归因报表"
    assert data["status"] == "draft"
    assert data["version"] == 0

    list_resp = client.get(f"/api/dataset/{sample_dataset.id}/blueprints")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_analyze_sql_returns_task_result(client, sample_dataset):
    resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/analyze-sql",
        json={"sql": "CREATE PROCEDURE sp_margin(IN p_start DATE, IN p_end DATE) SELECT margin_rate;"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["result"]["name"] == "月度毛利归因报表"

    task_resp = client.get(
        f"/api/dataset/{sample_dataset.id}/blueprints/analyze-sql/{data['task_id']}"
    )
    assert task_resp.status_code == 200
    assert task_resp.json()["result"]["parameters"]


def test_publish_requires_test_then_creates_version(client, sample_dataset):
    create_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints", json=_blueprint_payload()
    )
    bid = create_resp.json()["id"]

    publish_resp = client.patch(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/status",
        json={"action": "publish"},
    )
    assert publish_resp.status_code == 400

    test_resp = client.post(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/test",
        json={"params": {"start_date": "2026-05-01", "end_date": "2026-05-31"}},
    )
    assert test_resp.status_code == 200
    assert test_resp.json()["ok"] is True

    publish_resp = client.patch(
        f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/status",
        json={"action": "publish", "change_summary": "首次发布"},
    )
    assert publish_resp.status_code == 200
    assert publish_resp.json()["status"] == "active"
    assert publish_resp.json()["version"] == 1

    versions = client.get(f"/api/dataset/{sample_dataset.id}/blueprints/{bid}/versions")
    assert versions.status_code == 200
    assert versions.json()[0]["version"] == 1
    assert versions.json()[0]["snapshot"]["name"] == "月度毛利归因报表"


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
