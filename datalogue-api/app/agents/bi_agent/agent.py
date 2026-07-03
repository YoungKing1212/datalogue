# ============================================================
# File Name   : agent.py
# Description:
#   BI Agent 业务 façade。
#
# Responsibilities:
#   - 暴露 BI Agent 的能力清单和默认 Dataset 查询 Skill。
#   - 将 AgenticLeadAgent 之后的 BI 执行入口从旧 BI Agent 命名迁到新包。
#   - 保持 façade 层不读取 SQL/schema/raw rows/query plan。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from sqlalchemy.orm import Session

from app.bi.skill import DatasetQuerySkill


class BIAgent:
    """BI Agent 业务入口；当前负责注册 Dataset 查询 Skill 和暴露安全能力清单。"""

    agent_name = "bi_agent"

    def __init__(self, *, db: Session) -> None:
        self.db = db
        self.dataset_query_skill = DatasetQuerySkill(db=db)

    def capability_manifest(self) -> dict[str, object]:
        dataset_manifest = self.dataset_query_skill.capability_manifest()
        return {
            "agent_name": self.agent_name,
            "skill_names": [self.dataset_query_skill.skill_name],
            "default_skill": self.dataset_query_skill.skill_name,
            "skills": [
                {
                    "skill_name": dataset_manifest["skill_name"],
                    "tool_names": dataset_manifest["tool_names"],
                    "returns_artifact_refs": dataset_manifest["returns_artifact_refs"],
                }
            ],
            "exposes_internal_sql": False,
            "exposes_schema": False,
            "exposes_row_data": False,
        }
