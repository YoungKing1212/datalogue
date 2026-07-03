# ============================================================
# File Name   : react_factory.py
# Description:
#   BI Agent 的 AgentScope 2.0 Agent 工厂。
#
# Responsibilities:
#   - 创建真正的 AgentScope BI Agent。
#   - 直接注册 Dataset 工具链 tools，不经过 DatasetQuerySkill。
#   - 用 prompt 约束问数工具调用顺序和安全输出。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from agentscope.agent import Agent
from agentscope.tool import ToolBase, Toolkit
from sqlalchemy.orm import Session

from app.agents.agentscope_model import build_agentscope_chat_model
from app.bi.skill.runtime_bridge import (
    AgentScopeDatasetRuntimeSession,
    build_dataset_agentscope_tools,
)


BI_AGENT_DIRECT_QUERY_PROMPT = """
你是 Datalogue BI Agent，负责执行最小直连问数链路。

你必须按顺序使用已注册工具：
1. get_dataset_status
2. list_candidate_assets
3. compile_dsl_to_sql
4. execute_compiled_query
5. create_query_artifact
6. get_artifact_summary

如果 execute_compiled_query 返回 FIELD_NOT_FOUND，并且工具链允许 repair，则调用 repair_dsl 后再次 execute_compiled_query。

你必须遵守：
- 不向最终回答输出 SQL。
- 不向最终回答输出 schema。
- 不向最终回答输出 raw rows。
- 不向最终回答输出 compiled_query_ref。
- 最终只总结业务结果，并引用 artifact_ref、checkpoint_ref、row_count、column_count。
""".strip()


class BIAgentFactory:
    """创建 AgentScope 2.0 BI Agent；Dataset tools 直接挂在 BI Agent 上。"""

    def __init__(self, *, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        session: AgentScopeDatasetRuntimeSession,
        model_config_id: int | None = None,
    ) -> Agent:
        tools: list[ToolBase] = list(
            build_dataset_agentscope_tools(
                session=session,
                agent_name="bi_agent",
            )
        )  # Dataset tools 绑定当前 runtime session，避免跨会话复用候选资产和私有执行句柄。
        return Agent(
            name="bi_agent",
            system_prompt=BI_AGENT_DIRECT_QUERY_PROMPT,
            model=build_agentscope_chat_model(
                db=self.db,
                role="lead_agent",
                stream=True,
                model_config_id=model_config_id,
            ),
            toolkit=Toolkit(tools=tools),
        )
