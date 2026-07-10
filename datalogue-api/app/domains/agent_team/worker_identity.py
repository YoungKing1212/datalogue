# ============================================================
# File Name   : worker_identity.py
# Description:
#   AgentScope Team worker 类型识别。
#
# Responsibilities:
#   - 只从 AgentScope storage 中的 team agent system_prompt marker 判断 worker 类型。
#   - 为工具注册和中间件挂载提供统一 fail-closed 身份边界。
#   - 避免通过 agent_name 猜测 worker 类型导致权限旁路。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from typing import Literal

from agentscope.app.storage import StorageBase

TeamWorkerType = Literal["bi", "report"]

BI_WORKER_MARKERS = ("Datalogue BI Worker", "Dataset Query")
REPORT_WORKER_MARKERS = ("Datalogue Report Worker", "REPORT_WORKER_BOUNDARY")


async def resolve_team_worker_type(
    *,
    storage: StorageBase | None,
    user_id: str | None,
    agent_id: str | None,
) -> TeamWorkerType | None:
    """基于 system_prompt marker 识别 Team worker；不满足唯一匹配时一律返回 None。"""

    if storage is None or not user_id or not agent_id:
        return None
    agent_record = await storage.get_agent(user_id, agent_id)
    if not agent_record or agent_record.source != "team":
        return None

    agent_data = getattr(agent_record, "data", None)
    system_prompt = str(getattr(agent_data, "system_prompt", "") or "")
    matched: list[TeamWorkerType] = []
    if any(marker in system_prompt for marker in BI_WORKER_MARKERS):
        matched.append("bi")
    if any(marker in system_prompt for marker in REPORT_WORKER_MARKERS):
        matched.append("report")
    # 多 marker 或无 marker 都代表身份不可信，工具侧 fail-closed。
    return matched[0] if len(matched) == 1 else None


__all__ = [
    "BI_WORKER_MARKERS",
    "REPORT_WORKER_MARKERS",
    "TeamWorkerType",
    "resolve_team_worker_type",
]
