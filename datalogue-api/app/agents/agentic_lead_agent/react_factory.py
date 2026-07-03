# ============================================================
# File Name   : react_factory.py
# Description:
#   AgenticLeadAgent 的 AgentScope 2.0 Agent 工厂。
#
# Responsibilities:
#   - 创建真正的 AgentScope AgenticLeadAgent。
#   - 用 prompt 约束它只做顶层路由和安全策略判断。
#   - 不向 Lead Agent 暴露查询语句、数据结构、明细行或 Dataset 原子工具。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from agentscope.agent import Agent
from agentscope.state import AgentState
from agentscope.tool import Toolkit
from sqlalchemy.orm import Session

from app.agents.agentscope_model import build_agentscope_chat_model


AGENTIC_LEAD_AGENT_DIRECT_PROMPT = """
你是 Datalogue AgenticLeadAgent，负责固定 Agent 主链的顶层路由。

当前阶段固定只启用 bi_agent；不要运行时动态创建团队或子智能体。

你必须遵守：
- 如果用户问题是问数、指标、数据查询、统计分析，只选择 bi_agent。
- 不生成查询语句。
- 不读取数据结构。
- 不输出明细行。
- 不调用 Dataset 查询工具，只做固定路由。
- 只输出简短 JSON：{"selected_agent":"bi_agent","task_type":"bi_query","reason":"..."}。
""".strip()


class AgenticLeadAgentFactory:
    """创建 AgentScope 2.0 AgenticLeadAgent；暂不注册工具，避免顶层越权执行查询。"""

    def __init__(self, *, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        state: AgentState | None = None,
        model_config_id: int | None = None,
    ) -> Agent:
        return Agent(
            name="agentic_lead_agent",
            system_prompt=AGENTIC_LEAD_AGENT_DIRECT_PROMPT,
            model=build_agentscope_chat_model(
                db=self.db,
                role="lead_agent",
                stream=False,
                model_config_id=model_config_id,
            ),
            toolkit=Toolkit(tools=[]),
            state=state,
        )
