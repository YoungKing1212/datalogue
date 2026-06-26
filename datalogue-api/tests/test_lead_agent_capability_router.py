# ============================================================
# File Name   : test_lead_agent_capability_router.py
# Description:
#   LeadAgent Capability Router 回归测试。
#
# Responsibilities:
#   - 验证 LeadAgent 数据集路由只暴露 capability manifest 级候选摘要。
#   - 覆盖单数据集、跨数据集、低置信澄清和无 Manifest 四类路径。
#   - 固定低置信/歧义路径不能继续 fan-out 到 DatasetAgent。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from app import models
from app.services.dataset_router import route_dataset_for_question
from app.services.lead_agent_routing import _classify_entry_intent
from app.services.lead_agent import (
    build_clarification,
    build_subagent_dispatch,
    check_schema_status,
)


CAPABILITY_CANDIDATE_KEYS = {
    "dataset_id",
    "dataset_name",
    "reason",
    "confidence",
    "requires_confirmation",
}


def _add_dataset(db_session, sample_datasource, name: str):
    dataset = models.SemanticDataset(
        name=name,
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "orders"}], "joins": []},
        description=f"{name} 测试数据集",
        status="active",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def _add_current_manifest(
    db_session,
    *,
    dataset_id: int,
    dataset_name: str,
    domain: str,
    sample_questions: list[str] | None = None,
    description: str | None = None,
    negative_examples: list[str] | None = None,
):
    manifest = models.DatasetSubAgentManifest(
        dataset_id=dataset_id,
        manifest_version="v1",
        bound_schema_version=f"schema-{dataset_id}",
        review_status="current",
        is_current=True,
        manifest_json={
            "auto_fields": {
                "name": dataset_name,
                "key_metrics": [
                    {"name": "gmv", "display_name": "GMV", "synonyms": ["销售额"]},
                    {"name": "order_count", "display_name": "订单数", "synonyms": ["订单量"]},
                ],
                "key_dimensions": [
                    {"name": "region", "display_name": "地区", "synonyms": ["区域"]},
                ],
            },
            "manual_fields": {
                "description": description or f"{dataset_name} 用于 {domain} 问数。",
                "business_domain": [domain],
                "sample_questions": sample_questions or [],
                "routing_negative_examples": negative_examples or [],
            },
        },
    )
    db_session.add(manifest)
    db_session.commit()
    db_session.refresh(manifest)
    return manifest


def _candidate_keys(decision: dict):
    return [set(candidate) for candidate in decision.get("candidates", [])]


def test_single_dataset_selected_uses_capability_candidate_only(db_session, sample_dataset):
    """明确命中单数据集时自动选择，候选不能泄露 schema/SQL/资产详情字段。"""

    _add_current_manifest(
        db_session,
        dataset_id=sample_dataset.id,
        dataset_name="订单销售",
        domain="销售运营",
        sample_questions=["最近30日GMV趋势如何"],
    )

    decision = route_dataset_for_question(db_session, "最近30日GMV趋势如何")

    assert decision["decision"] == "selected"
    assert decision["dataset_id"] == sample_dataset.id
    assert _candidate_keys(decision) == [CAPABILITY_CANDIDATE_KEYS]
    assert decision["candidates"][0]["dataset_id"] == sample_dataset.id
    assert decision["candidates"][0]["dataset_name"] == "订单销售"
    assert "命中典型正例" in decision["candidates"][0]["reason"]
    assert decision["candidates"][0]["confidence"] >= 0.65
    assert decision["candidates"][0]["requires_confirmation"] is False


def test_cross_dataset_close_scores_require_confirmation(
    db_session,
    sample_dataset,
    sample_datasource,
):
    """多个数据集能力摘要得分接近时只返回确认候选，不进入 SubAgent dispatch。"""

    supplier_dataset = _add_dataset(db_session, sample_datasource, "供应商采购")
    _add_current_manifest(
        db_session,
        dataset_id=sample_dataset.id,
        dataset_name="订单销售",
        domain="销售运营",
        sample_questions=["最近30日GMV趋势如何"],
    )
    _add_current_manifest(
        db_session,
        dataset_id=supplier_dataset.id,
        dataset_name="供应商采购",
        domain="采购管理",
        sample_questions=["最近30日GMV趋势如何"],
    )

    decision = route_dataset_for_question(db_session, "最近30日GMV趋势如何")
    schema_status = check_schema_status(db_session, decision)
    clarification = build_clarification(decision, schema_status)
    dispatch = build_subagent_dispatch(
        question="最近30日GMV趋势如何",
        route_decision=decision,
        time_context={},
        thread_context={},
        schema_status=schema_status,
        manifest_guard={"status": "ok"},
    )

    assert decision["decision"] == "ambiguous"
    assert decision["dataset_id"] is None
    assert all(keys == CAPABILITY_CANDIDATE_KEYS for keys in _candidate_keys(decision))
    assert all(candidate["requires_confirmation"] is True for candidate in decision["candidates"])
    assert clarification["kind"] == "dataset_choice"
    assert dispatch is None


def test_low_confidence_candidate_requires_confirmation_without_dispatch(db_session, sample_dataset):
    """低置信只返回候选确认，不直接进入 DatasetAgent。"""

    _add_current_manifest(
        db_session,
        dataset_id=sample_dataset.id,
        dataset_name="订单销售",
        domain="销售运营",
        description="订单销售数据集用于门店经营分析。",
    )

    decision = route_dataset_for_question(db_session, "库存周转率是多少")
    schema_status = check_schema_status(db_session, decision)
    clarification = build_clarification(decision, schema_status)
    dispatch = build_subagent_dispatch(
        question="库存周转率是多少",
        route_decision=decision,
        time_context={},
        thread_context={},
        schema_status=schema_status,
        manifest_guard={"status": "ok"},
    )

    assert decision["decision"] == "no_match"
    assert decision["dataset_id"] is None
    assert _candidate_keys(decision) == [CAPABILITY_CANDIDATE_KEYS]
    assert decision["candidates"][0]["requires_confirmation"] is True
    assert clarification["kind"] == "dataset_missing"
    assert dispatch is None


def test_no_current_manifest_returns_no_match_without_candidates(db_session):
    """没有 current manifest 时无法回答数据集归属，候选为空。"""

    decision = route_dataset_for_question(db_session, "最近30日GMV趋势如何")

    assert decision["decision"] == "no_match"
    assert decision["dataset_id"] is None
    assert decision["candidates"] == []


def test_entry_router_requires_dataset_before_query_graph():
    """未选定数据集时，入口路由不能仅凭指标词进入 QueryGraph。"""

    result = _classify_entry_intent(
        db=None,
        question="最近30日GMV趋势如何",
        intent="query",
        entities={"metrics": ["GMV"]},
        dataset_id=None,
        history=[],
        multiturn_context={},
        clarification_response=None,
        lead_agent_context={},
    )

    assert result["entry_intent"] == "clarification"
    assert result["entry_route"] == "clarify"
    assert result["route_payload"] == {
        "kind": "clarification",
        "missing": ["dataset"],
    }


def test_route_block_answer_uses_capability_candidate_summary():
    """聊天阻断提示只读取 capability 候选摘要字段。"""

    from app.api.chat import _route_block_answer

    answer = _route_block_answer(
        {
            "decision": "no_match",
            "candidates": [
                {
                    "dataset_id": 1,
                    "dataset_name": "订单销售",
                    "reason": "未命中 manifest 中的稳定路由证据。",
                    "confidence": 0.2,
                    "requires_confirmation": True,
                }
            ],
        }
    )

    assert "订单销售" in answer
    assert "置信度 0.2" in answer
    assert "得分" not in answer
