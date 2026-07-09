# ============================================================
# File Name   : test_bi_lead_agent_capabilities.py
# Description:
#   BI Agent K1 能力清单与数据集摘要清洗测试。
#
# Responsibilities:
#   - 验证 LeadAgent 只暴露路由、确认和单数据集查询三类外层能力。
#   - 验证数据集能力摘要会剔除 DatasetAgent 内部执行上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

import pytest
from pydantic import ValidationError

from app.schemas.bi_agent import BIAgentCapability
from app.domains.bi.agent.capabilities import (
    build_bi_agent_capabilities,
    sanitize_dataset_capability,
)


def test_bi_lead_agent_capability_manifest_exposes_three_enabled_one_disabled():
    manifest = build_bi_agent_capabilities()
    enabled = {item.name for item in manifest if item.status == "enabled"}
    disabled = {item.name for item in manifest if item.status == "disabled"}

    assert enabled == {"list_dataset_capabilities", "request_dataset_confirmation", "query_dataset"}
    assert disabled == {"query_multiple_datasets"}
    assert "list_candidate_assets" not in enabled
    assert "compile_dsl_to_sql" not in enabled
    assert "execute_compiled_query" not in enabled
    assert "repair_dsl" not in enabled
    assert "create_query_artifact" not in enabled


def test_dataset_capability_summary_strips_dataset_internal_context():
    summary = sanitize_dataset_capability(
        {
            "dataset_id": 12,
            "name": "订单数据集",
            "domain": "销售",
            "supported_questions": ["订单金额趋势"],
            "key_metrics": ["订单金额"],
            "key_dimensions": ["月份"],
            "freshness": "T+1",
            "availability": "ready",
            "schema": {"orders": ["amount"]},
            "sql": "select * from orders",
            "dsl": {"metric": "amount"},
            "candidate_assets": [{"name": "订单金额"}],
            "field_mapping": {"amount": "orders.amount"},
            "blueprint_body": "内部蓝图正文",
        }
    )

    assert summary.model_dump() == {
        "dataset_id": 12,
        "name": "订单数据集",
        "domain": "销售",
        "supported_questions": ["订单金额趋势"],
        "key_metrics": ["订单金额"],
        "key_dimensions": ["月份"],
        "freshness": "T+1",
        "availability": "ready",
    }


def test_dataset_capability_summary_drops_complex_internal_items_and_keeps_safe_labels():
    summary = sanitize_dataset_capability(
        {
            "dataset_id": 12,
            "name": "订单数据集",
            "supported_questions": [
                {"raw_rows": [{"secret": "x"}]},
                {"question": "订单金额趋势"},
            ],
            "key_metrics": [
                {"result_rows": ["secret_order"]},
                {"name": "订单金额"},
            ],
            "key_dimensions": [
                {"sql": "select * from secret"},
                {"display_name": "月份"},
            ],
        }
    )

    payload = summary.model_dump_json()
    assert "raw_rows" not in payload
    assert "secret" not in payload
    assert "result_rows" not in payload
    assert "secret_order" not in payload
    assert "select * from secret" not in payload
    assert summary.supported_questions == ["订单金额趋势"]
    assert summary.key_metrics == ["订单金额"]
    assert summary.key_dimensions == ["月份"]


def test_bi_lead_agent_capability_requires_disabled_reason_and_replacement():
    with pytest.raises(ValidationError):
        BIAgentCapability(name="query_multiple_datasets", status="disabled")


def test_bi_lead_agent_capability_rejects_disabled_metadata_when_enabled():
    with pytest.raises(ValidationError):
        BIAgentCapability(
            name="query_dataset",
            status="enabled",
            disabled_reason="不应出现在 enabled 能力上",
        )
