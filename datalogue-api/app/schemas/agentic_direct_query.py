# ============================================================
# File Name   : agentic_direct_query.py
# Description:
#   AgenticLeadAgent 直连问数 API 契约。
#
# Responsibilities:
#   - 定义直连问数入口请求 DTO，限制只接收业务入口字段。
#   - 定义直连链路安全响应 DTO，避免返回 SQL、schema、raw rows 等内部执行态。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_UNSAFE_SUMMARY_RE = re.compile(
    r"(?i)\b(sql|select|insert|update|delete|drop|alter|create|with|schema|schema[-_\s]*context|"
    r"raw[_\s-]*rows|"
    r"compiled[_\s-]*query[_\s-]*ref|compiled[_\s-]*query|query[_\s-]*plan|physical[_\s-]*plan)\b"
)
_REDACTED_SUMMARY = "查询已完成，结果摘要因包含内部执行信息已被隐藏。"


def sanitize_public_summary(summary: Any) -> str | None:
    """过滤直连 API 可见摘要，避免 SQL/schema/raw rows 等内部执行态外泄。"""

    if summary is None:
        return None
    text = str(summary).strip()
    if not text:
        return None
    if _UNSAFE_SUMMARY_RE.search(text):
        return _REDACTED_SUMMARY
    return text


class AgenticDirectQueryRequest(BaseModel):
    """直连问数请求；conversation_id/trace_id 仅作为调用方上下文，不承载内部执行 payload。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    dataset_id: int = Field(gt=0)
    conversation_id: int | None = None
    trace_id: str | None = None
    model_config_id: int | None = Field(default=None, gt=0)


class AgenticDirectQueryResponse(BaseModel):
    """直连问数安全响应；只暴露最终摘要、引用和统计数量。"""

    model_config = ConfigDict(extra="forbid")

    status: str
    selected_agent: str
    summary: str | None = None
    artifact_ref: str | None = None
    checkpoint_ref: str | None = None
    row_count: int | None = None
    column_count: int | None = None
