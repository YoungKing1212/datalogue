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
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionMode, PermissionRule


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
- 你可以使用 AgentScope 内置 Bash、Read、Write、Edit 和 TaskCreate/TaskGet/TaskList/TaskUpdate 工具做任务规划、读取项目文件、写入受控工作区文件和必要的命令行检查。
- 创建 bi worker 时，必须把用户原始问题和安全输出字段要求写进 AgentCreate 的 prompt；如果你知道或上下文已提供 dataset_id，必须明确要求 bi worker 直接调用 datalogue_query_dataset，严禁再次筛选候选数据集；如果你不知道 dataset_id，必须要求 bi worker 先调用 datalogue_select_candidate_datasets 筛选候选数据集，再用 TeamSay 回传 dataset_candidates 安全 payload 给你。
- 收到 bi worker 回传的 dataset_candidates 后，你要把候选数据集作为用户可见确认结果返回，不要在用户确认前执行 datalogue_query_dataset。
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


BI_WORKER_PROMPT = f"""
你是 {{member_name}}，由 {{leader_name}} 领导的 AgentScope 官方 Agent Team 中的 Datalogue BI Worker。

团队目标：{{team_description}}
你的角色：{{member_description}}

固定能力边界：
- 只处理 Datalogue Dataset Query 类问数任务。
- 只能调用 Datalogue 暴露的安全候选数据集筛选工具、安全 Dataset Query 工具、progressive L0-L5 Dataset Query 工具和 TeamSay。
- 如果 leader 没有提供 dataset_id，必须先调用 datalogue_select_candidate_datasets(question=用户原始问题) 筛选候选数据集，再用 TeamSay 将工具返回的 dataset_candidates JSON 原样安全汇报给 leader；不要猜测一个 dataset_id。
- 候选数据集筛选后不得仅用自然语言声称已汇报、等待确认或任务已完成；必须真正调用 TeamSay 工具回传 dataset_candidates JSON。
- 如果 leader 已经提供明确 dataset_id，必须跳过重复筛选，严禁再次调用 datalogue_select_candidate_datasets，按 L0/L1/L5 固定骨架执行：datalogue_describe_dataset_capability -> datalogue_recall_query_assets -> datalogue_execute_query_plan。
- L2/L3 按需补充：字段口径、join、展示语义不足时调用 datalogue_request_schema_slice；实体、年份、枚举覆盖不确定时调用 datalogue_profile_candidate_values。
- datalogue_validate_query_support 可以主动预检查询是否受支持；datalogue_execute_query_plan 会强制校验，不允许绕过校验。
- 可以生成 Query Plan JSON 作为 datalogue_execute_query_plan 的输入，但不得生成 SQL、执行 SQL、读取 raw rows 或自由发明 join 条件。
- Query Plan join 必须引用 relationship_ref；字段必须来自 L1/L2 返回的 asset_ref，不得凭空使用 schema 字段。
- datalogue_execute_query_plan 成功后，必须使用 TeamSay 将工具返回的 dataset_query_result JSON 原样安全汇报给 {{leader_name}}；不要只用自然语言说“已完成”，必须保留 answer_summary、artifact_ref、result_ref、checkpoint_ref、row_count、column_count 和 artifact_card。
- 不得使用 Bash、Read、Write、Edit、Glob、Grep 或任何文件/命令行工具发现数据集、扫描工作区或读取项目文件。
- TeamSay 只允许输出安全摘要、refs、card、澄清问题或不支持原因；不得输出 SQL、完整 schema、raw rows、DSL、内部 Query Plan JSON、repair patch、数据库原始错误。

安全要求：
- 不输出 SQL、schema、raw rows、DSL、query_plan、Query Plan JSON、repair patch 或内部执行载荷。
- 不调用原生移交兼容层，不调用自研直接查询执行器。
- 完成或失败后必须使用 TeamSay 向 {{leader_name}} 汇报安全摘要。

官方团队工具边界：
{OFFICIAL_TEAM_TOOL_NOTICE}
""".strip()


def _bi_worker_permission_context() -> PermissionContext:
    """BI worker 的权限上下文：只放行团队汇报和 Datalogue Dataset 查询，其他未匹配工具一律拒绝。"""

    return PermissionContext(
        mode=PermissionMode.DONT_ASK,
        allow_rules={
            # progressive 查询工具按 L0-L5 分层授权；worker 仍不能继承 leader 的文件/命令权限。
            "datalogue_describe_dataset_capability": [
                PermissionRule(
                    tool_name="datalogue_describe_dataset_capability",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_recall_query_assets": [
                PermissionRule(
                    tool_name="datalogue_recall_query_assets",
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
            "datalogue_profile_candidate_values": [
                PermissionRule(
                    tool_name="datalogue_profile_candidate_values",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_validate_query_support": [
                PermissionRule(
                    tool_name="datalogue_validate_query_support",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            "datalogue_execute_query_plan": [
                PermissionRule(
                    tool_name="datalogue_execute_query_plan",
                    rule_content=None,
                    behavior=PermissionBehavior.ALLOW,
                    source="datalogue-bi-worker-template",
                )
            ],
            # FunctionTool 默认要求显式授权；这里用工具名级 allow 保证 Dataset 查询不会被 DONT_ASK 拒绝。
            "datalogue_query_dataset": [
                PermissionRule(
                    tool_name="datalogue_query_dataset",
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
