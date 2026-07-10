# ============================================================
# File Name   : dataset_query.py
# Description:
#   BI Agent 的 Dataset 查询 Skill。
#
# Responsibilities:
#   - 组装 BI Toolkit、Dataset Toolchain 和 AgentScope Dataset bridge。
#   - 向 BI Agent 暴露可注册能力摘要，不暴露 SQL/schema/raw rows/query plan。
#   - 保持 Skill 层只做编排，不直接执行查询或读取私有 SQL。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.domains.bi.toolkit import DatalogueBIAtomicToolkit, build_bi_atomic_toolkit
from app.domains.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge


class DatasetQuerySkill:
    """BI Agent 注册 Dataset 查询能力的 Skill 包装；只组装受控工具链。"""

    skill_name = "dataset_query"

    def __init__(
        self,
        *,
        db: Session,
        query_executor: Callable[[str], Any] | None = None,
    ) -> None:
        self.db = db
        self.query_executor = query_executor

    def build_toolkit(self) -> DatalogueBIAtomicToolkit:
        return build_bi_atomic_toolkit(self.db, query_executor=self.query_executor)

    def build_runtime_bridge(
        self,
        *,
        toolkit: DatalogueBIAtomicToolkit | None = None,
    ) -> AgentScopeDatasetRuntimeBridge:
        return AgentScopeDatasetRuntimeBridge(toolkit=toolkit or self.build_toolkit())

    def capability_manifest(self) -> dict[str, Any]:
        toolkit = self.build_toolkit()
        return {
            "skill_name": self.skill_name,
            "tool_names": toolkit.tool_names,
            "toolkit_provider": "DatalogueBIAtomicToolkit",
            "exposes_internal_sql": False,
            "exposes_schema": False,
            "exposes_row_data": False,
            "returns_artifact_refs": True,
        }
