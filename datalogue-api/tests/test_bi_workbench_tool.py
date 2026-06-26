# ============================================================
# File Name   : test_bi_workbench_tool.py
# Description:
#   ask_bi / BIWorkbenchTool 最小契约测试。
#
# Responsibilities:
#   - 验证 ask_bi 返回稳定外层响应。
#   - 验证 ArtifactCard、event envelope 和 refs 不泄漏控制面字段。
#   - 验证自定义 handler 仍被响应 schema 约束。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from app.schemas.bi_workbench import AskBIRequest
from app.services.bi_workbench_tool import BIWorkbenchTool, ask_bi


def test_ask_bi_returns_stable_outer_contract():
    response = ask_bi(
        AskBIRequest(
            question="查询杨凯 2024 年工作日志",
            conversation_id=1,
            caller="chat",
            confirmed_dataset_id=12,
            context_refs=[],
            request_options={},
        )
    )

    dumped = response.model_dump_json()
    assert response.task_id
    assert response.status in {"completed", "waiting_user", "blocked", "error"}
    assert response.event_envelope
    assert response.answer is not None
    assert response.artifact_card.primary_ref.ref == response.primary_ref.ref
    assert "raw_sql" not in dumped
    assert "raw_result" not in dumped
    assert "control_plane" not in dumped
    assert "capsule" not in dumped


def test_bi_workbench_tool_accepts_injected_safe_handler():
    def handler(request: AskBIRequest):
        base = ask_bi(request)
        return base.model_copy(update={"answer": "handler answer"})

    response = BIWorkbenchTool(handler=handler).ask_bi(
        AskBIRequest(question="查销售额", confirmed_dataset_id=3)
    )

    assert response.answer == "handler answer"
    assert response.primary_ref.ref.startswith("artifact:bi_answer:")
