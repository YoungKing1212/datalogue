# ============================================================
# File Name   : bi_worker_agent.py
# Description:
#   为 AgentScope Service 中的 BI Worker 装配最小化工具集。
#
# Responsibilities:
#   - 移除通用工作区、任务和后台控制工具，避免其 Schema 进入智能问数模型上下文。
#   - 仅保留 BI Worker 查询链路与 TeamSay 所需的工具。
#
# Author      : yangkai
# Created On  : 2026-07-15
# ============================================================

from __future__ import annotations

from agentscope.agent import Agent
from agentscope.tool import Toolkit

# BI Worker 只需要候选数据集、渐进式查询和团队回传；通用文件/任务工具既无业务必要，
# 还会在每轮模型调用重复注入冗长 Schema，必须在 Service 组装完成后立即剔除。
BI_WORKER_ALLOWED_TOOL_NAMES = frozenset(
    {
        "TeamSay",
        "datalogue_select_candidate_datasets",
        "datalogue_prepare_query_context",
        "datalogue_request_schema_slice",
        "datalogue_describe_tables",
        "datalogue_execute_query_plan_bundle",
        "datalogue_repair_query_plan",
    }
)


def build_bi_worker_toolkit(toolkit: Toolkit) -> Toolkit:
    """从 Service 的通用 Toolkit 投影出 BI Worker 可见的最小工具集。"""

    tools_by_name = {}
    for group in toolkit.tool_groups:
        for tool in group.tools:
            if tool.name in BI_WORKER_ALLOWED_TOOL_NAMES:
                # 同名工具沿用 AgentScope 后注册覆盖前注册的语义，避免过滤后改变运行时调用目标。
                tools_by_name[tool.name] = tool
    # 不保留非 basic ToolGroup，reset_tools 不会被自动注册，模型也无需为无关工具做激活决策。
    return Toolkit(tools=list(tools_by_name.values()))


class DatalogueRuntimeAgent(Agent):
    """在官方 AgentScope Service 中为 Datalogue BI Worker 收窄运行时工具。"""

    def __init__(self, *, name: str, toolkit: Toolkit | None = None, **kwargs) -> None:
        if name == "bi-worker" and toolkit is not None:
            toolkit = build_bi_worker_toolkit(
                toolkit
            )  # BI Worker 不继承通用 coding/planning 工具。
        super().__init__(name=name, toolkit=toolkit, **kwargs)
