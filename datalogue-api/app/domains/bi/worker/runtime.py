# ============================================================
# File Name   : bi_worker_runtime.py
# Description:
#   BI Worker Query Plan 的 L5 受控查询 Runtime。
#
# Responsibilities:
#   - 在执行前强制通过 L4 Query Support Validator，缺上下文时不触发查询。
#   - 复用 AgentScope Dataset bridge 和 BI atomic toolkit 执行受控查询。
#   - 把执行异常转换成安全 Repair Request，避免 SQL、raw rows 或数据库错误进入 Agent Team。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.domains.bi.agent.runtime_context import build_bi_runtime_context
from app.domains.bi.worker.contracts import (
    BIWorkerQueryPlan,
    BIWorkerQueryResult,
    FAILURE_DIAGNOSIS_MAP,
    FieldTarget,
    QueryFailureType,
    QueryEntity,
    RepairRequest,
)
from app.domains.bi.worker.validator import (
    BIWorkerQueryValidator,
    ProgressiveContextState,
)
from app.domains.bi.skill.runtime_bridge import AgentScopeDatasetRuntimeBridge
from app.domains.bi.toolkit import build_bi_atomic_toolkit
from app.core.models.dataset import SemanticDataset

logger = logging.getLogger(__name__)


class BIWorkerQueryRuntime:
    """BI Worker L5 Runtime：只执行已被 L4 渐进式上下文支持的查询计划。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.validator = BIWorkerQueryValidator()

    async def execute_query_plan(
        self,
        dataset_id: int,
        confirmed_question: str,
        query_plan: BIWorkerQueryPlan,
        context_state: ProgressiveContextState,
        trace_id: str | None = None,
    ) -> dict[str, Any]:

        # 进入点结构化摘要:一眼看清 dimension,便于按 dataset_id/trace_id 反查
        logger.info(
            "[bi_worker.execute_query_plan] START dataset_id=%s trace_id=%s intent=%s "
            "primary_asset=%s supporting=%d filters=%d selects=%d metrics=%d "
            "join_requirements=%d ctx_asset_refs=%d ctx_field_refs=%d "
            "ctx_relationship_refs=%d suggested_filters=%d",
            dataset_id,
            trace_id,
            query_plan.intent,
            query_plan.data_graph.primary_entity.asset_ref,
            len(query_plan.data_graph.supporting_entities),
            len(query_plan.filters),
            len(query_plan.selects),
            len(query_plan.metrics),
            len(query_plan.join_requirements),
            len(context_state.asset_refs),
            len(context_state.field_refs),
            len(context_state.relationship_refs),
            len(context_state.suggested_filters),
        )

        _normalize_context_state_refs(context_state)
        # 从 dataset 元数据主动补齐 field_refs/asset_refs,允许 LLM 不显式 merge context_state_patch。
        # 只补字段级和表级 ref,不动 relationship_refs(蓝图 SQL 硬关系 LLM 必须显式引用)。
        # 兜底本身只是"扩大合法引用范围"的可选增强:dataset 不可用时跳过,L4 仍然会用现有
        # context_state 兜底判定,不会因为 dataset 加载失败而阻断已经合法的查询。
        dataset = self._get_dataset(dataset_id)
        if dataset is not None:
            derived_refs = _derive_dataset_field_refs(dataset)
            before_field = len(context_state.field_refs)
            before_asset = len(context_state.asset_refs)
            context_state.field_refs = context_state.field_refs | derived_refs
            context_state.asset_refs = context_state.asset_refs | {
                r for r in derived_refs if r.count(".") == 1
            }
            logger.info(
                "[bi_worker.execute_query_plan] dataset ref 兜底 dataset_id=%s "
                "derived=%d field_refs=%d->%d asset_refs=%d->%d",
                dataset_id,
                len(derived_refs),
                before_field,
                len(context_state.field_refs),
                before_asset,
                len(context_state.asset_refs),
            )
        else:
            logger.warning(
                "[bi_worker.execute_query_plan] dataset 未找到,跳过 ref 兜底 dataset_id=%s",
                dataset_id,
            )

        # L4：内部校验 → 未通过时映射为失败类型
        validation = self.validator.validate(query_plan, context_state)
        if validation.support_status != "supported":
            missing = getattr(validation, "missing_context", None) or []
            # 逐条打印 missing 项 —— 这是 FIELD_NOT_FOUND 排查的核心信息
            for item in missing[:20]:
                logger.warning(
                    "[bi_worker.execute_query_plan] L4 missing_context dataset_id=%s "
                    "type=%s ref=%s recommended_next_tool=%s",
                    dataset_id,
                    item.get("type"),
                    item.get("ref"),
                    item.get("recommended_next_tool"),
                )
            failure = self._map_validation_to_failure(validation, query_plan)
            logger.warning(
                "[bi_worker.execute_query_plan] L4 FAILED dataset_id=%s trace_id=%s "
                "support_status=%s failure_type=%s missing_count=%d safe_reason=%s",
                dataset_id,
                trace_id,
                validation.support_status,
                failure.failure_type,
                len(missing),
                validation.safe_reason,
            )
            return failure.to_tool_payload()

        # 筛选完整性预检：问题中有筛选线索但 QueryPlan 未在 filters 中体现
        if not query_plan.filters and context_state.suggested_filters:
            missing_count = len(context_state.suggested_filters)
            diagnosis = FAILURE_DIAGNOSIS_MAP["FILTER_MISSING"]
            logger.warning(
                "[bi_worker.execute_query_plan] FILTER_MISSING dataset_id=%s trace_id=%s "
                "suggested_filter_count=%d types=%s",
                dataset_id,
                trace_id,
                missing_count,
                [str(item.get("clue_type") or "") for item in context_state.suggested_filters[:10]],
            )
            return BIWorkerQueryResult(
                answer_summary=f"查询计划缺少筛选条件：{missing_count} 个筛选线索未在 filters 中体现。",
                artifact_ref=None,
                checkpoint_ref=None,
                row_count=None,
                column_count=None,
                failure_type="FILTER_MISSING",
                safe_diagnosis=diagnosis["safe_diagnosis"],
                recommended_action=diagnosis["recommended_action"],
            ).to_tool_payload()

        try:
            result = await self._execute_supported_plan(
                dataset_id=dataset_id,
                confirmed_question=confirmed_question,
                query_plan=query_plan,
                trace_id=trace_id,
            )
        except Exception as exc:
            # 执行阶段异常:打完整堆栈便于定位真实数据库/编译错误。
            # 异常 message 可能含 SQL 片段,但 logger 只写文件日志、不进用户可见通道,允许打。
            logger.exception(
                "[bi_worker.execute_query_plan] EXECUTE EXCEPTION dataset_id=%s trace_id=%s "
                "exc_type=%s exc_msg=%s",
                dataset_id,
                trace_id,
                type(exc).__name__,
                str(exc),
            )
            failure = self._map_exception_to_failure(exc)
            logger.warning(
                "[bi_worker.execute_query_plan] 异常映射为 failure_type=%s",
                failure.failure_type,
            )
            return failure.to_tool_payload()

        # _execute_plan 已经把 bridge blocked 场景写成 failure_type，这里直接透传给 LLM。
        if result.failure_type is not None:
            logger.error("[failure_result]: %s", json.dumps(result.to_tool_payload()))
            logger.warning(
                "[bi_worker.execute_query_plan] BRIDGE FAILED dataset_id=%s trace_id=%s "
                "failure_type=%s safe_diagnosis=%s",
                dataset_id,
                trace_id,
                result.failure_type,
                result.safe_diagnosis,
            )
            return result.to_tool_payload()

        # 空结果映射：row_count=0 是明确空，row_count is None 且没有 artifact 也当作空结果，
        # 避免出现 status=completed 但 answer_summary="查询未完成" 的自相矛盾 payload。
        if result.row_count == 0 or (result.row_count is None and not result.artifact_ref):
            logger.warning(
                "[bi_worker.execute_query_plan] EMPTY_RESULT dataset_id=%s trace_id=%s "
                "row_count=%s artifact_ref=%s",
                dataset_id,
                trace_id,
                result.row_count,
                result.artifact_ref,
            )
            empty_result = BIWorkerQueryResult(
                answer_summary="查询执行成功但未返回数据。",
                artifact_ref=result.artifact_ref,
                checkpoint_ref=result.checkpoint_ref,
                row_count=result.row_count if result.row_count is not None else 0,
                column_count=result.column_count,
                failure_type="EMPTY_RESULT",
                safe_diagnosis=FAILURE_DIAGNOSIS_MAP["EMPTY_RESULT"]["safe_diagnosis"],
                recommended_action=FAILURE_DIAGNOSIS_MAP["EMPTY_RESULT"]["recommended_action"],
            )
            return empty_result.to_tool_payload()

        # 成功路径:记录关键指标,便于回归对比和 SLO 观测。
        logger.info(
            "[bi_worker.execute_query_plan] SUCCESS dataset_id=%s trace_id=%s "
            "row_count=%s column_count=%s artifact_ref=%s",
            dataset_id,
            trace_id,
            result.row_count,
            result.column_count,
            result.artifact_ref,
        )
        return result.to_tool_payload()

    def _map_validation_to_failure(
        self, validation, query_plan: BIWorkerQueryPlan
    ) -> BIWorkerQueryResult:
        missing_context = getattr(validation, "missing_context", None) or []
        missing_types = {item.get("type") for item in missing_context}
        if "missing_field" in missing_types and self._has_filter_refs(query_plan):
            failure_type: QueryFailureType = "FILTER_MISSING"
        elif "missing_field" in missing_types:
            failure_type = "FIELD_NOT_FOUND"
        elif "missing_relationship" in missing_types:
            failure_type = "FIELD_NOT_FOUND"
        else:
            failure_type = "FIELD_NOT_FOUND"
        diagnosis = FAILURE_DIAGNOSIS_MAP[failure_type]
        return BIWorkerQueryResult(
            answer_summary=f"查询计划缺少所需上下文：{validation.safe_reason}",
            artifact_ref=None,
            checkpoint_ref=None,
            row_count=None,
            column_count=None,
            failure_type=failure_type,
            safe_diagnosis=diagnosis["safe_diagnosis"],
            recommended_action=diagnosis["recommended_action"],
        )

    def _has_filter_refs(self, query_plan: BIWorkerQueryPlan) -> bool:
        if query_plan.filters:
            return True
        return any(join.required for join in query_plan.join_requirements)

    def _map_exception_to_failure(self, exc: Exception) -> BIWorkerQueryResult:
        _ = type(exc).__name__
        exc_msg = str(exc).lower()
        if "sql_guard" in exc_msg or "guard" in exc_msg or "not authorized" in exc_msg:
            failure_type: QueryFailureType = "SQL_GUARD_BLOCKED"
        elif "binding" in exc_msg or "bind" in exc_msg or "parameter" in exc_msg:
            failure_type = "VALUE_BINDING_FAILED"
        elif "aggregation" in exc_msg or "aggregate" in exc_msg:
            failure_type = "AGGREGATION_WRONG"
        else:
            failure_type = "EXECUTE_FAILED"
        diagnosis = FAILURE_DIAGNOSIS_MAP[failure_type]
        return BIWorkerQueryResult(
            answer_summary=f"查询执行失败（{failure_type}）。",
            artifact_ref=None,
            checkpoint_ref=None,
            row_count=None,
            column_count=None,
            failure_type=failure_type,
            safe_diagnosis=diagnosis["safe_diagnosis"],
            recommended_action=diagnosis["recommended_action"],
        )

    async def execute_fallback(
        self,
        *,
        dataset_id: int,
        confirmed_question: str,
        trace_id: str | None = None,
    ) -> BIWorkerQueryResult:
        """无 LLM 生成 QueryPlan 时的代码级兜底：基于表 schema 构造最小查询计划并执行。"""
        toolkit = build_bi_atomic_toolkit(self.db)
        bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
        runtime_context = build_bi_runtime_context(
            self.db,
            dataset_id=dataset_id,
            question=confirmed_question,
            bridge=bridge,
        )
        session_kwargs = (
            runtime_context.get("session_kwargs") if isinstance(runtime_context, dict) else {}
        )
        dsl = _build_fallback_dsl(session_kwargs)
        return await self._execute_plan(
            bridge=bridge,
            dataset_id=dataset_id,
            question=confirmed_question,
            session_kwargs=session_kwargs,
            dsl=dsl,
            trace_id=trace_id,
        )

    async def _execute_supported_plan(
        self,
        *,
        dataset_id: int,
        confirmed_question: str,
        query_plan: BIWorkerQueryPlan,
        trace_id: str | None,
    ) -> BIWorkerQueryResult:
        toolkit = build_bi_atomic_toolkit(self.db)
        bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
        runtime_context = build_bi_runtime_context(
            self.db,
            dataset_id=dataset_id,
            question=confirmed_question,
            bridge=bridge,
        )
        session_kwargs = (
            runtime_context.get("session_kwargs") if isinstance(runtime_context, dict) else {}
        )
        dsl = self._query_plan_to_legacy_query_plan(query_plan)
        return await self._execute_plan(
            bridge=bridge,
            dataset_id=dataset_id,
            question=confirmed_question,
            session_kwargs=session_kwargs,
            dsl=dsl,
            trace_id=trace_id,
        )

    async def _execute_plan(
        self,
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        dataset_id: int,
        question: str,
        session_kwargs: dict[str, Any],
        dsl: dict[str, Any],
        trace_id: str | None,
    ) -> BIWorkerQueryResult:
        session = bridge.start_session(
            dataset_id=dataset_id,
            question=question,
            agent_name="bi_worker",
            trace_id=trace_id,
            **session_kwargs,
        )
        result = await bridge.run_direct_query(session=session, dsl=dsl)
        artifact_ref = _optional_str(result.get("artifact_ref"))
        checkpoint_ref = _optional_str(result.get("checkpoint_ref"))
        row_count = _optional_int(result.get("row_count"))
        column_count = _optional_int(result.get("column_count"))
        bridge_status = _optional_str(result.get("status"))
        # bridge 明确 blocked / 缺 artifact 时，把 code 映射为 failure_type，避免上层
        # 误判为 completed；如果只是空结果由 execute_query_plan 主链再兜底为 EMPTY_RESULT。
        if bridge_status == "blocked" or (bridge_status != "completed" and not artifact_ref):
            failure_type = _map_bridge_code_to_failure(
                code=str(result.get("code") or "RUNTIME_BLOCKED"),
                error_summary=str(result.get("error_summary") or ""),
            )
            # 打印 bridge 原始失败信息：code、error_summary、tool_results 中的错误摘要
            _log_tool_result_errors(result, dataset_id, trace_id)
            logger.warning(
                "[bi_worker._execute_plan] BRIDGE BLOCKED dataset_id=%s trace_id=%s "
                "code=%s error_summary=%s failure_type=%s",
                dataset_id,
                trace_id,
                result.get("code"),
                result.get("error_summary"),
                failure_type,
            )
            diagnosis = FAILURE_DIAGNOSIS_MAP[failure_type]
            return BIWorkerQueryResult(
                answer_summary=f"查询执行未完成（{failure_type}）。",
                artifact_ref=None,
                checkpoint_ref=None,
                row_count=None,
                column_count=None,
                failure_type=failure_type,
                safe_diagnosis=diagnosis["safe_diagnosis"],
                recommended_action=diagnosis["recommended_action"],
            )
        return BIWorkerQueryResult(
            answer_summary=_answer_summary(
                status=bridge_status,
                artifact_ref=artifact_ref,
                row_count=row_count,
                column_count=column_count,
            ),
            artifact_ref=artifact_ref,
            checkpoint_ref=checkpoint_ref,
            row_count=row_count,
            column_count=column_count,
        )

    def _query_plan_to_legacy_query_plan(self, query_plan: BIWorkerQueryPlan) -> dict[str, Any]:
        alias_tables = _alias_table_names(query_plan)
        selected_assets = [
            {
                "asset_type": "field",
                "asset_id": item.target.asset_ref,
                "name": item.target.field,
                "display_name": item.display_name,
                "source": "bi_worker_query_plan",
                "confidence": 0.9,
                "usage": "selected",
                # 编译器依赖 metadata 区分表名和字段名，避免把 field name 误当 FROM 表。
                "metadata": _target_metadata(item.target, alias_tables=alias_tables),
            }
            for item in query_plan.selects
        ]
        # 将 filter 条件透传到编译器层，避免过滤条件在转换时丢失。
        compiled_filters = [
            {
                "field": item.target.field,
                "alias": item.target.alias,
                "asset_ref": item.target.asset_ref,
                "operator": item.operator,
                "value": item.value,
                "reason": item.reason,
                "metadata": _target_metadata(item.target, alias_tables=alias_tables),
            }
            for item in query_plan.filters
        ]
        compiled_metrics = [
            {
                "field": item.target.field,
                "alias": item.target.alias,
                "asset_ref": item.target.asset_ref,
                "aggregation": item.aggregation,
                "display_name": item.display_name,
                "metadata": _target_metadata(item.target, alias_tables=alias_tables),
            }
            for item in query_plan.metrics
        ]
        compiled_group_by = [
            {
                "field": item.field,
                "alias": item.alias,
                "asset_ref": item.asset_ref,
                "metadata": _target_metadata(item, alias_tables=alias_tables),
            }
            for item in query_plan.group_by
        ]
        result: dict[str, Any] = {
            "query_type": query_plan.intent,
            "execution_strategy": "query_graph",
            "confidence": 0.9,
            "selected_assets": selected_assets,
            "reference_assets": [],
            "rejected_assets": [],
            "required_inputs": [],
            "planner_source": "bi_worker_query_plan",
            "execution_source": "bi_worker_query_runtime",
            "explanation": {
                "summary": "BI Worker 已基于渐进式上下文生成受控查询计划。",
                "assumptions": list(query_plan.assumptions),
            },
            "debug": {
                "selected_main_table": _entity_table_name(query_plan.data_graph.primary_entity),
            },
        }
        if compiled_filters:
            result["filters"] = compiled_filters
        if compiled_metrics:
            result["metrics"] = compiled_metrics
        if compiled_group_by:
            result["group_by"] = compiled_group_by
        # 透传 join_requirements 里的显式 join_keys；旧编译器目前不消费，仅保留
        # 结构化通道供后续升级消费（避免 LLM 再次把 SQL 片段塞回非法字段）。
        compiled_joins = [
            {
                "left_alias": join.left_alias,
                "right_alias": join.right_alias,
                # 通过 alias 反查真实表名；找不到映射时返回空串（fail-closed 由下游编译器判断）。
                "left_table": alias_tables.get(join.left_alias, ""),
                "right_table": alias_tables.get(join.right_alias, ""),
                "relationship_ref": join.relationship_ref,
                "join_type": join.join_type,
                "required": join.required,
                "reason": join.reason,
                "join_keys": [
                    {"left_field": key.left_field, "right_field": key.right_field}
                    for key in join.join_keys
                ],
            }
            for join in query_plan.join_requirements
        ]
        if compiled_joins:
            result["join_requirements"] = compiled_joins
        if query_plan.ordering:
            result["ordering"] = [
                {
                    "field": item.target.field,
                    "alias": item.target.alias,
                    "asset_ref": item.target.asset_ref,
                    "direction": item.direction,
                    "metadata": _target_metadata(item.target, alias_tables=alias_tables),
                }
                for item in query_plan.ordering
            ]
        if query_plan.result_shape:
            result["limit"] = query_plan.result_shape.limit
        return result

    def _safe_repair_request(
        self,
        exc: Exception,
        *,
        failure_stage: str,
    ) -> RepairRequest:
        del exc
        return RepairRequest(
            repair_status="needs_plan_revision",
            failure_stage=failure_stage,
            failure_class="controlled_query_runtime_error",
            safe_reason="受控查询执行失败，需要调整查询计划或补充上下文后重试。",
            recommended_action="重新生成查询计划，并仅使用已确认的资产、字段和关系引用。",
            missing_context=[],
        )

    def _get_dataset(self, dataset_id: int) -> SemanticDataset | None:
        """加载 dataset 元数据;db 未注入或找不到时返回 None,由调用侧决定降级策略。

        当前 execute_query_plan 只把 dataset 用作 field_refs 兜底,dataset 缺失时应
        跳过兜底、继续走 L4 现有 context_state 判定,而不是让整条查询 fail-closed。
        """

        if self.db is None:
            return None
        return self.db.get(SemanticDataset, dataset_id)


def _derive_dataset_field_refs(dataset: SemanticDataset) -> set[str]:
    """从 dataset 元数据推导全部字段级 ref,作为 L4 校验兜底 field_refs。

    后端天然拥有 dataset schema,允许 LLM 忘 merge context_state_patch 时
    L4 依然能精确命中。安全边界不变:字段属于 dataset,查询不会越权。
    """

    refs: set[str] = set()
    for link in getattr(dataset, "selected_tables", None) or []:
        table = getattr(link, "source_table", None)
        if table is None:
            continue
        if getattr(table, "status", None) == "deleted":
            continue
        schema_name = getattr(table, "schema_name", None)
        table_name = getattr(table, "table_name", None)
        if not schema_name or not table_name:
            continue
        prefix = "table:" + schema_name + "." + table_name
        refs.add(prefix)  # 表级 ref 也补,供 asset_refs 匹配路径使用
        for column in getattr(table, "columns", None) or []:
            column_name = getattr(column, "column_name", None)
            if not column_name:
                continue
            refs.add(prefix + "." + column_name)
    return refs


def _normalize_context_state_refs(context_state: ProgressiveContextState) -> None:
    """工具 JSON 入参会把 ref 集合反序列化为 list,进入集合运算前统一收敛类型。"""

    context_state.asset_refs = set(context_state.asset_refs or [])
    context_state.relationship_refs = set(context_state.relationship_refs or [])
    context_state.field_refs = set(context_state.field_refs or [])


def _answer_summary(
    *,
    status: str | None,
    artifact_ref: str | None,
    row_count: int | None,
    column_count: int | None,
) -> str:
    if status != "completed" or not artifact_ref:
        return "查询未完成，未生成可展示结果。"
    return f"查询已完成，结果已生成 artifact_ref={artifact_ref}，共 {row_count or 0} 行、{column_count or 0} 列。"


def _log_tool_result_errors(
    result: dict[str, Any],
    dataset_id: int,
    trace_id: str | None = None,
) -> None:
    """打印 bridge blocked 返回的 tool_results 中的实际错误信息，便于排查具体的字段名。"""
    tool_results = result.get("tool_results") or []
    for i, tr in enumerate(tool_results):
        if not isinstance(tr, dict):
            continue
        output = tr.get("output")
        if output is not None:
            # output 可能是 list[TextBlock] 或原始字符串
            texts = []
            if isinstance(output, list):
                for block in output:
                    text = getattr(block, "text", None) or (block if isinstance(block, str) else None)
                    if text:
                        texts.append(str(text))
            elif isinstance(output, str):
                texts.append(output)
            for text in texts:
                try:
                    parsed = json.loads(text)
                except (TypeError, json.JSONDecodeError):
                    parsed = None
                if isinstance(parsed, dict):
                    code_val = parsed.get("code") or parsed.get("status", "")
                    error_val = parsed.get("error_summary", "") or parsed.get("error", "") or parsed.get("message", "")
                    logger.warning(
                        "[bi_worker._execute_plan] tool_result[%d] dataset_id=%s trace_id=%s "
                        "code=%s error_summary=%s",
                        i, dataset_id, trace_id, code_val, error_val,
                    )
                else:
                    logger.warning(
                        "[bi_worker._execute_plan] tool_result[%d] dataset_id=%s trace_id=%s raw=%s",
                        i, dataset_id, trace_id, text[:500],
                    )
        elif tr.get("code"):
            # 无 output 的扁平 tool_result（如权限拒绝等），直接从 dict 字段取
            logger.warning(
                "[bi_worker._execute_plan] tool_result[%d] dataset_id=%s trace_id=%s "
                "tool=%s code=%s status=%s",
                i, dataset_id, trace_id,
                tr.get("name", "?"),
                tr.get("code"),
                tr.get("status"),
            )


def _map_bridge_code_to_failure(*, code: str, error_summary: str) -> QueryFailureType:
    """把 bridge.run_direct_query 返回的 blocked code 映射为 QueryFailureType。

    使用 code + 可选 error_summary 关键字组合判断；与 _map_exception_to_failure 对齐，
    确保 EXECUTE_BLOCKED/COMPILE_BLOCKED 等场景也能触发 LLM 侧 repair 链路 B。
    """

    signal = f"{code} {error_summary}".lower()
    if "sql_guard" in signal or "guard" in signal or "not_authorized" in signal:
        return "SQL_GUARD_BLOCKED"
    if "bind" in signal or "parameter" in signal or "value_binding" in signal:
        return "VALUE_BINDING_FAILED"
    if "aggregation" in signal or "aggregate" in signal:
        return "AGGREGATION_WRONG"
    return "EXECUTE_FAILED"


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _asset_ref_value(asset_ref: str | None) -> str:
    """去掉 asset_ref 的类型前缀，保留真实表/字段路径。"""

    text = str(asset_ref or "").strip()
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text


def _table_from_field_ref(asset_ref: str | None, field_name: str | None) -> str | None:
    """从 field/table ref 中提取表名，支持 schema.table 与 schema.table.column 形态。"""

    original_ref = str(asset_ref or "").strip()
    raw = _asset_ref_value(asset_ref)
    field = str(field_name or "").strip()
    if field and raw.endswith(f".{field}"):
        table_name = raw[: -(len(field) + 1)].strip(".")
        return table_name or None
    if original_ref.startswith("table:"):
        # L2 schema 切片返回的表级 ref 是 table:schema.table；即使包含点号也代表物理表，
        # 不能按旧逻辑当成无法解析，否则 join alias 无法反查 left/right_table。
        return raw or None
    if raw and "." not in raw:
        return raw
    return None


def _entity_table_name(entity: QueryEntity) -> str | None:
    return _table_from_field_ref(entity.asset_ref, None)


def _alias_table_names(query_plan: BIWorkerQueryPlan) -> dict[str, str]:
    """建立 QueryPlan entity alias 到物理表名的映射，供字段 ref 缺表名时兜底。"""

    entities = [query_plan.data_graph.primary_entity, *query_plan.data_graph.supporting_entities]
    aliases: dict[str, str] = {}
    for entity in entities:
        table_name = _entity_table_name(entity)
        if table_name:
            aliases[entity.alias] = table_name
    return aliases


def _target_metadata(target: FieldTarget, *, alias_tables: dict[str, str]) -> dict[str, str]:
    """把 BIWorker FieldTarget 转成编译器可直接消费的表/列 metadata。"""

    table_name = _table_from_field_ref(target.asset_ref, target.field) or alias_tables.get(
        target.alias
    )
    metadata = {"column_name": target.field}
    if table_name:
        metadata["table_name"] = table_name
    return metadata


def _build_fallback_dsl(session_kwargs: dict[str, Any] | None) -> dict[str, Any]:
    """从 Runtime 会话上下文中构造最小 query_graph DSL，让直接 fallback 可安全执行。"""

    kwargs = session_kwargs if isinstance(session_kwargs, dict) else {}
    sql_generation_context = (
        kwargs.get("sql_generation_context")
        if isinstance(kwargs.get("sql_generation_context"), dict)
        else {}
    )
    table_schemas = sql_generation_context.get("table_schemas")
    if not isinstance(table_schemas, list) or not table_schemas:
        return {
            "execution_strategy": "query_graph",
            "query_type": "detail_query",
            "selected_assets": [],
        }

    primary = table_schemas[0]
    main_table = str(primary.get("table_name") or primary.get("name") or "").strip()
    if not main_table:
        return {
            "execution_strategy": "query_graph",
            "query_type": "detail_query",
            "selected_assets": [],
        }

    fields = primary.get("fields") if isinstance(primary.get("fields"), list) else []
    selected_assets = []
    for field_info in fields[:8]:
        if not isinstance(field_info, dict):
            continue
        column_name = str(field_info.get("column_name") or field_info.get("name") or "").strip()
        if not column_name:
            continue
        display_name = str(
            field_info.get("display_name") or field_info.get("comment") or column_name
        )
        selected_assets.append(
            {
                "asset_type": "field",
                "asset_id": f"{main_table}.{column_name}",
                "name": column_name,
                "display_name": display_name,
                "source": "direct_fallback",
                "confidence": 0.8,
                "metadata": {"table_name": main_table, "column_name": column_name},
            }
        )

    return {
        "execution_strategy": "query_graph",
        "query_type": "detail_query",
        "selected_assets": selected_assets,
        "limit": min(
            int(kwargs.get("query_constraints", {}).get("default_limit", 10000) or 10000), 10000
        ),
    }
