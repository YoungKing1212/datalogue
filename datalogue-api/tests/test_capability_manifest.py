# ============================================================
# File Name   : test_capability_manifest.py
# Description:
#   数据集能力清单契约测试。
#
# Responsibilities:
#   - 验证 LeadAgent 可见能力清单只包含业务摘要。
#   - 验证字段、表、SQL、blueprint 等内部资产不会进入输出。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

import pytest

from app.core import models
from app.services.capability_manifest import (
    assert_manifest_payload_safe,
    build_dataset_capability_manifest,
    list_capability_manifest_summaries,
)


def test_capability_manifest_uses_business_summaries_only(db_session, sample_dataset):
    manifest = models.DatasetSubAgentManifest(
        dataset_id=sample_dataset.id,
        manifest_version="v1",
        bound_schema_version="hash1",
        is_current=True,
        review_status="approved",
        manifest_json={
            "manual_fields": {
                "description": "订单销售数据集用于分析销售额、订单数量和区域表现。",
                "business_domain": ["销售运营"],
                "sample_questions": ["最近30日GMV趋势如何"],
                "routing_negative_examples": ["库存周转率是多少"],
                "permission_scope": {"status": "allowed", "description": "允许查询销售运营指标。"},
            },
            "internal_assets": {
                "raw_sql": "select * from orders",
                "fields": ["amount"],
            },
        },
    )
    db_session.add(manifest)
    db_session.commit()

    visible = build_dataset_capability_manifest(db_session, sample_dataset.id).model_dump()

    assert visible["dataset_id"] == sample_dataset.id
    assert visible["business_name"] == sample_dataset.name
    assert visible["quality_status"] == "published"
    assert "GMV" in visible["metrics"]
    assert "地区" in visible["dimensions"]
    assert visible["typical_questions"] == ["最近30日GMV趋势如何"]
    assert visible["cannot_answer"] == ["库存周转率是多少"]
    serialized = str(visible)
    assert "raw_sql" not in serialized
    assert "orders" not in serialized
    assert "amount" not in serialized


def test_capability_manifest_safety_rejects_internal_keys(sample_dataset):
    from app.core.schemas.capability_manifest import CapabilityManifest

    manifest = CapabilityManifest(
        dataset_id=sample_dataset.id,
        business_name="泄露测试",
        can_answer=["查询业务结果"],
    )
    payload = manifest.model_dump()
    payload["raw_sql"] = "select * from t"

    with pytest.raises(ValueError, match="forbidden internal details"):
        assert_manifest_payload_safe(payload)


def test_capability_manifest_summary_list_is_safe(db_session, sample_dataset):
    summaries = list_capability_manifest_summaries(db_session)

    assert summaries
    summary = summaries[0].model_dump()
    assert summary["schema_version"] == "capability_manifest.v1"
    assert "GMV" in summary["metrics"]
    assert "raw_sql" not in str(summary)
