# ============================================================
# File Name   : test_lead_agent_routing.py
# Description:
#   Phase 3 LeadAgent 总入口路由（route_query_intent）11 个单测。
#   覆盖：chitchat 短路、统一 payload、蓝图/知识/permission/拒答/主链、
#   LLM 失败降级、entities 透传、tracer span、clarification_response、
#   纯函数性。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.lead_agent_routing import (
    _classify_entry_intent,
    route_query_intent,
)


def _llm_response(content: dict, usage: dict | None = None) -> MagicMock:
    """构造一个 mock LLM response。"""
    mock_response = MagicMock()
    mock_response.content = json.dumps(content)
    mock_response.usage_metadata = usage or {"input_tokens": 10, "output_tokens": 5}
    return mock_response


# ===== 1. chitchat 短路 =====


def test_route_query_intent_chitchat_short_circuits(monkeypatch):
    """chitchat 路径：LLM 不被调（直接走 rule-based chitchat 短路），返回 direct_answer。"""
    from app.services import lead_agent_routing

    # mock LLM：chitchat 路径直接被短路，但 LLM 仍会被调（route_query_intent 总是先调 LLM）
    # 测试只验证：返回 entry_intent=chitchat / entry_route=direct_answer
    monkeypatch.setattr(
        lead_agent_routing,
        "_invoke_intent_llm",
        lambda **_: ("chitchat", {}, "你好", {}),
    )
    result = route_query_intent(
        db=None,
        question="你好",
        dataset_id=None,
        lead_agent_context={},
        history=[],
        multiturn_context={},
        clarification_response=None,
    )
    assert result["entry_intent"] == "chitchat"
    assert result["entry_route"] == "direct_answer"
    assert result["answer"] == "你好"


# ===== 2. 统一 payload 11 字段 =====


def test_route_query_intent_emits_unified_payload(monkeypatch):
    """route_query_intent 必须返回 11 字段：intent/entities/entry_intent/entry_route/entry_reason/route_payload/blueprint_id/blueprint_match/knowledge_term_id/answer/token_usage。"""
    from app.services import lead_agent_routing

    monkeypatch.setattr(
        lead_agent_routing,
        "_invoke_intent_llm",
        lambda **_: ("query", {"metrics": ["gmv"]}, None, {"total_tokens": 100}),
    )
    result = route_query_intent(
        db=None,
        question="最近 30 天的 GMV",
        dataset_id=1,
        lead_agent_context={},
        history=[],
        multiturn_context={},
        clarification_response=None,
    )
    for key in (
        "intent",
        "entities",
        "entry_intent",
        "entry_route",
        "entry_reason",
        "route_payload",
        "blueprint_id",
        "blueprint_match",
        "knowledge_term_id",
        "answer",
        "token_usage",
    ):
        assert key in result, f"result 缺字段 {key}"


# ===== 3. 蓝图匹配 =====


def test_route_query_intent_blueprint_match(db_session, sample_dataset):
    """命中已发布分析蓝图时 entry_intent=analysis_blueprint + blueprint_id 正确。"""
    from app.models.dataset import AnalysisBlueprint

    from app.services import lead_agent_routing

    bp = AnalysisBlueprint(
        dataset_id=sample_dataset.id,
        name="毛利归因分析",
        trigger_keywords=["毛利", "归因"],
        status="active",
    )
    db_session.add(bp)
    db_session.commit()
    db_session.refresh(bp)

    monkeypatch_get_llm = patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response(
                    {"intent": "query", "entities": {}},
                )
            )
        ),
    )
    with monkeypatch_get_llm:
        result = route_query_intent(
            db=db_session,
            question="为什么本月毛利下降",
            dataset_id=sample_dataset.id,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
        )
    assert result["entry_intent"] == "analysis_blueprint"
    assert result["entry_route"] == "analysis_blueprint"
    assert result["blueprint_id"] == bp.id
    assert result["route_payload"]["blueprint_id"] == bp.id


# ===== 4. 知识库问答 =====


def test_route_query_intent_knowledge_qa(db_session, sample_dataset):
    """命中业务术语时 entry_intent=knowledge_qa + knowledge_term_id 正确。"""
    from app.models.dataset import BusinessTerm

    from app.services import lead_agent_routing

    term = BusinessTerm(
        dataset_id=sample_dataset.id,
        name="gmv",
        display_name="GMV",
        aliases=["销售额"],
        definition="商品交易总额。",
        status="active",
    )
    db_session.add(term)
    db_session.commit()
    db_session.refresh(term)

    monkeypatch_get_llm = patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response({"intent": "query", "entities": {}})
            )
        ),
    )
    with monkeypatch_get_llm:
        result = route_query_intent(
            db=db_session,
            question="GMV 是什么口径",
            dataset_id=sample_dataset.id,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
        )
    assert result["entry_intent"] == "knowledge_qa"
    assert result["knowledge_term_id"] == term.id
    assert "商品交易总额" in result["answer"]


# ===== 5. permission 拒答 =====


def test_route_query_intent_permission_rejection():
    """命中 '权限不足' 模式 → entry_route=reject / permission_denied。"""
    from app.services import lead_agent_routing

    with patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response({"intent": "query", "entities": {}})
            )
        ),
    ):
        result = route_query_intent(
            db=None,
            question="查询权限不足的数据",
            dataset_id=1,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
        )
    assert result["entry_intent"] == "rejection"
    assert result["entry_route"] == "reject"
    assert result["route_payload"]["kind"] == "permission_denied"
    assert "权限" in result["answer"]


# ===== 6. metric 主链 =====


def test_route_query_intent_metric_query():
    """entities.metrics 命中 → entry_intent=metric_query / query_graph。"""
    from app.services import lead_agent_routing

    with patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response(
                    {
                        "intent": "query",
                        "entities": {"metrics": ["GMV"], "dimensions": ["region"]},
                    }
                )
            )
        ),
    ):
        result = route_query_intent(
            db=None,
            question="各地区 GMV",
            dataset_id=1,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
        )
    assert result["entry_intent"] == "metric_query"
    assert result["entry_route"] == "query_graph"


def test_route_query_intent_work_log_query_routes_to_detail(monkeypatch):
    """日志类查询应进入明细查询主链，不能落到默认澄清。"""
    from app.services import lead_agent_routing

    monkeypatch.setattr(
        lead_agent_routing,
        "_invoke_intent_llm",
        lambda **_: ("query", {}, None, {}),
    )

    result = route_query_intent(
        db=None,
        question="查询汤杰前年的工作日志",
        dataset_id=10,
        lead_agent_context={},
        history=[],
        multiturn_context={},
        clarification_response=None,
    )

    assert result["entry_intent"] == "detail_query"
    assert result["entry_route"] == "query_graph"
    assert result["answer"] is None


def test_route_query_intent_filter_refinement_uses_last_success_task(monkeypatch):
    """有上一轮成功查询时，姓名过滤追问应继续进入 QueryGraph。"""
    from app.services import lead_agent_routing

    monkeypatch.setattr(
        lead_agent_routing,
        "_invoke_intent_llm",
        lambda **_: ("query", {}, None, {}),
    )

    result = route_query_intent(
        db=None,
        question="我想看姓名为杨凯的",
        dataset_id=10,
        lead_agent_context={},
        history=[],
        multiturn_context={
            "raw": {
                "last_success_task": {
                    "dataset_id": 10,
                    "main_table": "plan_task_daily_record",
                    "query_type": "detail_query",
                }
            }
        },
        clarification_response=None,
    )

    assert result["entry_intent"] == "detail_query"
    assert result["entry_route"] == "query_graph"
    assert result["route_payload"]["source"] == "multiturn_filter_refinement"


# ===== 7. LLM 失败降级 =====


def test_route_query_intent_handles_llm_failure():
    """LLM 调用 raise 时：route_query_intent 降级到 rule-based 路径，不 crash。"""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("LLM service unavailable")
    with patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=mock_llm,
    ):
        # LLM 失败 → intent="query", entities={}
        # rule-based 看到 entities 空 + question="各地区 GMV" 命中 metric pattern → query_graph
        result = route_query_intent(
            db=None,
            question="各地区 GMV",
            dataset_id=1,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
        )
    assert result["intent"] == "query"
    assert result["entry_intent"] == "metric_query"
    assert result["entry_route"] == "query_graph"


# ===== 8. entities 透传 =====


def test_route_query_intent_preserves_entities_for_downstream():
    """LLM 提取的 entities 必须原样保留（供下游 term_normalize / semantic_asset_resolution 使用）。"""
    from app.services import lead_agent_routing

    captured_entities = {
        "metrics": ["GMV", "订单数"],
        "dimensions": ["门店", "省份"],
        "time_range": {"raw": "最近 30 天"},
    }
    with patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response(
                    {"intent": "query", "entities": captured_entities}
                )
            )
        ),
    ):
        result = route_query_intent(
            db=None,
            question="各门店最近 30 天的 GMV 和订单数",
            dataset_id=1,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
        )
    assert result["entities"] == captured_entities
    assert result["entities"]["metrics"] == ["GMV", "订单数"]


# ===== 9. tracer span =====


def test_route_query_intent_tracer_span_emitted():
    """tracer span 必含 input/output payload。"""
    from app.services import lead_agent_routing

    spans = []

    class FakeTracer:
        def start_span(self, _ctx, *, node, display_name, input_payload):
            spans.append({"event": "start", "node": node, "input": input_payload})

        def end_span(self, _ctx, *, node, output_payload):
            spans.append({"event": "end", "node": node, "output": output_payload})

    fake_tracer = FakeTracer()
    fake_ctx = MagicMock()

    with patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response({"intent": "chitchat", "entities": {}})
            )
        ),
    ):
        route_query_intent(
            db=None,
            question="你好",
            dataset_id=None,
            lead_agent_context={},
            history=[],
            multiturn_context={},
            clarification_response=None,
            tracer=fake_tracer,
            trace_context=fake_ctx,
        )
    start_span = next(s for s in spans if s["event"] == "start" and s["node"] == "lead_agent_routing")
    end_span = next(s for s in spans if s["event"] == "end" and s["node"] == "lead_agent_routing")
    assert start_span["input"]["question"] == "你好"
    assert end_span["output"]["entry_intent"] == "chitchat"


# ===== 10. clarification_response 处理 =====


def test_route_query_intent_consumes_multiturn_clarification():
    """clarification_response 字段被透传到 LLM human_text（不丢信息）。"""
    from app.services.lead_agent_routing import _build_human_text

    human_text = _build_human_text(
        question="销售数据集",
        history=[],
        multiturn_context={"pending_clarification": {"kind": "dataset_choice"}},
        clarification_response={"kind": "dataset_choice", "selected_dataset_id": 1},
    )
    assert "多轮提示" in human_text
    assert "dataset_choice" in human_text


# ===== 11. 纯函数性 =====


def test_route_query_intent_does_not_mutate_input():
    """route_query_intent 不得修改入参 dict（dict / list 不原地改动）。"""
    from app.services import lead_agent_routing

    input_lead_ctx = {"multiturn_classification": {"intent": "query"}}
    input_mt = {"pending_clarification": {"kind": "dataset_choice"}}
    input_history = [{"role": "user", "content": "hi"}]

    with patch(
        "app.services.lead_agent_routing.get_llm",
        return_value=MagicMock(
            invoke=MagicMock(
                return_value=_llm_response({"intent": "query", "entities": {}})
            )
        ),
    ):
        route_query_intent(
            db=None,
            question="hi",
            dataset_id=1,
            lead_agent_context=input_lead_ctx,
            history=input_history,
            multiturn_context=input_mt,
            clarification_response=None,
        )

    assert input_lead_ctx == {"multiturn_classification": {"intent": "query"}}
    assert input_mt == {"pending_clarification": {"kind": "dataset_choice"}}
    assert input_history == [{"role": "user", "content": "hi"}]
