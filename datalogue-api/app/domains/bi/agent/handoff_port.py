# ============================================================
# File Name   : handoff_port.py
# Description:
#   BI Agent handoff 可替换端口。
#
# Responsibilities:
#   - 定义 Host Adapter 与 AgentScope native handoff 的共同接口。
#   - 让 BIAgentHandoffService 只依赖 D2 安全结果契约，不依赖具体运行时实现。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import Protocol

from app.core.schemas.bi_agent import BIAgentHandoffRequest, BIAgentHandoffResult


class BIHandoffPort(Protocol):
    """BI Agent 到 DatasetAgent 的 handoff 端口；实现方必须只返回安全 D2 结果。"""

    async def query_dataset(
        self,
        request: BIAgentHandoffRequest,
        *,
        task_id: str | None,
    ) -> BIAgentHandoffResult:
        """执行已确认的数据集查询交接，禁止透出 SQL/schema/raw rows/DSL 等执行层内部态。"""
