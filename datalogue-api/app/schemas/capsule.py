# ============================================================
# File Name   : capsule.py
# Description:
#   多轮对话 SubAgent 状态胶囊协议。
#
# Responsibilities:
#   - 定义跨轮保存的数据集内查询上下文结构。
#   - 区分 LeadAgent 可读元字段和 SubAgent 可读写业务状态。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


CAPSULE_VERSION = "1.0"


class QueryContext(BaseModel):
    """数据集内生效的结构化查询状态，仅由 SubAgent 解读。"""

    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    time_filter: Optional[dict[str, Any]] = None
    time_range: Optional[dict[str, Any]] = None
    time_grain: Optional[str] = None
    order_by: Optional[list[dict[str, Any]]] = None
    limit: Optional[int] = None
    routing_path: Optional[Literal["blueprint", "scenario", "adhoc"]] = None
    blueprint_id: Optional[str] = None
    scenario_id: Optional[str] = None


class ResultDigest(BaseModel):
    """上一轮结果摘要，避免把全量结果放入多轮上下文。"""

    status: Literal["ok", "failed", "empty"] = "empty"
    columns: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    numeric_summary: dict[str, dict[str, float]] = Field(default_factory=dict)
    top_values: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    highlights: dict[str, Any] = Field(default_factory=dict)
    sql_audit_id: Optional[str] = None
    sql_count: int = 0
    has_answer: bool = False
    answer_preview: Optional[str] = None
    error: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SubAgentCapsule(BaseModel):
    """SubAgent 跨轮状态胶囊。

    LeadAgent 只允许读取 capsule_version、dataset_id、schema_version 和 updated_turn。
    """

    capsule_version: str = CAPSULE_VERSION
    dataset_id: str
    schema_version: str
    updated_turn: int
    query_context: Optional[QueryContext] = None
    term_resolutions: dict[str, str] = Field(default_factory=dict)
    last_result_digest: Optional[ResultDigest] = None


class CapsuleMeta(BaseModel):
    """LeadAgent 可读的胶囊元信息。"""

    capsule_version: str
    dataset_id: str
    schema_version: str
    updated_turn: int


def capsule_meta(capsule: SubAgentCapsule | dict[str, Any]) -> CapsuleMeta:
    """只暴露 LeadAgent 允许读取的胶囊元字段。"""

    raw = capsule.model_dump() if isinstance(capsule, SubAgentCapsule) else dict(capsule or {})
    return CapsuleMeta(
        capsule_version=str(raw.get("capsule_version") or ""),
        dataset_id=str(raw.get("dataset_id") or ""),
        schema_version=str(raw.get("schema_version") or ""),
        updated_turn=int(raw.get("updated_turn") or 0),
    )
