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

import logging
import re
from typing import Any

import sqlglot
from sqlalchemy.orm import Session
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

from app.domains.bi.worker.contracts import (
    DatasetCapabilityContext,
    QueryAssetContext,
    SchemaSliceContext,
    ValueProfileContext,
)
from app.core.models.dataset import SemanticDataset, SourceColumn, SourceTable


logger = logging.getLogger(__name__)


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


def _focus_field_names(focus: dict[str, Any] | None) -> set[str]:
    """提取 L2 focus 中显式点名的字段名，兼容调试期多种入参 key。"""

    if not isinstance(focus, dict):
        return set()
    names: set[str] = set()
    for key in ("fields", "missing_fields", "target_fields"):
        raw_items = focus.get(key)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            text = str(item or "").strip()
            if not text:
                continue
            # 支持 "table.column" / "schema.table.column"；L2 精确通道只按列名匹配。
            names.add(text.split(".")[-1].lower())
    return names


def _safe_parse_sql(sql: str) -> exp.Expression | None:
    """依次尝试 mysql/sqlite/postgres 方言解析，全部失败返回 None。"""

    for dialect in ("mysql", "sqlite", "postgres"):
        try:
            parsed = sqlglot.parse_one(sql, read=dialect)
            # parse_one 声明返回 exp.Expr（Expression 的父类），
            # 这里仅接受 Expression 子类，其他情况一律 skip。
            if isinstance(parsed, exp.Expression):
                return parsed
        # sqlglot 内部可能抛出 ParseError/SqlglotError；此处兜底其他异常，
        # 保证 blueprint 解析失败不阻塞主链路。
        except (ParseError, SqlglotError, Exception):  # noqa: BLE001
            continue
    return None


def _extract_joins_from_ast(
    parsed: exp.Expression,
    dataset: SemanticDataset,
    blueprint: Any,
) -> list[dict[str, Any]]:
    """从 AST 提取 INNER/LEFT JOIN 的等值 join 键，返回 relationship dict 列表。"""

    # dataset 中已选物理表：建 table_name(lower) -> (schema_name, table_name) 映射，
    # 用于把 blueprint SQL 里的表名反查到 dataset 侧的规范物理表。
    schema_by_name: dict[str, tuple[str, str]] = {}
    for link in dataset.selected_tables or []:
        st = getattr(link, "source_table", None)
        if st is not None and st.status != "deleted":
            schema_by_name[st.table_name.lower()] = (st.schema_name, st.table_name)

    # alias -> 物理 (schema, table)：FROM 主表 + 所有 JOIN 右表都会被 find_all 遍历到。
    alias_map: dict[str, tuple[str, str]] = {}
    for tbl in parsed.find_all(exp.Table):
        tbl_name = tbl.name or ""
        alias = tbl.alias_or_name  # 无 alias 时回退到表名
        physical = schema_by_name.get(tbl_name.lower())
        if physical and alias:
            alias_map[alias] = physical

    results: list[dict[str, Any]] = []
    for join_node in parsed.find_all(exp.Join):
        # sqlglot 的 join 类型分布在 side/kind 两个字段：
        # - side: LEFT/RIGHT/FULL
        # - kind: INNER/CROSS
        kind = (join_node.args.get("kind") or "").upper()
        side = (join_node.args.get("side") or "").upper()
        if side == "LEFT":
            join_type = "left"
        elif side in ("RIGHT", "FULL"):
            # RIGHT/FULL 不在契约范围内，跳过
            continue
        elif kind == "INNER" or (not side and not kind):
            join_type = "inner"
        elif kind == "CROSS":
            # CROSS JOIN 没有等值条件，直接跳过
            continue
        else:
            # 其他非常规写法保守回退为 inner
            join_type = "inner"

        on_expr = join_node.args.get("on")
        if on_expr is None:
            continue

        # 收集 ON 中的等值条件，暂存两侧 alias 便于后续规范化。
        raw_keys: list[dict[str, str]] = []
        for eq in on_expr.find_all(exp.EQ):
            left_col = eq.this if isinstance(eq.this, exp.Column) else None
            right_col = eq.expression if isinstance(eq.expression, exp.Column) else None
            if left_col is None or right_col is None:
                continue
            left_alias = (left_col.table or "").strip()
            right_alias = (right_col.table or "").strip()
            left_field = (left_col.name or "").strip()
            right_field = (right_col.name or "").strip()
            if not (left_alias and right_alias and left_field and right_field):
                continue
            raw_keys.append(
                {
                    "_left_alias": left_alias,
                    "_right_alias": right_alias,
                    "left_field": left_field,
                    "right_field": right_field,
                }
            )

        if not raw_keys:
            continue

        # 右表：join_node.this 一定是 exp.Table
        right_tbl_node = join_node.this if isinstance(join_node.this, exp.Table) else None
        if right_tbl_node is None:
            continue
        right_alias = right_tbl_node.alias_or_name
        right_physical = alias_map.get(right_alias)
        if right_physical is None:
            continue

        # 左表从首个 join_key 的另一侧 alias 推断
        first_key = raw_keys[0]
        # 若首个 key 里 right_alias 恰好在两侧之一，另一侧就是左 alias
        if first_key["_right_alias"] == right_alias:
            first_left_alias = first_key["_left_alias"]
        elif first_key["_left_alias"] == right_alias:
            first_left_alias = first_key["_right_alias"]
        else:
            continue
        left_physical = alias_map.get(first_left_alias)
        if left_physical is None:
            continue

        # 规范化每条 key，允许 SQL 里 ON a.x=b.y 与 b.y=a.x 两种顺序
        filtered_keys: list[dict[str, str]] = []
        for k in raw_keys:
            kla = k["_left_alias"]
            kra = k["_right_alias"]
            if kla == first_left_alias and kra == right_alias:
                filtered_keys.append(
                    {"left_field": k["left_field"], "right_field": k["right_field"]}
                )
            elif kla == right_alias and kra == first_left_alias:
                filtered_keys.append(
                    {"left_field": k["right_field"], "right_field": k["left_field"]}
                )
        if not filtered_keys:
            continue

        left_schema, left_table = left_physical
        right_schema, right_table = right_physical
        left_ref = f"table:{left_schema}.{left_table}"
        right_ref = f"table:{right_schema}.{right_table}"
        results.append(
            {
                "relationship_ref": (f"blueprint_join:{blueprint.id}:{left_ref}->{right_ref}"),
                "left_asset_ref": left_ref,
                "right_asset_ref": right_ref,
                "relationship_type": "blueprint_join",
                "join_keys": filtered_keys,
                "join_type": join_type,
                "source_blueprint_id": blueprint.id,
                "description": f"来自蓝图「{blueprint.name}」的真实关联条件。",
            }
        )
    return results


def _parse_blueprint_joins(dataset: SemanticDataset) -> list[dict[str, Any]]:
    """从 dataset 的所有 active 蓝图 call_template 解析真实 join 关系。

    - 只处理简单单层 SELECT + INNER/LEFT JOIN；
    - 只识别 ON 表达式里的 exp.EQ 等值条件；
    - 任何异常/边界情况都 skip 单条 join，不阻塞主链路。
    """

    results: list[dict[str, Any]] = []
    for bp in dataset.blueprints or []:
        if bp.status != "active":
            continue
        sql = (bp.call_template or bp.raw_sql or "").strip()
        if not sql:
            continue
        parsed = _safe_parse_sql(sql)
        if parsed is None:
            continue
        try:
            joins = _extract_joins_from_ast(parsed, dataset, bp)
        except Exception:  # noqa: BLE001
            # 解析异常降级到 debug 日志，绝不影响 L2 主链
            logger.debug("解析蓝图 %s join 失败", bp.id, exc_info=True)
            continue
        results.extend(joins)
    return results


class BIWorkerContextProvider:
    """基于 Datalogue 元数据提供 BI Worker 查询上下文。"""

    def __init__(self, db: Session):
        self._db = db

    def describe_dataset_capability(
        self, dataset_id: int, question: str
    ) -> DatasetCapabilityContext:
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
        question: str | None = None,
        focus: dict[str, Any] | None = None,
    ) -> SchemaSliceContext:
        """L2 表清单通道：只返回 dataset 内全部表 + 关系，不再返回 fields。

        本轮把 L2 拆成两个正交工具：
        - request_schema_slice：给 LLM 一个稳定的“表目录”视图，避免后端猜表；
        - describe_tables：由 LLM 点名后按需拉取字段详情/样例值。

        为保证外部签名兼容，仍接受 question/focus，但内部一律忽略。
        """

        # question/focus 已废弃，显式丢弃以让静态检查/调试期一眼看出不再使用。
        del question, focus

        dataset = self._get_dataset(dataset_id)
        # 直接列全量物理表，不做模糊过滤：让 LLM 自己按点名走 describe_tables。
        tables = self._source_tables(dataset)
        entities: list[dict[str, Any]] = []
        for table in tables:
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
                    # 让 LLM 在无字段视图下也能粗略评估表规模，用于决定是否 describe。
                    "row_count_approx": table.row_count_approx,
                    "column_count": len(table.columns),
                }
            )

        relationships = self._relationships(entities, dataset)
        return SchemaSliceContext(
            dataset_id=dataset.id,
            entities=entities,
            relationships=relationships,
            # entities 里没有 fields，_context_state_patch 会派生出空 field_refs，
            # 待 describe_tables 阶段再补齐真实的 field_refs。
            context_state_patch=self._context_state_patch(entities, relationships),
            context_state_usage=(
                "将 context_state_patch 合并进后续 L4/L5 的 context_state；"
                "需要字段详情/样例值时，调用 datalogue_describe_tables 按表名点选。"
            ),
            summary=f"数据集内共 {len(entities)} 张表，已列出全部表和关系。",
        )

    def describe_tables(self, dataset_id: int, table_names: list[str]) -> dict[str, Any]:
        """按点名返回 dataset 内多张表的字段详情/注释/样例值。

        - table_names 中不存在的表返回 status="not_found" 占位，不影响其他表；
        - 每张表所有列全部返回，不截断；样例值仅取前 3 条。
        """

        dataset = self._get_dataset(dataset_id)
        # dataset 内表名（小写）→ SourceTable 映射，保证按名查找 O(1)。
        all_tables = {table.table_name.lower(): table for table in self._source_tables(dataset)}
        entities: list[dict[str, Any]] = []
        for raw_name in table_names or []:
            name = str(raw_name).strip()
            if not name:
                # 跳过空字符串输入，不算错误。
                continue
            table = all_tables.get(name.lower())
            if table is None:
                # 表不存在：返回 not_found 占位，让 LLM 感知未命中，其他表照常返回。
                entities.append(
                    {
                        "asset_ref": f"table:unknown.{name}",
                        "table": name,
                        "status": "not_found",
                        "reason": "table not in dataset",
                    }
                )
                continue
            entities.append(self._describe_table(table))
        relationships = self._relationships(entities, dataset)
        return {
            "datalogue_event_type": "bi_worker_l2_table_detail",
            "dataset_id": dataset.id,
            "entities": entities,
            # describe_tables 是字段详情来源，必须同步给 Worker 可直接合并的 field_refs，
            # 避免模型从自然语言字段列表手写 context_state 后触发 L4 FIELD_NOT_FOUND。
            "context_state_patch": self._context_state_patch(entities, relationships),
            "context_state_usage": (
                "将 context_state_patch 合并进后续 L4/L5 的 context_state；"
                "字段 ref 以 table:schema.table.field 形式进入 field_refs。"
            ),
            "summary": f"已返回 {len(entities)} 张表的字段详情。",
        }

    def _describe_table(self, table: SourceTable) -> dict[str, Any]:
        """把单张 SourceTable 转换为 describe_tables 的字段详情结构。"""

        fields: list[dict[str, Any]] = []
        for column in table.columns:
            # 元数据同步阶段已把样例值写入 SourceColumn.sample_values（JSON list），
            # 这里只做类型收敛并截取前 3 条，避免把大 list 灌进 LLM 上下文。
            raw_samples = _json_list(column.sample_values)
            sample_values = [str(value) for value in raw_samples[:3]]
            fields.append(
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
                    "semantic_role": (
                        column.user_semantic_role or column.ai_semantic_role or column.semantic_role
                    ),
                    "sample_values": sample_values,
                    # metadata=元数据已采集；unavailable=元数据侧无样例可用，
                    # 让 LLM 知道“空样例”是数据缺失而不是被人为截断。
                    "sample_source": "metadata" if raw_samples else "unavailable",
                }
            )
        return {
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
            "row_count_approx": table.row_count_approx,
            "column_count": len(table.columns),
            "fields": fields,
            "status": "ok",
        }

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

        蓝图命中时只作为 QueryPlan 生成参考，不要求 worker 直接生成或执行 SQL。
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
                "先提取 parameters，再调用 datalogue_prepare_query_context、datalogue_request_schema_slice 获取表/关系，"
                "再用 datalogue_describe_tables 获取蓝图涉及表的字段与 field_refs；"
                "将蓝图的输出字段、筛选条件和排序语义转换为 BIWorkerQueryPlan 后交给 datalogue_execute_query_plan_bundle。"
                "禁止把 call_template 当作可直接传入工具的 SQL。"
                if blueprints
                else "无可用蓝图，请走 datalogue_prepare_query_context → datalogue_request_schema_slice → datalogue_describe_tables → datalogue_execute_query_plan_bundle。"
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
            missing_conditions.append(
                {
                    "type": "missing_dimension",
                    "detail": "未发现业务维度信息，可能影响维度筛选。",
                }
            )
        if not capability.key_metrics:
            missing_conditions.append(
                {
                    "type": "missing_metric",
                    "detail": "未发现业务指标信息，可能影响指标查询。",
                }
            )
        if not matched_assets:
            missing_conditions.append(
                {
                    "type": "no_assets_recalled",
                    "detail": "未召回相关数据资产，建议调整问题描述。",
                }
            )
        if suggested_filters:
            missing_conditions.append(
                {
                    "type": "filter_hint_unresolved",
                    "detail": "问题中包含筛选条件，需要在 QueryPlan filters 中完整表达。",
                    "clues": suggested_filters,
                }
            )
        asset_coverage = "insufficient" if missing_conditions else "sufficient"
        next_step = (
            "request_more_schema" if asset_coverage == "insufficient" else "generate_query_plan"
        )
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
                "asset_refs": [self._asset_ref_from_matched_asset(item) for item in matched_assets],
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
    def _asset_ref_from_matched_asset(item: dict[str, Any]) -> str:
        """把 prepare 阶段资产摘要转换为后续 QueryPlan 可复用的安全 asset_ref。"""

        asset_type = str(item.get("asset_type") or "").strip()
        schema = str(item.get("schema") or "").strip()
        name = str(item.get("name") or "").strip()
        qualified_name = f"{schema}.{name}" if schema and name else name
        return f"{asset_type}:{qualified_name}" if asset_type else qualified_name

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
            r"查询\s*([一-龥]{2,4})\s*的",
            r"按\s*([一-龥]{2,4})\s*(?:查询|筛选|过滤)",
            r"([一-龥]{2,4})\s*(?:的日志|的记录|的订单|的数据)",
        ]:
            match = re.search(pattern, question)
            if match:
                name = match.group(1)
                clues.append(
                    {
                        "clue_type": "person_name",
                        "value": name,
                        "reason": f"用户输入的人名「{name}」应从员工姓名或相关人员字段筛选",
                    }
                )
                break
        # 年份：YYYY年 或 YYYY
        year_match = re.search(r"(\d{4})\s*年", question)
        if year_match:
            clues.append(
                {
                    "clue_type": "year",
                    "value": year_match.group(1),
                    "reason": f"用户输入的年份「{year_match.group(1)}」应从日期字段筛选",
                }
            )
        # 日期范围：YYYY-MM-DD 或 YYYY/MM/DD
        date_match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", question)
        if date_match:
            clues.append(
                {
                    "clue_type": "date",
                    "value": date_match.group(1),
                    "reason": f"用户输入的日期「{date_match.group(1)}」应从日志或日期字段筛选",
                }
            )
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
            column_text = " ".join(text for text in column_texts if text)
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
        # 精确通道：兼容 fields/missing_fields/target_fields。字段可写成 "table.column"，
        # 匹配时只取最后一段列名，保证蓝图输出字段补切片稳定命中。
        wanted = _focus_field_names(focus)
        if wanted:
            exact = [
                column
                for column in table.columns
                if column.column_name and column.column_name.lower() in wanted
            ]
            if exact:
                return exact
        # 兜底：保留原模糊匹配，让不显式点名字段的 focus（tables/relationships/reason）依然能命中。
        focus_text = " ".join(
            str(value)
            for key, value in focus.items()
            if key not in {"fields", "missing_fields", "target_fields"}
        )
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
            role = (
                column.user_semantic_role or column.ai_semantic_role or column.semantic_role or ""
            ).lower()
            if roles and role and role not in roles:
                continue
            label = _first_text(
                column.column_comment, column.effective_desc, column.user_description
            )
            if label and label not in labels:
                labels.append(label)
        if labels:
            return labels
        for column in columns:
            label = _first_text(
                column.column_comment, column.effective_desc, column.user_description
            )
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

    def _relationships(
        self,
        entities: list[dict[str, Any]],
        dataset: SemanticDataset,
    ) -> list[dict[str, Any]]:
        # 软关系：同一数据集内被同时选中的表之间的候选关联提示。
        soft: list[dict[str, Any]] = []
        if len(entities) >= 2:
            primary = entities[0]["asset_ref"]
            soft = [
                {
                    "relationship_ref": f"dataset_selected:{primary}->{entity['asset_ref']}",
                    "left_asset_ref": primary,
                    "right_asset_ref": entity["asset_ref"],
                    "relationship_type": "dataset_selected_together",
                    "description": "这些实体属于同一语义数据集，可作为后续规划的候选关联资产。",
                }
                for entity in entities[1:]
            ]
        # 硬关系：来自蓝图 SQL 的真实 FK/join，优先级高于软关系。
        hard = _parse_blueprint_joins(dataset)
        # 去重：同一对 (left_asset_ref, right_asset_ref) 若已存在真实 FK，则丢弃对应软关系。
        hard_pairs = {(r["left_asset_ref"], r["right_asset_ref"]) for r in hard}
        soft_filtered = [
            r for r in soft if (r["left_asset_ref"], r["right_asset_ref"]) not in hard_pairs
        ]
        return soft_filtered + hard

    def _context_state_patch(
        self, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """把 L2 schema 切片转换成 ProgressiveContextState 可直接合并的安全 ref 集合。

        - entities 来自 request_schema_slice 时 fields 缺席，field_refs 会为空；
        - describe_tables 侧的 entities 才会派生 field_refs。
        遍历 ``entity.get("fields") or []`` 已经天然 fail-safe，无需额外分支。
        """

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
            if (
                table.table_name.lower() == lowered
                or f"{table.schema_name}.{table.table_name}".lower() == lowered
            ):
                return table
        return None

    def _find_column(self, table: SourceTable, column_name: str) -> SourceColumn | None:
        lowered = column_name.lower()
        for column in table.columns:
            if column.column_name.lower() == lowered:
                return column
        return None
