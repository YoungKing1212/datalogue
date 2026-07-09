# ============================================================
# File Name   : repair_plan.py
# Description:
#   RepairPlan v1 修复意图协议。
#
# Responsibilities:
#   - 定义 SQL 失败后的受控修复计划结构。
#   - 允许内部 action 携带字段/表定位，禁止用户可见摘要夹带 SQL 或 schema 细节。
#   - 为 Tool 校验、artifact 脱敏摘要和事件 envelope 提供稳定类型。
#
# Author      : yangkai
# Created On  : 2026-06-28
# ============================================================

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RepairFailureClass = Literal[
    "FIELD_NOT_FOUND",
    "FIELD_MAPPING_DRIFT",
    "TABLE_NOT_FOUND",
    "DIALECT_FUNCTION_UNSUPPORTED",
    "TYPE_ERROR",
    "PERMISSION_DENIED",
    "CONNECTION_ERROR",
    "TIMEOUT",
    "RESULT_TOO_LARGE",
    "SECURITY_RISK",
    "UNKNOWN",
]

RepairStatus = Literal[
    "evaluated",
    "plan_created",
    "confirmation_required",
    "rerun_started",
    "rerun_completed",
    "failed",
    "blocked",
]

RepairActionType = Literal[
    "replace_field",
    "replace_table",
    "replace_dialect_function",
    "cast_type",
    "diagnose_only",
    "block_repair",
]

_SQL_TEXT_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)


def _reject_visible_sql_text(text: str, *, field_name: str) -> None:
    """用户可见摘要字段不能出现 SQL 片段，RepairPlan 只表达业务修复意图。"""

    value = str(text or "")
    lowered = value.lower()
    if _SQL_TEXT_RE.search(value) or any(
        token in lowered
        for token in ("raw_sql", "raw_result", "schema_context", "control_plane")
    ):
        raise ValueError(f"{field_name} contains forbidden internal detail")


class RepairAction(BaseModel):
    """单个修复动作；target/replacement 仅供 Tool 内部校验，不进入用户可见 payload。"""

    model_config = ConfigDict(extra="forbid")

    action_type: RepairActionType
    business_summary: str
    target: dict[str, Any] = Field(default_factory=dict)
    replacement: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _reject_summary_leaks(self) -> "RepairAction":
        _reject_visible_sql_text(self.business_summary, field_name="business_summary")
        return self


class RepairPlan(BaseModel):
    """RepairPlan v1 只描述修复计划，不承载可执行 SQL。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "repair_plan.v1"
    dataset_id: int
    failure_class: RepairFailureClass
    status: RepairStatus = "evaluated"
    business_summary: str
    actions: list[RepairAction] = Field(default_factory=list)
    requires_user_confirmation: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    attempts: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _reject_visible_summary_leaks(self) -> "RepairPlan":
        if self.schema_version != "repair_plan.v1":
            raise ValueError("unsupported repair plan schema_version")
        _reject_visible_sql_text(self.business_summary, field_name="business_summary")
        return self
