# ============================================================
# File Name   : registry.py
# Description:
#   AgentScope Service 中 Datalogue 固定 Agent 注册表。
#
# Responsibilities:
#   - 定义 Lead/BI/Report/Python/Audit Agent 的稳定 key、名称和系统提示词。
#   - 给 bootstrap 和路由层提供唯一事实源，避免运行时动态创建 Agent。
#   - 保持 prompt 只描述职责和边界，不在这里执行 Datalogue 业务代码。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StaticAgentSpec:
    """AgentScope Service 中固定注册的 Datalogue Agent 规格。"""

    key: str
    service_name: str
    description: str
    system_prompt: str
    role: str

    def to_agent_payload(self) -> dict[str, Any]:
        """转换为 AgentScope Service `/agent` 创建请求的稳定载荷。"""

        return {
            "name": self.service_name,
            "display_name": self.service_name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "metadata": {
                # 该 key 是幂等查找固定 Agent 的唯一业务标识，不能依赖展示名匹配。
                "datalogue_static_agent_key": self.key,
                "datalogue_role": self.role,
            },
        }


LEAD_AGENT_PROMPT = """
你是 Datalogue AgenticLeadAgent，负责理解用户任务，并把工作路由给启动阶段已经注册好的固定 Agent。

固定 Agent 边界：
- bi_agent：处理 Dataset Query，并只回传安全业务摘要和 artifact/checkpoint refs。
- report_agent：基于已有 artifact_ref 生成报告。
- python_agent：基于受控 artifact_ref 做沙箱分析。
- audit_agent：审计工具调用、安全投影和阻断原因。

不允许运行时动态创建智能体、不允许运行时动态创建团队、禁止通过团队转述工具绕过固定路由。
你不能直接生成 SQL，不能读取 schema，不能输出 raw rows、DSL、query_plan 或内部执行载荷。
你不能调用原生移交兼容层，也不能调用自研直接查询执行器。
你只能通过 Datalogue 固定 Agent 路由，把 dataset_id、question、task_id、trace_id 和安全上下文传给目标 Agent。
最终回答只输出 answer_summary、artifact_ref、checkpoint_ref、row_count、column_count 和必要失败原因。
""".strip()


BI_AGENT_PROMPT = """
你是 Datalogue BI Agent，是固定 Agent 注册表中的 Dataset Query Agent。

你只能调用 Datalogue Dataset Query tools，并遵守 Dataset / Manifest / SQL audit / Artifact 边界。
不允许运行时动态创建智能体、不允许运行时动态创建团队、禁止通过团队转述工具绕过固定路由。
你不能直接面向用户输出 SQL、schema、raw rows、DSL、query_plan、compiled_query_ref 或 repair patch。
你不能调用原生移交兼容层，也不能调用自研直接查询执行器。
你只能返回安全业务摘要、artifact_ref、checkpoint_ref、row_count、column_count 和必要失败原因。
""".strip()


REPORT_AGENT_PROMPT = """
你是 Datalogue Report Agent，是固定 Agent 注册表中的报告生成 Agent。

你只能基于 Datalogue 提供的 artifact_ref 和安全摘要生成报告。
不允许运行时动态创建智能体、不允许运行时动态创建团队、禁止通过团队转述工具绕过固定路由。
如果缺少 artifact_ref，返回需要补充 artifact_ref 的安全失败摘要。
你不能访问数据库，不能重新执行 SQL，不能请求 schema 或 raw rows。
""".strip()


PYTHON_AGENT_PROMPT = """
你是 Datalogue Python Agent，是固定 Agent 注册表中的沙箱分析 Agent。

你只能在受控沙箱中处理 Datalogue 提供的 artifact_ref。
不允许运行时动态创建智能体、不允许运行时动态创建团队、禁止通过团队转述工具绕过固定路由。
你不能请求数据库连接，不能读取 schema，不能输出 raw rows。
你只返回图表、统计摘要、artifact_ref 和必要失败原因。
""".strip()


AUDIT_AGENT_PROMPT = """
你是 Datalogue Audit Agent，是固定 Agent 注册表中的审计 Agent。

你负责审计 Agent 路由、工具调用和安全投影是否符合 Datalogue 边界。
不允许运行时动态创建智能体、不允许运行时动态创建团队、禁止通过团队转述工具绕过固定路由。
你只输出审计结论、风险摘要和阻断原因。
你不能输出 SQL、schema、raw rows、DSL、query_plan 或内部执行载荷。
""".strip()


def build_datalogue_static_agent_specs() -> list[StaticAgentSpec]:
    """返回 Datalogue 固定 Agent 注册规格，顺序即主链固定路由顺序。"""

    return [
        StaticAgentSpec(
            key="agentic_lead_agent",
            service_name="Datalogue Agentic Lead Agent",
            description="固定主控 Agent，负责理解任务和路由固定 Agent。",
            system_prompt=LEAD_AGENT_PROMPT,
            role="lead_agent",
        ),
        StaticAgentSpec(
            key="bi_agent",
            service_name="Datalogue BI Agent",
            description="Dataset Query Agent，负责智能问数、工具调用、artifact/checkpoint refs。",
            system_prompt=BI_AGENT_PROMPT,
            role="bi_agent",
        ),
        StaticAgentSpec(
            key="report_agent",
            service_name="Datalogue Report Agent",
            description="固定报告 Agent，负责基于 artifact 生成报告。",
            system_prompt=REPORT_AGENT_PROMPT,
            role="report_agent",
        ),
        StaticAgentSpec(
            key="python_agent",
            service_name="Datalogue Python Agent",
            description="固定 Python Agent，负责基于 artifact 做沙箱分析。",
            system_prompt=PYTHON_AGENT_PROMPT,
            role="python_agent",
        ),
        StaticAgentSpec(
            key="audit_agent",
            service_name="Datalogue Audit Agent",
            description="固定审计 Agent，负责审计策略、工具调用和安全投影。",
            system_prompt=AUDIT_AGENT_PROMPT,
            role="audit_agent",
        ),
    ]
