# ============================================================
# File Name   : bi_worker_context.py
# Description:
#   BI Worker 渐进式上下文 Provider。
#
# Responsibilities:
#   - 从数据集元数据中生成 L0-L3 分层安全上下文。
#   - 控制不同层级可暴露的信息，避免 SQL、完整 schema 或业务数据行进入工具响应。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.agentscope_service.bi_worker_contracts import (
    DatasetCapabilityContext,
    QueryAssetContext,
    SchemaSliceContext,
    ValueProfileContext,
)
from app.models.dataset import SemanticDataset, SourceColumn, SourceTable


_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _tokens(text: str | None) -> set[str]:
    """中英文粗粒度切词，用于只依赖元数据的相关性召回。"""

    if not text:
        return set()
    tokens: set[str] = set()
    for part in _WORD_RE.findall(str(text).lower()):
        tokens.add(part)
        # 中文没有空格，补充二元片段能覆盖“员工姓名”“工作日志”这类短语匹配。
        if any("\u4e00" <= char <= "\u9fff" for char in part):
            tokens.update(part[index : index + 2] for index in range(max(len(part) - 1, 0)))
    return {token for token in tokens if token}


def _matches(question: str, candidates: list[str | None]) -> bool:
    question_text = (question or "").lower()
    question_tokens = _tokens(question)
    for candidate in candidates:
        if not candidate:
            continue
        candidate_text = str(candidate).lower()
        if candidate_text and (candidate_text in question_text or question_text in candidate_text):
            return True
        if question_tokens & _tokens(candidate_text):
            return True
    return False


def _first_text(*values: str | None) -> str | None:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return None


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


class BIWorkerContextProvider:
    """基于 Datalogue 元数据提供 BI Worker L0-L3 渐进式上下文。"""

    def __init__(self, db: Session):
        self._db = db

    def describe_dataset_capability(self, dataset_id: int, question: str) -> DatasetCapabilityContext:
        dataset = self._get_dataset(dataset_id)
        tables = self._source_tables(dataset)
        columns = self._source_columns(tables)

        key_dimensions = self._business_labels(columns, roles={"dimension", "time", "identifier"})
        key_metrics = self._business_labels(columns, roles={"metric", "measure"})
        if not key_metrics:
            key_metrics = ["记录数量"]

        supported_questions = self._supported_questions(dataset, tables, key_dimensions[:3])
        summary_parts = [dataset.name]
        if dataset.description:
            summary_parts.append(dataset.description)
        if supported_questions:
            summary_parts.append(f"可支持：{'、'.join(supported_questions[:3])}")

        return DatasetCapabilityContext(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            business_domain=dataset.description,
            supported_questions=supported_questions,
            key_metrics=key_metrics[:8],
            key_dimensions=key_dimensions[:8],
            summary="；".join(summary_parts),
        )

    def recall_query_assets(self, dataset_id: int, question: str) -> QueryAssetContext:
        dataset = self._get_dataset(dataset_id)
        tables = self._matched_tables(dataset, question)
        assets = []
        for table in tables:
            # L1 只召回资产级信息，不展开字段清单或 SQL，避免把 schema 直接注入规划层。
            assets.append(
                {
                    "asset_type": "table",
                    "name": table.table_name,
                    "schema": table.schema_name,
                    "description": _first_text(
                        table.effective_desc,
                        table.user_description,
                        table.ai_description,
                        table.table_comment,
                        table.business_desc,
                    ),
                    "match_reason": "question_metadata_match",
                }
            )

        return QueryAssetContext(
            dataset_id=dataset.id,
            question=question,
            assets=assets,
            summary=f"已召回 {len(assets)} 个与问题相关的数据资产。",
        )

    def request_schema_slice(
        self,
        dataset_id: int,
        question: str,
        focus: dict[str, Any] | None = None,
    ) -> SchemaSliceContext:
        dataset = self._get_dataset(dataset_id)
        focus = focus or {}
        tables = self._matched_tables(dataset, question, focus)
        entities = []
        for table in tables:
            columns = self._matched_columns(table, question, focus)
            if not columns:
                columns = list(table.columns[: min(len(table.columns), 5)])
            # L2 允许暴露相关物理表/字段名，但只返回切片，不返回完整建表语句或数据内容。
            entities.append(
                {
                    "asset_ref": f"table:{table.schema_name}.{table.table_name}",
                    "table": table.table_name,
                    "schema": table.schema_name,
                    "description": _first_text(
                        table.effective_desc,
                        table.user_description,
                        table.ai_description,
                        table.table_comment,
                        table.business_desc,
                    ),
                    "fields": [
                        {
                            "name": column.column_name,
                            "data_type": column.data_type,
                            "description": _first_text(
                                column.effective_desc,
                                column.user_description,
                                column.ai_description,
                                column.column_comment,
                                column.business_desc,
                            ),
                            "semantic_role": column.user_semantic_role
                            or column.ai_semantic_role
                            or column.semantic_role,
                        }
                        for column in columns[:8]
                    ],
                }
            )

        relationships = self._relationships(entities)
        return SchemaSliceContext(
            dataset_id=dataset.id,
            entities=entities,
            relationships=relationships,
            summary=f"已返回 {len(entities)} 个实体的相关 schema 切片。",
        )

    def profile_candidate_values(
        self,
        dataset_id: int,
        question: str,
        probes: list[dict[str, Any]],
    ) -> ValueProfileContext:
        dataset = self._get_dataset(dataset_id)
        tables = self._source_tables(dataset)
        profiles = []
        for probe in probes:
            table_name = str(probe.get("table") or "")
            column_name = str(probe.get("column") or probe.get("field") or "")
            table = self._find_table(tables, table_name)
            column = self._find_column(table, column_name) if table else None
            probe_values = _json_list(probe.get("values"))
            # L3 只说明探针是否能在元数据中定位，不访问业务数据内容。
            profiles.append(
                {
                    "table": table.table_name if table else table_name,
                    "field": column.column_name if column else column_name,
                    "matched": bool(table and column),
                    "coverage": "metadata_only",
                    "probe_value_count": len(probe_values),
                    "question_match": bool(
                        column
                        and _matches(
                            question,
                            [
                                column.column_name,
                                column.column_comment,
                                column.effective_desc,
                                column.user_description,
                                *[str(item) for item in _json_list(column.suggested_synonyms)],
                            ],
                        )
                    ),
                    "safe_note": "仅基于元数据确认候选值探针覆盖情况。",
                }
            )

        return ValueProfileContext(
            dataset_id=dataset.id,
            profiles=profiles,
            summary=f"已生成 {len(profiles)} 个候选值探针画像。",
        )

    def _get_dataset(self, dataset_id: int) -> SemanticDataset:
        dataset = self._db.get(SemanticDataset, dataset_id)
        if dataset is None:
            raise ValueError("DATASET_NOT_FOUND")
        return dataset

    def _source_tables(self, dataset: SemanticDataset) -> list[SourceTable]:
        return [
            link.source_table
            for link in dataset.selected_tables
            if link.source_table is not None and link.source_table.status != "deleted"
        ]

    def _source_columns(self, tables: list[SourceTable]) -> list[SourceColumn]:
        return [column for table in tables for column in table.columns]

    def _matched_tables(
        self,
        dataset: SemanticDataset,
        question: str,
        focus: dict[str, Any] | None = None,
    ) -> list[SourceTable]:
        focus_text = " ".join(str(value) for value in (focus or {}).values())
        matched = []
        for table in self._source_tables(dataset):
            column_texts = [
                " ".join(
                    filter(
                        None,
                        [
                            column.column_name,
                            column.column_comment,
                            column.effective_desc,
                            column.user_description,
                            " ".join(str(item) for item in _json_list(column.suggested_synonyms)),
                        ],
                    )
                )
                for column in table.columns
            ]
            column_text = " ".join(
                text
                for text in column_texts
                if text
            )
            if _matches(
                f"{question} {focus_text}",
                [
                    table.table_name,
                    table.table_comment,
                    table.effective_desc,
                    table.user_description,
                    table.ai_description,
                    table.business_desc,
                    column_text,
                ],
            ):
                matched.append(table)
        return matched or self._source_tables(dataset)[:3]

    def _matched_columns(
        self,
        table: SourceTable,
        question: str,
        focus: dict[str, Any],
    ) -> list[SourceColumn]:
        focus_text = " ".join(str(value) for value in focus.values())
        matched = []
        for column in table.columns:
            if _matches(
                f"{question} {focus_text}",
                [
                    column.column_name,
                    column.column_comment,
                    column.effective_desc,
                    column.user_description,
                    column.ai_description,
                    column.business_desc,
                    column.user_semantic_role,
                    column.ai_semantic_role,
                    column.semantic_role,
                    *[str(item) for item in _json_list(column.suggested_synonyms)],
                ],
            ):
                matched.append(column)
        return matched

    def _business_labels(self, columns: list[SourceColumn], roles: set[str]) -> list[str]:
        labels: list[str] = []
        for column in columns:
            role = (column.user_semantic_role or column.ai_semantic_role or column.semantic_role or "").lower()
            if roles and role and role not in roles:
                continue
            label = _first_text(column.column_comment, column.effective_desc, column.user_description)
            if label and label not in labels:
                labels.append(label)
        if labels:
            return labels
        for column in columns:
            label = _first_text(column.column_comment, column.effective_desc, column.user_description)
            if label and label not in labels:
                labels.append(label)
        return labels

    def _supported_questions(
        self,
        dataset: SemanticDataset,
        tables: list[SourceTable],
        dimensions: list[str],
    ) -> list[str]:
        questions = []
        if dataset.description:
            questions.append(dataset.description)
        for table in tables[:3]:
            desc = _first_text(table.table_comment, table.effective_desc, table.user_description)
            if desc:
                questions.append(f"围绕{desc}进行查询")
        if dimensions:
            questions.append(f"按{'、'.join(dimensions[:3])}分析")
        return questions[:6]

    def _relationships(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(entities) < 2:
            return []
        primary = entities[0]["asset_ref"]
        return [
            {
                "relationship_ref": f"dataset_selected:{primary}->{entity['asset_ref']}",
                "left_asset_ref": primary,
                "right_asset_ref": entity["asset_ref"],
                "relationship_type": "dataset_selected_together",
                "description": "这些实体属于同一语义数据集，可作为后续规划的候选关联资产。",
            }
            for entity in entities[1:]
        ]

    def _find_table(self, tables: list[SourceTable], table_name: str) -> SourceTable | None:
        lowered = table_name.lower()
        for table in tables:
            if table.table_name.lower() == lowered or f"{table.schema_name}.{table.table_name}".lower() == lowered:
                return table
        return None

    def _find_column(self, table: SourceTable, column_name: str) -> SourceColumn | None:
        lowered = column_name.lower()
        for column in table.columns:
            if column.column_name.lower() == lowered:
                return column
        return None
