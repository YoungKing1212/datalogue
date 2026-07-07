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
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
)

from app.prompts.agent_team import (
    AUDIT_WORKER_PROMPT,
    BI_WORKER_PROMPT,
    LEADER_AGENT_SYSTEM_PROMPT,
    PYTHON_WORKER_PROMPT,
    REPORT_WORKER_PROMPT,
)

LEADER_AGENT_NAME = "Datalogue Agent Team Leader"


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

        kwargs = {}
        if self.worker_type == "bi":
            kwargs = {
                # BI worker 是业务查询 worker，不应该继承 leader 的文件工作区权限，否则缺 dataset_id 时会走 Glob/Read 探测并卡在确认。
                "permission_context": _bi_worker_permission_context(),
                "override_leader_mode": True,
                "extend_leader_permission_rules": False,
                "extend_leader_working_directories": False,
            }
        return SubAgentTemplate(
            type=self.worker_type,
            description=f"{self.display_name}：{self.description}",
            system_prompt_template=self.system_prompt_template,
            **kwargs,
        )


def _bi_worker_permission_context() -> PermissionContext:
    """BI worker 的权限上下文：只放行团队汇报和 Datalogue Dataset 查询，其他未匹配工具一律拒绝。"""

    return PermissionContext(
        mode=PermissionMode.DONT_ASK,
        allow_rules={
            # 查询工具按合并后的职责授权；worker 仍不能继承 leader 的文件/命令权限。
            "datalogue_prepare_query_context": [
                PermissionRule(
                    tool_name="datalogue_prepare_query_context",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_search_assets": [
                PermissionRule(
                    tool_name="datalogue_search_assets",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_request_schema_slice": [
                PermissionRule(
                    tool_name="datalogue_request_schema_slice",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_execute_query_plan_bundle": [
                PermissionRule(
                    tool_name="datalogue_execute_query_plan_bundle",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_repair_query_plan": [
                PermissionRule(
                    tool_name="datalogue_repair_query_plan",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            # 缺 dataset_id 时，BI worker 只能通过这个安全工具筛选候选卡，不允许读文件或扫描工作区。
            "datalogue_select_candidate_datasets": [
                PermissionRule(
                    tool_name="datalogue_select_candidate_datasets",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            # worker 完成、失败或缺参时必须能回报 leader，否则会被 DONT_ASK 阻断。
            "TeamSay": [
                PermissionRule(
                    tool_name="TeamSay",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
        },
    )


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
