# ============================================================
# File Name   : test_term_clarification_service.py
# Description:
#   Phase 4 `resolve_term_clarification` 服务层 28 个单测。
#   覆盖：5 状态机全分支（none/missing/expired/unresolved/resolved）+
#   6 种解析路径（selected_term_id / selected_index / selected_text /
#   ordinal_zh / ordinal_digit / display_name / alias）+
#   数据隔离（dataset_id 过滤 / clarification_id 过滤 / None 兼容）+
#   DB 副作用（selected_payload 写入 / expired 标记 / 不变 pending 状态）+
#   Pydantic/dict 输入兼容 + tracer span emit + 9 字段契约。
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, PendingClarification
from app.services.lead_agent_routing import (
    parse_clarification_response,
    resolve_term_clarification,
    term_candidate_matches_text,
    term_format_clarification_answer,
    term_latest_pending_clarification,
    term_resolve_clarification_candidate,
    term_response_selected_index,
)


# ============================================================
# 公共 fixture helpers
# ============================================================


def _make_conv(db_session, sample_dataset) -> Conversation:
    """创建一个测试用 Conversation。"""
    conv = Conversation(
        title="术语澄清测试",
        thread_id="thread-term-clarification",
        dataset_id=sample_dataset.id,
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


def _make_pending_term_clarification(
    db_session: Session,
    conv: Conversation,
    sample_dataset,
    *,
    candidates: list[dict] | None = None,
    expires_in_minutes: int = 30,
    original_question: str = "销售额是多少",
    clarification_id: int | None = None,
    dataset_id: int | None = None,
) -> PendingClarification:
    """创建一个术语澄清挂起态。"""
    if candidates is None:
        candidates = [
            {
                "index": 1,
                "term_id": 1,
                "name": "gmv",
                "display_name": "GMV",
                "definition": "商品交易总额",
                "aliases": ["成交额"],
            },
            {
                "index": 2,
                "term_id": 2,
                "name": "paid_amount",
                "display_name": "实付金额",
                "definition": "用户实际支付金额",
                "aliases": ["支付金额"],
            },
        ]
    expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
    pending = PendingClarification(
        id=clarification_id,
        conversation_id=conv.id,
        dataset_id=dataset_id if dataset_id is not None else sample_dataset.id,
        clarification_type="term_conflict",
        status="pending",
        original_question=original_question,
        conflict_payload={"kind": "term_conflict_clarification"},
        candidates=candidates,
        expires_at=expires_at,
    )
    db_session.add(pending)
    db_session.commit()
    db_session.refresh(pending)
    return pending


# ============================================================
# 1. 状态机：none（5 个测试）
# ============================================================


def test_resolve_none_when_no_pending_no_response(db_session, sample_dataset):
    """状态机 none：无挂起且无回复。"""
    result = resolve_term_clarification(
        db=db_session,
        question="查 GMV",
        conversation_id=1,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    assert result["status"] == "none"
    assert result["selected_term_id"] is None
    assert result["resolved_question"] is None
    assert result["answer"] is None
    assert result["entry_intent"] is None
    assert result["entry_route"] is None
    assert result["entry_reason"] is None
    assert result["route_payload"] == {}
    assert result["clarification_resolution_result"] == {"status": "none"}


def test_resolve_none_when_empty_dict_response(db_session, sample_dataset):
    """空 dict 响应等价于 None → none。"""
    result = resolve_term_clarification(
        db=db_session,
        question="查 GMV",
        conversation_id=1,
        dataset_id=sample_dataset.id,
        clarification_response={},
    )
    assert result["status"] == "none"


# ============================================================
# 2. 状态机：missing（1 个测试）
# ============================================================


def test_resolve_missing_with_response_but_no_pending(db_session, sample_dataset):
    """状态机 missing：有回复但找不到挂起 → 拒答。"""
    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=99999,  # 不存在的会话
        dataset_id=sample_dataset.id,
        clarification_response={"selected_term_id": 1},
    )
    assert result["status"] == "missing"
    assert result["answer"] == "没有找到待处理的术语澄清，请重新提出完整问题。"
    assert result["entry_intent"] == "clarification"
    assert result["entry_route"] == "clarify"
    assert result["entry_reason"] == "没有找到待处理的术语澄清态。"
    assert result["route_payload"] == {"kind": "term_conflict_missing"}
    assert result["clarification_resolution_result"] == {"status": "missing"}


# ============================================================
# 3. 状态机：expired（3 个测试）
# ============================================================


def test_resolve_expired_marks_status_and_returns_expired(db_session, sample_dataset):
    """状态机 expired：lazy mark expired + commit + 拒答。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset, expires_in_minutes=-1,
    )

    result = resolve_term_clarification(
        db=db_session,
        question="第一个",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )

    assert result["status"] == "expired"
    assert result["answer"] == "术语澄清已过期，请重新提出完整问题。"
    assert result["route_payload"]["kind"] == "term_conflict_expired"
    assert result["route_payload"]["clarification_id"] == pending.id
    assert result["clarification_resolution_result"]["status"] == "expired"
    assert result["clarification_resolution_result"]["clarification_id"] == pending.id

    db_session.refresh(pending)
    assert pending.status == "expired"


def test_resolve_expired_via_clarification_id_filter(db_session, sample_dataset):
    """expired 配合 clarification_id 过滤。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset,
        expires_in_minutes=-1,
        clarification_id=42,
    )
    result = resolve_term_clarification(
        db=db_session,
        question="第一个",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"clarification_id": 42},
    )
    assert result["status"] == "expired"
    db_session.refresh(pending)
    assert pending.status == "expired"


def test_resolve_expired_pending_status_not_resolved(db_session, sample_dataset):
    """expired 后 pending.status='expired'，绝不会是 'resolved'。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset, expires_in_minutes=-5,
    )
    resolve_term_clarification(
        db=db_session,
        question="第一个",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    db_session.refresh(pending)
    assert pending.status != "resolved"
    assert pending.status == "expired"


# ============================================================
# 4. 状态机：unresolved（3 个测试）
# ============================================================


def test_resolve_unresolved_keeps_pending_and_returns_unresolved(db_session, sample_dataset):
    """状态机 unresolved：候选未匹配 → 保持 pending + 重新提示。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="都不是",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )

    assert result["status"] == "unresolved"
    assert "1. GMV" in result["answer"]
    assert "2. 实付金额" in result["answer"]
    assert result["entry_intent"] == "clarification"
    assert result["entry_route"] == "clarify"
    assert result["entry_reason"] == "用户澄清回复未能匹配候选术语。"
    assert result["route_payload"]["kind"] == "term_conflict_clarification"
    assert result["route_payload"]["clarification_id"] == pending.id
    assert len(result["route_payload"]["candidates"]) == 2
    assert result["clarification_resolution_result"]["status"] == "unresolved"

    db_session.refresh(pending)
    assert pending.status == "pending"  # unresolved 不会改 pending.status


def test_resolve_unresolved_via_structured_selected_index_out_of_range(db_session, sample_dataset):
    """unresolved：结构化 selected_index 越界（候选只有 1 项，selected_index=99）。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(
        db_session, conv, sample_dataset,
        candidates=[{"index": 1, "term_id": 1, "name": "gmv", "display_name": "GMV"}],
    )
    result = resolve_term_clarification(
        db=db_session,
        question="选第 99 个",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"selected_index": 99},
    )
    assert result["status"] == "unresolved"
    assert result["route_payload"]["kind"] == "term_conflict_clarification"


def test_resolve_unresolved_route_payload_includes_candidates_with_count(db_session, sample_dataset):
    """unresolved route_payload.candidates 完整且包含原顺序。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset,
        candidates=[
            {"index": 1, "term_id": 1, "name": "gmv", "display_name": "GMV", "definition": "商品交易总额"},
            {"index": 2, "term_id": 2, "name": "paid_amount", "display_name": "实付金额", "definition": "用户实际支付金额"},
        ],
    )
    result = resolve_term_clarification(
        db=db_session,
        question="都是",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    assert result["status"] == "unresolved"
    assert result["route_payload"]["clarification_id"] == pending.id
    assert len(result["route_payload"]["candidates"]) == 2


# ============================================================
# 5. 状态机：resolved（6 个测试）
# ============================================================


def test_resolve_resolved_via_selected_term_id(db_session, sample_dataset):
    """resolved via selected_term_id 结构化精确匹配。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"clarification_id": pending.id, "selected_term_id": 1},
    )

    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 1
    assert result["resolved_question"] == "销售额是多少"
    assert result["answer"] is None
    assert result["route_payload"]["kind"] == "term_conflict_resolved"
    assert result["route_payload"]["selected_term_id"] == 1
    assert result["clarification_resolution_result"]["status"] == "resolved"

    db_session.refresh(pending)
    assert pending.status == "resolved"
    assert pending.selected_payload["term_id"] == 1
    assert pending.selected_payload["source"] == "structured"


def test_resolve_resolved_via_ordinal_text_zh(db_session, sample_dataset):
    """resolved via 自然语言『第一个』。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="第一个",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 1

    db_session.refresh(pending)
    assert pending.selected_payload["source"] == "natural_language"


def test_resolve_resolved_via_ordinal_text_digit(db_session, sample_dataset):
    """resolved via 自然语言『2』。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="2",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 2


def test_resolve_resolved_via_display_name(db_session, sample_dataset):
    """resolved via 自然语言展示名。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="实付金额",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 2
    assert result["clarification_resolution_result"]["selected_term"]["display_name"] == "实付金额"


def test_resolve_resolved_via_alias(db_session, sample_dataset):
    """resolved via 自然语言 alias。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="成交额",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 1


def test_resolve_resolved_via_selected_text_in_response(db_session, sample_dataset):
    """resolved via clarification_response.selected_text 自然语言。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="都行",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"selected_text": "支付金额"},
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 2


# ============================================================
# 6. 数据隔离：dataset_id / clarification_id 过滤（3 个测试）
# ============================================================


def test_resolve_dataset_id_filter_isolates_pending(db_session, sample_dataset):
    """dataset_id 过滤：dataset 匹配的 pending 被选中。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset, dataset_id=sample_dataset.id,
    )
    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"selected_term_id": 1},
    )
    assert result["status"] == "resolved"
    assert result["clarification_resolution_result"]["clarification_id"] == pending.id


def test_resolve_pending_with_dataset_id_none_still_matches(db_session, sample_dataset):
    """dataset_id=None 的 pending 兼容匹配（query 包含 dataset_id 过滤 + dataset_id IS NULL）。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset, dataset_id=None,
    )
    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"selected_term_id": 1},
    )
    assert result["status"] == "resolved"
    assert result["clarification_resolution_result"]["clarification_id"] == pending.id


def test_resolve_clarification_id_mismatch_returns_missing(db_session, sample_dataset):
    """clarification_id 错配 → missing 状态。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(
        db_session, conv, sample_dataset, clarification_id=10,
    )
    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"clarification_id": 999, "selected_term_id": 1},
    )
    assert result["status"] == "missing"
    assert result["route_payload"] == {"kind": "term_conflict_missing"}


# ============================================================
# 7. Pydantic / dict 兼容（2 个测试）
# ============================================================


def test_resolve_pydantic_v2_model_dump_compat(db_session, sample_dataset):
    """Pydantic v2 对象（有 model_dump）→ 走 model_dump 路径。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)

    # 模拟 Pydantic v2 对象
    class FakePydantic:
        def model_dump(self, exclude_none=True):
            return {"selected_term_id": 1}

    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=FakePydantic(),
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 1


def test_resolve_dict_payload_with_none_values_excluded(db_session, sample_dataset):
    """dict payload 中 None 值会被排除。"""
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)

    result = resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"selected_term_id": 1, "selected_index": None, "selected_text": None},
    )
    assert result["status"] == "resolved"
    assert result["selected_term_id"] == 1


# ============================================================
# 8. DB 副作用（3 个测试）
# ============================================================


def test_resolve_resolved_writes_selected_payload_to_db(db_session, sample_dataset):
    """resolved → pending.selected_payload 写入完整结构。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(db_session, conv, sample_dataset)

    resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"selected_term_id": 1},
    )
    db_session.refresh(pending)
    assert pending.selected_payload is not None
    assert pending.selected_payload["term_id"] == 1
    assert pending.selected_payload["name"] == "gmv"
    assert pending.selected_payload["display_name"] == "GMV"
    assert pending.selected_payload["source"] == "structured"
    assert pending.resolved_at is not None


def test_resolve_expired_does_not_write_selected_payload(db_session, sample_dataset):
    """expired → pending.selected_payload 保持 None。"""
    conv = _make_conv(db_session, sample_dataset)
    pending = _make_pending_term_clarification(
        db_session, conv, sample_dataset, expires_in_minutes=-1,
    )
    resolve_term_clarification(
        db=db_session,
        question="第一个",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response=None,
    )
    db_session.refresh(pending)
    assert pending.status == "expired"
    assert pending.selected_payload is None


def test_resolve_resolved_does_not_touch_other_pending(db_session, sample_dataset):
    """resolved → 同会话其他 pending 状态不变（只动命中的那条）。"""
    conv = _make_conv(db_session, sample_dataset)
    pending_a = _make_pending_term_clarification(
        db_session, conv, sample_dataset, clarification_id=100,
    )
    pending_b = _make_pending_term_clarification(
        db_session, conv, sample_dataset, clarification_id=101,
    )

    resolve_term_clarification(
        db=db_session,
        question="选 GMV",
        conversation_id=conv.id,
        dataset_id=sample_dataset.id,
        clarification_response={"clarification_id": pending_a.id, "selected_term_id": 1},
    )

    db_session.refresh(pending_a)
    db_session.refresh(pending_b)
    assert pending_a.status == "resolved"
    assert pending_b.status == "pending"


# ============================================================
# 9. 字段契约（2 个测试）
# ============================================================


def test_resolve_route_payload_kind_for_each_status(db_session, sample_dataset):
    """route_payload.kind 与 status 一一对应。"""
    # none
    r_none = resolve_term_clarification(
        db=db_session, question="q", conversation_id=1, dataset_id=1,
        clarification_response=None,
    )
    assert r_none["route_payload"] == {}

    # missing
    r_missing = resolve_term_clarification(
        db=db_session, question="q", conversation_id=1, dataset_id=1,
        clarification_response={"selected_term_id": 1},
    )
    assert r_missing["route_payload"]["kind"] == "term_conflict_missing"

    # unresolved
    conv = _make_conv(db_session, sample_dataset)
    _make_pending_term_clarification(db_session, conv, sample_dataset)
    r_unresolved = resolve_term_clarification(
        db=db_session, question="都不是", conversation_id=conv.id,
        dataset_id=sample_dataset.id, clarification_response=None,
    )
    assert r_unresolved["route_payload"]["kind"] == "term_conflict_clarification"

    # resolved
    r_resolved = resolve_term_clarification(
        db=db_session, question="选 GMV", conversation_id=conv.id,
        dataset_id=sample_dataset.id, clarification_response={"selected_term_id": 1},
    )
    assert r_resolved["route_payload"]["kind"] == "term_conflict_resolved"


def test_resolve_answer_field_only_for_terminal_statuses(db_session, sample_dataset):
    """answer 字段仅在 missing/expired/unresolved 时填，resolved/none 时 None。"""
    # none → answer=None
    r_none = resolve_term_clarification(
        db=db_session, question="q", conversation_id=1, dataset_id=1,
        clarification_response=None,
    )
    assert r_none["answer"] is None

    # missing → answer 非空
    r_missing = resolve_term_clarification(
        db=db_session, question="q", conversation_id=1, dataset_id=1,
        clarification_response={"selected_term_id": 1},
    )
    assert r_missing["answer"] is not None


# ============================================================
# 10. tracer span emit（1 个测试）
# ============================================================


def test_resolve_tracer_span_emitted(db_session, sample_dataset):
    """tracer span 必含 input/output payload。"""
    spans = []

    class FakeTracer:
        def start_span(self, _ctx, *, node, display_name, input_payload):
            spans.append({"event": "start", "node": node, "input": input_payload})

        def end_span(self, _ctx, *, node, output_payload):
            spans.append({"event": "end", "node": node, "output": output_payload})

    fake_tracer = FakeTracer()
    fake_ctx = MagicMock()

    resolve_term_clarification(
        db=db_session,
        question="第一个",
        conversation_id=1,
        dataset_id=1,
        clarification_response={"selected_term_id": 1},
        tracer=fake_tracer,
        trace_context=fake_ctx,
    )

    start_spans = [s for s in spans if s["event"] == "start"]
    end_spans = [s for s in spans if s["event"] == "end"]
    assert len(start_spans) == 1
    assert start_spans[0]["node"] == "term_clarification_resolution"
    assert "question" in start_spans[0]["input"]
    assert len(end_spans) == 1
    assert end_spans[0]["node"] == "term_clarification_resolution"


# ============================================================
# 11. 纯函数性（不修改入参 dict）（1 个测试）
# ============================================================


def test_resolve_does_not_mutate_input_dict(db_session, sample_dataset):
    """resolve_term_clarification 不得修改入参 dict。"""
    input_response = {"selected_term_id": 1, "clarification_id": 1}
    snapshot = dict(input_response)
    resolve_term_clarification(
        db=db_session,
        question="q",
        conversation_id=1,
        dataset_id=1,
        clarification_response=input_response,
    )
    assert input_response == snapshot


# ============================================================
# 12. 辅助函数单元测试（2 个测试）
# ============================================================


def test_parse_clarification_response_handles_pydantic_dict_none():
    """parse_clarification_response 兼容 Pydantic/dict/None。"""
    assert parse_clarification_response(None) == {}
    assert parse_clarification_response({}) == {}
    assert parse_clarification_response({"a": 1, "b": None}) == {"a": 1}

    class FakePydantic:
        def model_dump(self, exclude_none=True):
            return {"x": 10}

    assert parse_clarification_response(FakePydantic()) == {"x": 10}


def test_term_helpers_work_independently(db_session, sample_dataset):
    """term_response_selected_index / term_candidate_matches_text / term_format_clarification_answer 独立可测。"""
    assert term_response_selected_index("第一个") == 1
    assert term_response_selected_index("选 2") == 2
    assert term_response_selected_index("无关文本") is None

    candidate = {"display_name": "GMV", "name": "gmv", "aliases": ["成交额"]}
    assert term_candidate_matches_text(candidate, "GMV")
    assert term_candidate_matches_text(candidate, "成交额")
    assert not term_candidate_matches_text(candidate, "无关")

    answer = term_format_clarification_answer(
        [
            {"index": 1, "name": "a", "display_name": "A", "definition": "Def A"},
            {"index": 2, "name": "b", "display_name": "B"},
        ],
        "请选择：",
    )
    assert "请选择：" in answer
    assert "1. A（Def A）" in answer
    assert "2. B" in answer
