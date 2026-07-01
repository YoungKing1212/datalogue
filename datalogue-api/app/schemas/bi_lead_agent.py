# ============================================================
# File Name   : bi_lead_agent.py
# Description:
#   BI LeadAgent K1 对外请求、响应、handoff 和能力清单契约。
#
# Responsibilities:
#   - 定义 LeadAgent 路由、用户确认、DatasetAgent handoff 的 Pydantic DTO。
#   - 约束用户可见和跨 Agent 传递字段，避免 DatasetAgent 内部执行上下文外泄。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


BILeadAgentCapabilityStatus = Literal["enabled", "disabled"]
BILeadAgentRunPhase = Literal["route_run", "confirm_run", "handoff_run", "summarize_run"]
BILeadAgentRunStatus = Literal[
    "created",
    "waiting_confirmation",
    "running",
    "completed",
    "blocked",
    "failed",
    "cancelled",
]
BIHandoffStatus = Literal[
    "created",
    "accepted",
    "running",
    "waiting_child",
    "completed",
    "blocked",
    "failed",
    "cancelled",
]


class BILeadAgentCapability(BaseModel):
    """LeadAgent 可调度能力声明；disabled 项用于显式表达 K1 暂不开放的能力边界。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: BILeadAgentCapabilityStatus
    disabled_reason: str | None = None
    replacement: str | None = None


class DatasetCapabilitySummary(BaseModel):
    """数据集路由级摘要，只保留业务能力字段，不承载 schema、SQL、DSL 等内部上下文。"""

    model_config = ConfigDict(extra="forbid")

    dataset_id: int
    name: str
    domain: str | None = None
    supported_questions: list[str] = Field(default_factory=list)
    key_metrics: list[str] = Field(default_factory=list)
    key_dimensions: list[str] = Field(default_factory=list)
    freshness: str | None = None
    availability: str | None = None


class CreateBILeadAgentRunRequest(BaseModel):
    """创建 LeadAgent run 的入口请求。"""

    model_config = ConfigDict(extra="forbid")

    question: str
    trace_id: str | None = None
    task_id: str | None = None


class ConfirmBILeadAgentRunRequest(BaseModel):
    """用户确认单数据集路由后进入 handoff 的请求。"""

    model_config = ConfigDict(extra="forbid")

    dataset_id: int
    confirmed_question: str
    task_goal: str
    capability_snapshot: DatasetCapabilitySummary
    routing_rationale: str
    risk_notice: str | None = None
    user_decision: Literal["approved", "rejected"]


class BILeadAgentHandoffRequest(BaseModel):
    """LeadAgent 向 DatasetAgent 发起单数据集任务移交的内部契约。"""

    model_config = ConfigDict(extra="forbid")

    dataset_id: int
    confirmed_question: str
    task_goal: str
    user_confirmation_id: int
    routing_rationale: str
    trace_id: str
    parent_run_id: str


class BILeadAgentHandoffResult(BaseModel):
    """DatasetAgent handoff 结果摘要；只回传引用和统计摘要，不回传执行明细。"""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    parent_agent: Literal["bi_lead_agent"] = "bi_lead_agent"
    child_agent: Literal["dataset_agent"] = "dataset_agent"
    child_run_id: str | None = None
    dataset_id: int
    task_id: str | None = None
    trace_id: str
    handoff_status: BIHandoffStatus
    answer_summary: str | None = None
    artifact_ref: str | None = None
    checkpoint_ref: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    status_reason: str | None = None
    error_code: str | None = None
    error_summary: str | None = None


class BILeadAgentRunResponse(BaseModel):
    """LeadAgent run 查询响应，统一表达当前阶段、确认记录和 handoff 摘要。"""

    model_config = ConfigDict(extra="forbid")

    run_id: int
    status: BILeadAgentRunStatus
    phase: BILeadAgentRunPhase
    question: str
    trace_id: str
    task_id: str | None = None
    confirmation_id: int | None = None
    handoff: BILeadAgentHandoffResult | None = None
    status_reason: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
