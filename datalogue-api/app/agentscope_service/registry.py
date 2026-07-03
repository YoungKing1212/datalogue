# ============================================================
# File Name   : registry.py
# Description:
#   AgentScope Agent Team worker 模板注册表。
#
# Responsibilities:
#   - 定义 Datalogue 固定 worker 类型：bi、report、python、audit。
#   - 输出 AgentScope 官方 SubAgentTemplate，交给 AgentCreate 的 subagent_type 枚举使用。
#   - 只描述业务能力边界，不实现 Datalogue 自研 runner 或 handoff 编排。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

from agentscope.app import SubAgentTemplate


OFFICIAL_TEAM_TOOL_NOTICE = (
    "TeamCreate、AgentCreate、TeamSay、TeamDelete 只能作为 AgentScope 官方内置 Team 工具使用；"
    "Datalogue 不实现同名替代工具，不通过自研运行器或自研直接查询执行器绕过官方团队协作。"
)

LEADER_AGENT_NAME = "Datalogue Agent Team Leader"

LEADER_AGENT_SYSTEM_PROMPT = f"""
你是 Datalogue 智能问数主链的 AgentScope 官方 Agent Team Leader。

工作理念：
- 你只负责理解用户任务、创建团队、选择 worker、汇总安全结果。
- 需要 worker 时必须使用 AgentScope 官方 TeamCreate、AgentCreate、TeamSay、TeamDelete 工具。
- 固定 worker 类型只有 bi、report、python、audit；这是业务模板类型，不是固定 Agent 实例。
- 你不能调用 Datalogue 旧自研执行入口、旧 BI Agent 公开 API、自研 runner 或自研 handoff。
- 用户可见回答只包含安全摘要和 refs，不输出 SQL、schema、raw rows、DSL、query_plan 或内部修复载荷。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()


@dataclass(frozen=True)
class AgentTeamLeaderSpec:
    """Datalogue Agent Team leader 在 AgentScope Service 中的官方 Agent 身份。"""

    name: str
    system_prompt: str

    def to_agent_payload(self) -> dict[str, str]:
        """转换为 AgentScope 官方 POST /agent 可消费的最小 payload。"""

        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
        }


def build_datalogue_leader_agent_spec() -> AgentTeamLeaderSpec:
    """返回主链 leader 身份；worker 实例仍由 AgentScope AgentCreate 动态创建。"""

    return AgentTeamLeaderSpec(
        name=LEADER_AGENT_NAME,
        system_prompt=LEADER_AGENT_SYSTEM_PROMPT,
    )


@dataclass(frozen=True)
class AgentTeamWorkerTemplateSpec:
    """Datalogue 暴露给 AgentScope Agent Team 的固定 worker 类型。"""

    worker_type: str
    display_name: str
    description: str
    system_prompt_template: str

    def to_subagent_template(self) -> SubAgentTemplate:
        """转换为 AgentScope 官方 AgentCreate 可消费的 SubAgentTemplate。"""

        return SubAgentTemplate(
            type=self.worker_type,
            description=f"{self.display_name}：{self.description}",
            system_prompt_template=self.system_prompt_template,
        )


BI_WORKER_PROMPT = f"""
你是 {{member_name}}，由 {{leader_name}} 领导的 AgentScope 官方 Agent Team 中的 Datalogue BI Worker。

团队目标：{{team_description}}
你的角色：{{member_description}}

固定能力边界：
- 只处理 Datalogue Dataset Query 类问数任务。
- 只能调用 Datalogue 暴露的安全 Dataset Query 工具。
- 只能回传 answer_summary、artifact_ref、checkpoint_ref、row_count、column_count 和必要失败原因。

安全要求：
- 不输出 SQL、schema、raw rows、DSL、query_plan、repair patch 或内部执行载荷。
- 不调用原生移交兼容层，不调用自研直接查询执行器。
- 完成或失败后必须使用 TeamSay 向 {{leader_name}} 汇报安全摘要。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()


REPORT_WORKER_PROMPT = f"""
你是 {{member_name}}，由 {{leader_name}} 领导的 AgentScope 官方 Agent Team 中的 Datalogue Report Worker。

团队目标：{{team_description}}
你的角色：{{member_description}}

固定能力边界：
- 只基于已有 artifact_ref 和安全摘要生成报告内容。
- 缺少 artifact_ref 时返回需要补充 artifact_ref 的安全失败摘要。
- 不访问数据库，不重新执行 SQL，不请求 schema 或 raw rows。

汇报要求：
- 完成或失败后必须使用 TeamSay 向 {{leader_name}} 汇报报告摘要、artifact_ref 和必要失败原因。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()


PYTHON_WORKER_PROMPT = f"""
你是 {{member_name}}，由 {{leader_name}} 领导的 AgentScope 官方 Agent Team 中的 Datalogue Python Worker。

团队目标：{{team_description}}
你的角色：{{member_description}}

固定能力边界：
- 只在受控沙箱中处理 Datalogue 提供的 artifact_ref。
- 不请求数据库连接，不读取 schema，不输出 raw rows。
- 只返回图表、统计摘要、artifact_ref 和必要失败原因。

汇报要求：
- 完成或失败后必须使用 TeamSay 向 {{leader_name}} 汇报安全摘要。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()


AUDIT_WORKER_PROMPT = f"""
你是 {{member_name}}，由 {{leader_name}} 领导的 AgentScope 官方 Agent Team 中的 Datalogue Audit Worker。

团队目标：{{team_description}}
你的角色：{{member_description}}

固定能力边界：
- 审计 Agent Team worker 选择、工具调用和安全投影是否符合 Datalogue 边界。
- 只输出审计结论、风险摘要和阻断原因。
- 不输出 SQL、schema、raw rows、DSL、query_plan 或内部执行载荷。

汇报要求：
- 完成或失败后必须使用 TeamSay 向 {{leader_name}} 汇报审计结果。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()


def build_datalogue_worker_template_specs() -> list[AgentTeamWorkerTemplateSpec]:
    """返回 Datalogue 固定 worker 类型；顺序即 AgentCreate 暴露给 leader 的稳定顺序。"""

    return [
        AgentTeamWorkerTemplateSpec(
            worker_type="bi",
            display_name="Datalogue BI Worker",
            description="Dataset Query worker，负责智能问数、工具调用、artifact/checkpoint refs。",
            system_prompt_template=BI_WORKER_PROMPT,
        ),
        AgentTeamWorkerTemplateSpec(
            worker_type="report",
            display_name="Datalogue Report Worker",
            description="报告 worker，负责基于 artifact_ref 和安全摘要生成报告。",
            system_prompt_template=REPORT_WORKER_PROMPT,
        ),
        AgentTeamWorkerTemplateSpec(
            worker_type="python",
            display_name="Datalogue Python Worker",
            description="Python 沙箱 worker，负责基于 artifact_ref 做受控分析。",
            system_prompt_template=PYTHON_WORKER_PROMPT,
        ),
        AgentTeamWorkerTemplateSpec(
            worker_type="audit",
            display_name="Datalogue Audit Worker",
            description="审计 worker，负责检查工具调用、安全投影和阻断原因。",
            system_prompt_template=AUDIT_WORKER_PROMPT,
        ),
    ]


def build_datalogue_subagent_templates() -> list[SubAgentTemplate]:
    """构建 AgentScope create_app(custom_subagent_templates=...) 所需的 worker 模板。"""

    return [spec.to_subagent_template() for spec in build_datalogue_worker_template_specs()]
