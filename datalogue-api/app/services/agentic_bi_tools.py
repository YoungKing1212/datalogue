# ============================================================
# File Name   : agentic_bi_tools.py
# Description:
#   Agentic Shell-first AS-R0 的 BI 原子工具提供器。
#
# Responsibilities:
#   - 提供 Agentic Shell 可白名单化的最小 BI 原子工具骨架。
#   - 暴露数据集状态、候选资产目录和 artifact 摘要等安全结构。
#   - 保证 SQL、schema 全量、物理字段明细和 raw rows 不进入 Agent 上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.dataset import AnalysisBlueprint, SemanticDataset
from app.services.agentic_shell import DatalogueAgenticShell
from app.services.artifact_store import ArtifactStore


class BIAtomicToolProvider:
    """BI 主链原子工具集合；AS-R0 先提供安全契约和只读目录摘要。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._sanitizer = DatalogueAgenticShell()

    def get_dataset_status(self, dataset_id: int) -> dict[str, Any]:
        dataset = self._get_dataset(dataset_id)
        if dataset is None:
            return {
                "dataset_id": dataset_id,
                "status": "not_found",
                "metadata_schema_summary": {"selected_table_count": 0},
            }
        return {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "status": dataset.status,
            "metric_count": len(dataset.metrics or []),
            "dimension_count": len(dataset.dimensions or []),
            "blueprint_count": len(dataset.blueprints or []),
            "metadata_schema_summary": self._metadata_schema_summary(dataset),
        }

    def list_candidate_assets(
        self,
        dataset_id: int,
        *,
        question: str | None = None,
    ) -> dict[str, Any]:
        dataset = self._get_dataset(dataset_id)
        if dataset is None:
            return {
                "dataset_id": dataset_id,
                "question_used": False,
                "status": "not_found",
                "blueprint": [],
                "metric": [],
                "dimension": [],
                "metadata_schema_summary": {"selected_table_count": 0},
            }
        # AS-R0 第一阶段没有向量库；question 参数只保留接口兼容，不参与召回或排序。
        catalog = {
            "dataset_id": dataset.id,
            "question_used": False,
            "blueprint": [self._blueprint_summary(item) for item in self._sorted_blueprints(dataset)],
            "metric": [
                {
                    "id": metric.id,
                    "name": metric.display_name or metric.name,
                    "description": metric.description,
                    "synonyms": metric.synonyms or [],
                }
                for metric in sorted(dataset.metrics or [], key=lambda item: item.id or 0)
            ],
            "dimension": [
                {
                    "id": dimension.id,
                    "name": dimension.display_name or dimension.name,
                    "synonyms": dimension.synonyms or [],
                    "enum_values": dimension.enum_values or [],
                }
                for dimension in sorted(dataset.dimensions or [], key=lambda item: item.id or 0)
            ],
            "metadata_schema_summary": self._metadata_schema_summary(dataset),
        }
        return self._sanitizer.sanitize_output(catalog)

    def compile_dsl_to_sql(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """预留工具边界；SQL 只能在该工具内部流转，AS-R0 P0 不开放实现。"""

        raise NotImplementedError("compile_dsl_to_sql is reserved for DatasetAgent Runtime wiring")

    def execute_compiled_query(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """预留工具边界；执行结果必须先落 artifact，不能把 raw rows 返回给 Agent。"""

        raise NotImplementedError("execute_compiled_query is reserved for DatasetAgent Runtime wiring")

    def create_query_artifact(
        self,
        *,
        payload: Any,
        dataset_id: int | None = None,
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, str]:
        # 写入前复用 Shell 输出清洗，确保 artifact 入口不会被 Agent 旁路塞入内部执行载荷。
        sanitized_payload = self._sanitizer.sanitize_output(payload)
        artifact_ref = ArtifactStore(self.db).put_json(
            kind="sql_result",
            payload=sanitized_payload,
            dataset_id=dataset_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )
        return {"artifact_ref": artifact_ref}

    def get_artifact_summary(self, artifact_ref: str) -> dict[str, Any]:
        artifact = ArtifactStore(self.db).get(artifact_ref)
        if artifact is None:
            return {"artifact_ref": artifact_ref, "status": "not_found"}
        summary = {
            "artifact_ref": artifact.artifact_id,
            "kind": artifact.kind,
            "content_mime": artifact.content_mime,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        }
        return self._sanitizer.sanitize_output(summary)

    def _get_dataset(self, dataset_id: int) -> SemanticDataset | None:
        return (
            self.db.query(SemanticDataset)
            .filter(SemanticDataset.id == dataset_id)
            .one_or_none()
        )

    @staticmethod
    def _metadata_schema_summary(dataset: SemanticDataset) -> dict[str, int]:
        # 只返回计数级 metadata summary，不返回表名、字段名、DDL 或 schema 主体。
        return {"selected_table_count": len(dataset.selected_tables or [])}

    @staticmethod
    def _sorted_blueprints(dataset: SemanticDataset) -> list[AnalysisBlueprint]:
        return sorted(dataset.blueprints or [], key=lambda item: item.id or 0)

    @staticmethod
    def _blueprint_summary(blueprint: AnalysisBlueprint) -> dict[str, Any]:
        return {
            "id": blueprint.id,
            "name": blueprint.name,
            "description": blueprint.description,
            "trigger_keywords": blueprint.trigger_keywords or [],
            "when_to_use": blueprint.when_to_use,
        }
