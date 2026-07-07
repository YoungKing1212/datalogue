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
    """基于 Datalogue 元数据提供 BI Worker 查询上下文。"""

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
            # L2 已经拿到实体、字段和关系 ref，这里同步生成机器可合并状态，
            # 避免 Worker 从自然语言摘要反推 context_state 时写错结构。
            context_state_patch=self._context_state_patch(entities, relationships),
            context_state_usage="将 context_state_patch 合并进后续 L4/L5 的 context_state；不要从自然语言摘要手写 context_state。",
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

    def search_assets(self, dataset_id: int) -> dict[str, Any]:
        """列出数据集下所有候选蓝图、指标和维度。

        蓝图命中时可直接用 call_template（SQL 模板）构造查询，跳过渐进式探索。
        """
        dataset = self._get_dataset(dataset_id)
        blueprints = self._list_blueprints(dataset)
        metrics = self._list_metrics(dataset)
        dimensions = self._list_dimensions(dataset)
        return {
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "blueprints": blueprints,
            "blueprint_count": len(blueprints),
            "metrics": metrics,
            "metric_count": len(metrics),
            "dimensions": dimensions,
            "dimension_count": len(dimensions),
            "usage_hint": (
                "优先匹配蓝图：若某蓝图的 name/description/trigger_keywords 与用户问题相关，"
                "按其 call_template 构造 SQL，填入 parameters 要求的参数值后调用 datalogue_execute_query_plan_bundle 执行。"
                "若无蓝图匹配，再使用 datalogue_prepare_query_context → datalogue_execute_query_plan_bundle。"
                if blueprints
                else "无可用蓝图，请走 datalogue_prepare_query_context → datalogue_request_schema_slice → datalogue_execute_query_plan_bundle。"
            ),
        }

    def prepare_query_context(self, dataset_id: int, question: str) -> dict[str, Any]:
        """合并 L0+L1+蓝图：描述数据集能力、召回资产并列出蓝图快速路径。"""
        capability = self.describe_dataset_capability(dataset_id, question)
        assets = self.recall_query_assets(dataset_id, question)
        blueprint_catalog = self.search_assets(dataset_id)
        matched_assets = [
            {
                "asset_type": item.get("asset_type"),
                "name": item.get("name"),
                "schema": item.get("schema"),
                "description": item.get("description"),
                "match_reason": item.get("match_reason"),
            }
            for item in assets.assets
        ]
        suggested_filters = self._extract_filter_clues(question)
        missing_conditions: list[dict[str, Any]] = []
        if not capability.key_dimensions:
            missing_conditions.append({
                "type": "missing_dimension",
                "detail": "未发现业务维度信息，可能影响维度筛选。",
            })
        if not capability.key_metrics:
            missing_conditions.append({
                "type": "missing_metric",
                "detail": "未发现业务指标信息，可能影响指标查询。",
            })
        if not matched_assets:
            missing_conditions.append({
                "type": "no_assets_recalled",
                "detail": "未召回相关数据资产，建议调整问题描述。",
            })
        if suggested_filters:
            missing_conditions.append({
                "type": "filter_hint_unresolved",
                "detail": "问题中包含筛选条件，需要在 QueryPlan filters 中完整表达。",
                "clues": suggested_filters,
            })
        asset_coverage = "insufficient" if missing_conditions else "sufficient"
        next_step = "request_more_schema" if asset_coverage == "insufficient" else "generate_query_plan"
        return {
            "asset_coverage": asset_coverage,
            "dataset_id": capability.dataset_id,
            "dataset_name": capability.dataset_name,
            "business_domain": capability.business_domain,
            "supported_questions": capability.supported_questions[:5],
            "key_metrics": capability.key_metrics[:8],
            "key_dimensions": capability.key_dimensions[:8],
            "matched_assets": matched_assets,
            "matched_asset_count": len(matched_assets),
            "blueprints": blueprint_catalog.get("blueprints", []),
            "blueprint_count": blueprint_catalog.get("blueprint_count", 0),
            "missing_conditions": missing_conditions,
            "next_step_suggestion": next_step,
            "suggested_filters": suggested_filters,
            "context_state": {
                "asset_refs": [item["asset_type"] + ":" + item["name"] for item in matched_assets],
                "relationship_refs": [],
                "field_refs": [],
                "dataset_summary": capability.summary,
                "suggested_filters": suggested_filters,
            },
            "summary": (
                f"数据集「{capability.dataset_name}」资产覆盖{'充足' if asset_coverage == 'sufficient' else '不充分'}，"
                f"建议{'生成查询计划' if next_step == 'generate_query_plan' else '补充数据上下文'}。"
            ),
        }

    @staticmethod
    def _extract_filter_clues(question: str) -> list[dict[str, Any]]:
        """从用户问题中提取筛选线索（中文人名、年份、日期等）。

        Args:
            question: 用户原始问题。

        Returns:
            筛选线索列表，每条含 clue_type、value 和 reason。
        """
        clues: list[dict[str, Any]] = []
        # 中文人名：查询XXX的、按XXX、XXX的日志/记录
        for pattern in [
            r'查询\s*([一-龥]{2,4})\s*的',
            r'按\s*([一-龥]{2,4})\s*(?:查询|筛选|过滤)',
            r'([一-龥]{2,4})\s*(?:的日志|的记录|的订单|的数据)',
        ]:
            match = re.search(pattern, question)
            if match:
                name = match.group(1)
                clues.append({
                    "clue_type": "person_name",
                    "value": name,
                    "reason": f"用户输入的人名「{name}」应从员工姓名或相关人员字段筛选",
                })
                break
        # 年份：YYYY年 或 YYYY
        year_match = re.search(r'(\d{4})\s*年', question)
        if year_match:
            clues.append({
                "clue_type": "year",
                "value": year_match.group(1),
                "reason": f"用户输入的年份「{year_match.group(1)}」应从日期字段筛选",
            })
        # 日期范围：YYYY-MM-DD 或 YYYY/MM/DD
        date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', question)
        if date_match:
            clues.append({
                "clue_type": "date",
                "value": date_match.group(1),
                "reason": f"用户输入的日期「{date_match.group(1)}」应从日志或日期字段筛选",
            })
        return clues

    def _list_blueprints(self, dataset: SemanticDataset) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for bp in dataset.blueprints:
            if bp.status != "active":
                continue
            results.append(
                {
                    "blueprint_id": bp.id,
                    "name": bp.name,
                    "description": bp.description,
                    "when_to_use": bp.when_to_use,
                    "trigger_keywords": _json_list(bp.trigger_keywords),
                    "trigger_examples": _json_list(bp.trigger_examples),
                    "parameters": _json_list(bp.parameters),
                    "call_template": bp.call_template,
                    "output_schema": _json_list(bp.output_schema),
                }
            )
        return results

    def _list_metrics(self, dataset: SemanticDataset) -> list[dict[str, Any]]:
        return [
            {
                "metric_id": m.id,
                "name": m.name,
                "display_name": m.display_name,
                "expr": m.expr,
                "table_name": m.table_name,
                "time_field": m.time_field,
                "granularity": m.granularity,
                "description": m.description,
            }
            for m in dataset.metrics
        ]

    def _list_dimensions(self, dataset: SemanticDataset) -> list[dict[str, Any]]:
        return [
            {
                "dimension_id": d.id,
                "name": d.name,
                "display_name": d.display_name,
                "column_name": d.column_name,
                "table_name": d.table_name,
                "join_to": d.join_to,
                "join_key": d.join_key,
            }
            for d in dataset.dimensions
        ]

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

    def _context_state_patch(self, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
        """把 L2 schema 切片转换成 ProgressiveContextState 可直接合并的安全 ref 集合。"""

        field_refs: list[str] = []
        for entity in entities:
            asset_ref = str(entity["asset_ref"])
            for field in entity.get("fields") or []:
                field_name = field.get("name")
                if field_name:
                    field_refs.append(f"{asset_ref}.{field_name}")
        return {
            "asset_refs": [str(entity["asset_ref"]) for entity in entities],
            "relationship_refs": [
                str(relationship["relationship_ref"])
                for relationship in relationships
                if relationship.get("relationship_ref")
            ],
            "field_refs": field_refs,
        }

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
