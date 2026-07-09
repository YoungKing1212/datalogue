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

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from agentscope.app import SubAgentTemplate
from agentscope.permission import (
    PermissionContext,
    PermissionMode,
)

from app.prompts.agent_team import (
    AUDIT_WORKER_PROMPT,
    BI_WORKER_PROMPT,
    LEADER_AGENT_SYSTEM_PROMPT,
    PYTHON_WORKER_PROMPT,
    REPORT_WORKER_PROMPT,
)

logger = logging.getLogger(__name__)

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


def _load_bi_worker_permission_context() -> PermissionContext:
    """从外部 JSON 文件加载 BI Worker 权限上下文，便于运维修改。"""
    conf_path = Path(__file__).resolve().parent.parent.parent.parent / "conf" / "bi_worker_permissions.json"
    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PermissionContext.model_validate(data)
    except FileNotFoundError:
        logger.warning(f"BI Worker 权限配置文件未找到: {conf_path}，使用默认 fail-closed 配置")
        return PermissionContext(mode=PermissionMode.DONT_ASK)


def _bi_worker_permission_context() -> PermissionContext:
    """BI worker 的权限上下文：只放行团队汇报和 Datalogue Dataset 查询，其他未匹配工具一律拒绝。"""
    return _load_bi_worker_permission_context()


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
