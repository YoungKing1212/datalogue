# ============================================================
# File Name   : dataset_query_executor.py
# Description:
#   AgentScope Service 中 BI worker 的 Dataset 查询适配器。
#
# Responsibilities:
#   - 复用 Datalogue BI 原子 Toolkit、AgentScope Dataset bridge 和 BI runtime context。
#   - 为 BI worker 的 Dataset 查询适配提供安全结果摘要，不暴露查询语句、表结构或明细行。
#   - 保持本文件只做适配，不实例化旧直连 runner 或 handoff adapter。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal


@dataclass(frozen=True)
class AgentTeamDatasetQueryResult:
    """BI worker 工具可返回给 AgentScope 的安全结果形状。"""

    answer_summary: str
    artifact_ref: str | None
    checkpoint_ref: str | None
    row_count: int | None
    column_count: int | None

    def to_tool_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        # Worker 需要把这个结构化 payload 原样 TeamSay 给 Leader；前端依赖 result_ref/artifact_card 弹出结果详情卡。
        payload.update(
            {
                "datalogue_event_type": "dataset_query_result",
                "summary": self.answer_summary,
                "result_ref": self.artifact_ref,
                "artifact_card": _artifact_card_payload(
                    answer_summary=self.answer_summary,
                    artifact_ref=self.artifact_ref,
                    checkpoint_ref=self.checkpoint_ref,
                    row_count=self.row_count,
                    column_count=self.column_count,
                ),
            }
        )
        return payload


async def execute_dataset_query_for_agent_team_direct_fallback(
    *,
    db: Session | None = None,
    dataset_id: int,
    confirmed_question: str,
    task_goal: str | None = None,
    user_confirmation_id: str | None = None,
    routing_rationale: str | None = None,
    trace_id: str | None = None,
    parent_run_id: str | None = None,
) -> AgentTeamDatasetQueryResult:
    """显式 fallback：仅在 progressive runtime 被关闭或回滚时使用旧 direct query。"""

    del task_goal, user_confirmation_id, routing_rationale, parent_run_id
    if db is None:
        with SessionLocal() as scoped_db:
            try:
                result = await _execute_dataset_query_with_db(
                    db=scoped_db,
                    dataset_id=dataset_id,
                    confirmed_question=confirmed_question,
                    trace_id=trace_id,
                )
                # AgentScope worker 自己创建 DB session 时，返回给 SSE 的 artifact_ref 必须先提交，否则详情接口会读不到产物。
                scoped_db.commit()
                return result
            except Exception:
                scoped_db.rollback()
                raise
    return await _execute_dataset_query_with_db(
        db=db,
        dataset_id=dataset_id,
        confirmed_question=confirmed_question,
        trace_id=trace_id,
    )


async def _execute_dataset_query_with_db(
    *,
    db: Session,
    dataset_id: int,
    confirmed_question: str,
    trace_id: str | None,
) -> AgentTeamDatasetQueryResult:
    """委托 BIWorkerQueryRuntime 执行 fallback 查询。"""
    from app.domains.bi.worker.runtime import BIWorkerQueryRuntime

    runtime = BIWorkerQueryRuntime(db)
    result = await runtime.execute_fallback(
        dataset_id=dataset_id,
        confirmed_question=confirmed_question,
        trace_id=trace_id,
    )
    return AgentTeamDatasetQueryResult(
        answer_summary=result.answer_summary,
        artifact_ref=result.artifact_ref,
        checkpoint_ref=result.checkpoint_ref,
        row_count=result.row_count,
        column_count=result.column_count,
    )


def _artifact_card_payload(
    *,
    answer_summary: str,
    artifact_ref: str | None,
    checkpoint_ref: str | None,
    row_count: int | None,
    column_count: int | None,
) -> dict[str, Any] | None:
    """构造用户可见结果卡，只携带引用和行列数，不携带 SQL、schema 或 raw rows。"""

    if not artifact_ref:
        return None
    return {
        "artifact_type": "bi_answer",
        "title": "查询结果",
        "status": "completed",
        "summary_for_chat": answer_summary,
        "preview_payload": {
            "row_count": row_count or 0,
            "column_count": column_count or 0,
        },
        "primary_ref": {
            "ref_id": artifact_ref,
            "ref_type": "result",
            "label": "查询结果",
        },
        "related_refs": [
            {
                "ref_id": checkpoint_ref,
                "ref_type": "checkpoint",
                "label": "查询检查点",
            }
        ]
        if checkpoint_ref
        else [],
        "actions": [
            {
                "action_type": "view",
                "label": "查看详情",
                "ref": artifact_ref,
                "disabled": False,
            },
            {
                "action_type": "export",
                "label": "导出",
                "ref": artifact_ref,
                "disabled": True,
            },
        ],
    }
