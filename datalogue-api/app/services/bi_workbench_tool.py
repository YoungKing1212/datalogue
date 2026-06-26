# ============================================================
# File Name   : bi_workbench_tool.py
# Description:
#   ask_bi / BIWorkbenchTool 最小能力入口。
#
# Responsibilities:
#   - 为 AgentScope Shell Adapter 提供第一阶段唯一 BI 调用入口。
#   - 生成稳定的 answer、event envelope、ArtifactCard 和 refs 外层契约。
#   - 保持第一阶段只做协议验证，不接管 Chat / LeadAgent 主链 runtime。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.schemas.bi_workbench import (
    ArtifactAction,
    ArtifactCard,
    ArtifactRef,
    AskBIRequest,
    AskBIResponse,
    DatalogueEventEnvelope,
    EventVisibility,
    sanitize_outer_payload,
)


AskBIHandler = Callable[[AskBIRequest], AskBIResponse | dict[str, Any]]


class BIWorkbenchTool:
    """BI 工作台能力入口；当前只提供 contract-first 的 ask_bi 验证壳。"""

    def __init__(self, handler: AskBIHandler | None = None) -> None:
        self.handler = handler

    def ask_bi(self, request: AskBIRequest) -> AskBIResponse:
        if self.handler is not None:
            result = self.handler(request)
            return result if isinstance(result, AskBIResponse) else AskBIResponse(**result)
        return self._build_minimal_response(request)

    def _build_minimal_response(self, request: AskBIRequest) -> AskBIResponse:
        task_id = f"ask_bi_{uuid4().hex}"
        primary_ref = ArtifactRef(
            ref=f"artifact:bi_answer:{task_id}",
            kind="answer",
            title="BI 查询结果摘要",
        )
        answer = f"已受理问数请求：{request.question}"
        artifact_card = ArtifactCard(
            title="BI 查询结果",
            summary_for_chat=answer,
            primary_ref=primary_ref,
            preview_payload={
                "question": request.question,
                "confirmed_dataset_id": request.confirmed_dataset_id,
                "source": "ask_bi_contract",
            },
            actions=[
                ArtifactAction(
                    action_type="export",
                    label="导出",
                    enabled=False,
                    disabled_reason="第一阶段仅验证引用和边界，不生成导出文件。",
                )
            ],
        )
        event = DatalogueEventEnvelope(
            event_type="answer.completed",
            task_id=task_id,
            conversation_id=request.conversation_id,
            visibility=EventVisibility.USER_VISIBLE,
            payload=sanitize_outer_payload(
                {
                    "answer": answer,
                    "artifact_card": artifact_card.model_dump(mode="json"),
                    "primary_ref": primary_ref.model_dump(mode="json"),
                }
            ),
        )
        return AskBIResponse(
            task_id=task_id,
            event_envelope=event,
            answer=answer,
            artifact_card=artifact_card,
            primary_ref=primary_ref,
            related_refs=[],
            status="completed",
        )


def ask_bi(request: AskBIRequest | dict[str, Any]) -> AskBIResponse:
    """模块级便捷入口；Shell Adapter 注入自定义 handler 时可绕过此默认实现。"""

    parsed_request = request if isinstance(request, AskBIRequest) else AskBIRequest(**request)
    # 第一阶段默认实现只返回安全外层契约，避免在 AgentScope 验证线里误触发主链副作用。
    return BIWorkbenchTool().ask_bi(parsed_request)
