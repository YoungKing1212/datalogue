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

from typing import Any

from agentscope.agent import Agent
from agentscope.tool import Toolkit
from sqlalchemy.orm import Session

from app.agents.agentscope_model import build_agentscope_chat_model
from app.agentscope_service.tools import build_datalogue_query_dataset_tool


BI_AGENT_DIRECT_QUERY_PROMPT = """
你是 Datalogue 固定注册 BI Agent，负责执行已确认的数据集问数任务。

你只能使用 datalogue_query_dataset 这个工具。

你必须遵守：
- 工具入参只放 dataset_id、confirmed_question、task_goal、user_confirmation_id、routing_rationale、trace_id、parent_run_id。
- 不向最终回答输出查询语句。
- 不向最终回答输出数据结构。
- 不向最终回答输出明细行。
- 最终只总结业务结果，并引用 artifact_ref、checkpoint_ref、row_count、column_count。
""".strip()


class BIAgentFactory:
    """创建 AgentScope 2.0 BI Agent；只注册固定 Dataset 查询工具。"""

    def __init__(self, *, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        session: Any | None = None,
        model_config_id: int | None = None,
    ) -> Agent:
        del session  # 固定工具内部由 Datalogue 适配器创建隔离执行会话，避免把私有状态暴露给 Agent。
        return Agent(
            name="bi_agent",
            system_prompt=BI_AGENT_DIRECT_QUERY_PROMPT,
            model=build_agentscope_chat_model(
                db=self.db,
                role="lead_agent",
                stream=True,
                model_config_id=model_config_id,
            ),
            toolkit=Toolkit(tools=[build_datalogue_query_dataset_tool()]),
        )
