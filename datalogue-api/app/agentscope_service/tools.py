# ============================================================
# File Name   : tools.py
# Description:
#   AgentScope Service 侧 Datalogue Dataset Tool 注册入口。
#
# Responsibilities:
#   - 暴露 create_app extra_agent_tools 可消费的异步工具 factory。
#   - 用 AgentScope FunctionTool 注册 Agent Team worker 可调用的候选数据集筛选和查询工具。
#   - 将工具返回值收口为安全 JSON 文本块，避免泄露查询语句、表结构或明细行。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.app.storage import StorageBase
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, ToolBase, ToolChunk
from pydantic import ValidationError

from app.agentscope_service.bi_worker_context import BIWorkerContextProvider
from app.agentscope_service.bi_worker_contracts import (
    BIWorkerQueryPlan,
    RepairRequest,
)
from app.agentscope_service.bi_worker_runtime import BIWorkerQueryRuntime
from app.agentscope_service.bi_worker_validator import ProgressiveContextState
from app.agentscope_service.progress_bridge import publish_agent_event
from app.core.database import SessionLocal
from app.models.dataset import SemanticDataset
from app.schemas.bi_workbench import sanitize_event_payload


AgentToolFactory = Callable[[str | None, str | None, str | None], Awaitable[list[ToolBase]]]

BI_WORKER_PLAN_CONTRACT_MAX_RETRIES = 1
_BI_WORKER_PLAN_CONTRACT_TOTAL_ATTEMPT_KEY = "__total_contract_attempts__"
_BI_WORKER_REPAIR_MAX_RETRIES = 2
_BI_WORKER_REPAIR_ATTEMPT_KEY = "__total_repair_attempts__"

BI_WORKER_QUERY_PLAN_CONTRACT_HINT = {
    "required_top_level_fields": [
        "intent",
        "question",
        "result_shape",
        "data_graph",
        "join_requirements",
        "filters",
        "selects",
        "metrics",
        "group_by",
        "ordering",
        "assumptions",
    ],
    "detail_query_required_field": "selects",
    "metric_query_required_field": "metrics",
    "allowed_filter_operators": ["=", "!=", ">", ">=", "<", "<=", "between", "in", "contains"],
    "target_shape": {"asset_ref": "asset_or_field_ref_from_L1_or_L2", "alias": "entity_alias", "field": "field_name"},
    "join_requirement_shape": {
        "left_alias": "primary_entity_alias",
        "right_alias": "supporting_entity_alias",
        "relationship_ref": "relationship_ref_from_L2",
        "join_type": "inner",
        "required": True,
        "reason": "为什么必须关联该实体",
    },
    "context_state_shape": {
        "asset_refs": ["asset_ref_from_L2"],
        "relationship_refs": ["relationship_ref_from_L2"],
        "field_refs": ["field_ref_from_L2"],
        "lookup_dependencies": {},
        "missing_context_history": [],
        "l2_request_count": 0,
        "l3_profile_count": 0,
        "validation_more_context_count": 0,
    },
    "context_state_usage": "优先合并 L2 返回的 context_state_patch；不要从 l0_summary/l1_assets/l2_entities 摘要手写 context_state。",
    "minimal_detail_query_plan": {
        "intent": "detail_query",
        "question": "用户确认后的问题",
        "result_shape": {"type": "table", "grain": "one_row_per_business_record", "limit": 100},
        "data_graph": {
            "primary_entity": {"asset_ref": "asset:primary", "alias": "main", "role": "primary"},
            "supporting_entities": [],
        },
        "join_requirements": [],
        "filters": [
            {
                "target": {"asset_ref": "asset:primary.date", "alias": "main", "field": "date_field"},
                "operator": "between",
                "value": ["2025-01-01", "2025-12-31"],
                "reason": "限定用户指定时间范围",
            }
        ],
        "selects": [
            {
                "target": {"asset_ref": "asset:primary.content", "alias": "main", "field": "content_field"},
                "display_name": "展示名称",
                "display_semantic": "业务含义",
                "requires_decoding": False,
            }
        ],
        "metrics": [],
        "group_by": [],
        "ordering": [],
        "assumptions": [],
    },
    "minimal_metric_query_plan": {
        "intent": "metric_query",
        "question": "用户确认后的指标问题",
        "result_shape": {"type": "metric", "grain": "overall", "limit": 100},
        "data_graph": {
            "primary_entity": {"asset_ref": "asset:primary", "alias": "main", "role": "primary"},
            "supporting_entities": [],
        },
        "join_requirements": [],
        "filters": [],
        "selects": [],
        "metrics": [
            {
                "target": {"asset_ref": "asset:primary.metric", "alias": "main", "field": "metric_field"},
                "aggregation": "sum",
                "display_name": "指标名称",
            }
        ],
        "group_by": [],
        "ordering": [],
        "assumptions": [],
    },
}


def build_datalogue_extra_agent_tools(*, storage: StorageBase | None = None) -> AgentToolFactory:
    """构建 AgentScope create_app(extra_agent_tools=...) 可直接使用的工具工厂。"""

    async def _extra_agent_tools(
        user_id: str | None,
        agent_id: str | None,
        session_id: str | None,
    ) -> list[ToolBase]:
        # AgentScope Service 已经从 workspace 和 planner 注入 Bash/Read/Write/Edit/Task*；
        # extra_agent_tools 只返回 Datalogue 自有业务工具，避免 basic 组内同名覆盖警告。
        worker_context = await _team_worker_context(
            storage=storage,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
        )
        if worker_context is None:
            return []  # Dataset 查询只能由 Team worker 调用；拿不到身份时 fail-closed，避免 Leader 直接查数。
        return [
            build_datalogue_search_assets_tool(worker_context=worker_context),
            build_datalogue_select_candidate_datasets_tool(worker_context=worker_context),
            *build_datalogue_progressive_bi_worker_tools(worker_context=worker_context),
        ]

    return _extra_agent_tools


def _tool_success_chunk(payload: dict[str, Any]) -> ToolChunk:
    """把 BI Worker 工具 payload 统一封装为 AgentScope SDK 的成功 ToolChunk。"""

    return ToolChunk(
        content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))],
        state=ToolResultState.SUCCESS,
    )


def _safe_plan_contract_signature(exc: Exception) -> str:
    """把契约错误压缩成不含用户输入、字段明细或 SQL 的稳定签名。"""

    if isinstance(exc, ValidationError):
        parts = []
        for item in exc.errors(include_url=False, include_context=False, include_input=False):
            loc = ".".join(str(part) for part in item.get("loc") or ("root",))
            parts.append(f"{item.get('type', 'validation_error')}:{loc}")
        return "|".join(sorted(parts)) or "validation_error"
    return type(exc).__name__


def _safe_plan_contract_error_summary(exc: Exception) -> list[str]:
    """返回只包含错误类型和位置的摘要，不回显用户输入、SQL 或原始 schema。"""

    if isinstance(exc, ValidationError):
        summary = []
        for item in exc.errors(include_url=False, include_context=False, include_input=False):
            loc = ".".join(str(part) for part in item.get("loc") or ("root",))
            summary.append(f"{item.get('type', 'validation_error')}:{loc}")
        return sorted(summary) or ["validation_error"]
    # TypeError 通常是 context_state 传入了意外字段（如 dataset_summary），
    # 把错误信息安全地暴露给 LLM 可帮助其自修复。
    return [f"{type(exc).__name__}: {exc}"]


def _bi_worker_plan_contract_repair_payload(*, failure_counts: dict[str, int], exc: Exception) -> dict[str, Any]:
    """生成可回传给 Agent 的安全修复提示，避免同类契约错误耗满 ReAct 轮次。"""

    signature = _safe_plan_contract_signature(exc)
    signature_attempt = failure_counts.get(signature, 0) + 1
    total_attempt = failure_counts.get(_BI_WORKER_PLAN_CONTRACT_TOTAL_ATTEMPT_KEY, 0) + 1
    failure_counts[signature] = signature_attempt
    failure_counts[_BI_WORKER_PLAN_CONTRACT_TOTAL_ATTEMPT_KEY] = total_attempt
    # 同类错误和变体错误都要止损：Agent 改变错误形态时不能重置整体重试预算。
    stop_retry = (
        signature_attempt > BI_WORKER_PLAN_CONTRACT_MAX_RETRIES
        or total_attempt > BI_WORKER_PLAN_CONTRACT_MAX_RETRIES
    )
    return {
        "datalogue_event_type": "bi_worker_repair_request",
        "repair_status": "failed" if stop_retry else "needs_plan_revision",
        "failure_stage": "validate",
        "failure_class": "query_plan_contract_error",
        "safe_reason": "Query Plan JSON 未符合 BI Worker 安全契约，查询尚未执行。",
        "recommended_action": (
            "停止重试，使用 TeamSay 向 leader 汇报需要澄清查询计划字段结构。"
            if stop_retry
            else "按 query_plan_contract_hint 修正后最多再重试一次。"
        ),
        "retry_policy": {
            "attempt": signature_attempt,
            "signature_attempt": signature_attempt,
            "total_attempt": total_attempt,
            "max_retries": BI_WORKER_PLAN_CONTRACT_MAX_RETRIES,
            "stop_retry": stop_retry,
        },
        "validation_error_summary": _safe_plan_contract_error_summary(exc),
        "query_plan_contract_hint": BI_WORKER_QUERY_PLAN_CONTRACT_HINT,
    }


async def _is_team_worker(*, storage: StorageBase | None, user_id: str | None, agent_id: str | None) -> bool:
    """判断当前工具装配对象是否是 AgentScope Team worker。"""

    return await _team_worker_context(storage=storage, user_id=user_id, agent_id=agent_id, session_id=None) is not None


async def _team_worker_context(
    *,
    storage: StorageBase | None,
    user_id: str | None,
    agent_id: str | None,
    session_id: str | None,
) -> dict[str, str | None] | None:
    """读取 Team worker 的安全业务上下文；身份不满足时返回 None。"""

    if storage is None or not user_id or not agent_id:
        return None
    agent_record = await storage.get_agent(user_id, agent_id)
    if not agent_record or agent_record.source != "team":
        return None
    agent_data = getattr(agent_record, "data", None)
    agent_name = getattr(agent_data, "name", None)
    return {
        "user_id": user_id,
        "agent_id": agent_id,
        "agent_name": str(agent_name) if agent_name else None,
        "session_id": session_id,
    }


class DatalogueSearchAssetsTool(FunctionTool):
    """datalogue_search_assets 的自定义 FunctionTool，绕过 AgentScope 2.0.3 DONT_ASK
    权限引擎在 SubAgentTemplate 场景下对 FunctionTool 的误拦截。"""

    async def check_permissions(self, **kwargs: Any) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="datalogue_search_assets is always allowed for BI workers.",
            decision_reason="ALLOWED_BY_TOOL",
        )


def build_datalogue_search_assets_tool(
    *, worker_context: dict[str, str | None] | None = None
) -> DatalogueSearchAssetsTool:
    """列出数据集下所有候选蓝图、指标、维度，命中蓝图时可走 SQL 模板快速路径。"""

    def datalogue_search_assets(dataset_id: int) -> ToolChunk:
        """List all blueprints, metrics and dimensions for the confirmed dataset.

        蓝图含 call_template（SQL 模板）和 parameters（参数提取规则），
        命中后直接填参构造 SQL 执行，跳过 L0/L1/L2/L5 渐进式探索。
        """
        _ = worker_context
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).search_assets(dataset_id=dataset_id)
        return _tool_success_chunk(payload)

    return DatalogueSearchAssetsTool(
        datalogue_search_assets,
        name="datalogue_search_assets",
        description="列出数据集下所有蓝图（含SQL模板）、指标和维度，优先用蓝图快速路径。",
        is_concurrency_safe=True,
        is_read_only=True,
    )


def build_datalogue_progressive_bi_worker_tools(
    worker_context: dict[str, str | None] | None = None,
) -> list[ToolBase]:
    """创建 Agent Team BI Worker 可见的查询工具集。"""

    plan_contract_failure_counts: dict[str, int] = {}

    def datalogue_prepare_query_context(dataset_id: int, confirmed_question: str) -> ToolChunk:
        """Describe dataset capability and recall query assets in one step (merged L0+L1)."""

        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).prepare_query_context(
                dataset_id=dataset_id,
                question=confirmed_question,
            )
        return _tool_success_chunk(payload)

    def datalogue_request_schema_slice(
        dataset_id: int,
        confirmed_question: str,
        focus: dict[str, Any] | None = None,
    ) -> ToolChunk:
        """Request a focused schema slice for query planning."""

        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).request_schema_slice(
                dataset_id=dataset_id,
                question=confirmed_question,
                focus=focus,
            ).model_dump()
        return _tool_success_chunk(payload)

    async def datalogue_execute_query_plan_bundle(
        dataset_id: int,
        confirmed_question: str,
        query_plan: dict[str, Any],
        context_state: dict[str, Any],
        trace_id: str | None = None,
    ) -> ToolChunk:
        """Validate plan support then execute in one step (merged L4+L5)."""

        try:
            plan = BIWorkerQueryPlan.model_validate(query_plan)
            # 只保留 ProgressiveContextState 认识的字段；
            # LLM 可能把 prepare_query_context 返回的 dataset_summary 等额外字段一并传入。
            valid_keys = ProgressiveContextState.field_names()
            filtered_state = {
                key: value for key, value in context_state.items()
                if key in valid_keys
            }
            state = ProgressiveContextState(**filtered_state)
        except (TypeError, ValidationError) as exc:
            return _tool_success_chunk(
                _bi_worker_plan_contract_repair_payload(
                    failure_counts=plan_contract_failure_counts,
                    exc=exc,
                )
            )
        with SessionLocal() as db:
            runtime = BIWorkerQueryRuntime(db)
            payload = await runtime.execute_query_plan(
                dataset_id=dataset_id,
                confirmed_question=confirmed_question,
                query_plan=plan,
                context_state=state,
                trace_id=trace_id,
            )
            db.commit()
        if payload.get("datalogue_event_type") == "dataset_query_result" and payload.get("status") == "completed":
            _publish_worker_business_final(worker_context=worker_context, payload=payload)
        return _tool_success_chunk(payload)

    def datalogue_repair_query_plan(
        failure_type: str,
        current_query_plan: dict[str, Any] | None = None,
        context_state: dict[str, Any] | None = None,
    ) -> ToolChunk:
        """Repair a failed query plan with targeted hints based on failure type."""

        retry_key = f"repair:{failure_type}"
        retry_attempt = plan_contract_failure_counts.get(retry_key, 0) + 1
        total_repair = plan_contract_failure_counts.get(_BI_WORKER_REPAIR_ATTEMPT_KEY, 0) + 1
        plan_contract_failure_counts[retry_key] = retry_attempt
        plan_contract_failure_counts[_BI_WORKER_REPAIR_ATTEMPT_KEY] = total_repair

        stop_retry = (
            retry_attempt > _BI_WORKER_REPAIR_MAX_RETRIES
            or total_repair > _BI_WORKER_REPAIR_MAX_RETRIES
        )
        valid_failure_types = {"FIELD_NOT_FOUND", "FILTER_MISSING", "AGGREGATION_WRONG",
                               "VALUE_BINDING_FAILED", "SQL_GUARD_BLOCKED", "EMPTY_RESULT"}
        resolved_type = failure_type if failure_type in valid_failure_types else "FIELD_NOT_FOUND"
        repair = RepairRequest.from_failure_type(
            resolved_type,  # type: ignore[arg-type]
            retry_count=retry_attempt,
        )
        payload = {
            "datalogue_event_type": "bi_worker_repair",
            "repair_status": "no_more_retries" if stop_retry else "retry_with_hint",
            "failure_type": failure_type,
            "safe_reason": repair.safe_reason,
            "recommended_action": repair.recommended_action,
            "stop_retry": stop_retry,
            "retry_attempt": retry_attempt,
            "max_retries": _BI_WORKER_REPAIR_MAX_RETRIES,
            "hints": [
                {
                    "target_field": failure_type,
                    "suggested_action": repair.recommended_action,
                }
            ],
        }
        return _tool_success_chunk(payload)

    return [
        FunctionTool(
            datalogue_prepare_query_context,
            description="BI Worker L0+L1：描述数据集能力并召回相关资产，返回统一查询上下文。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        FunctionTool(
            datalogue_request_schema_slice,
            description="BI Worker L2：按问题焦点返回受控 schema 切片，用于后续查询计划。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        FunctionTool(
            datalogue_execute_query_plan_bundle,
            description="BI Worker L4+L5：校验查询计划支持度并执行，一路返回结果或失败诊断。",
            is_concurrency_safe=False,
            is_read_only=False,
        ),
        FunctionTool(
            datalogue_repair_query_plan,
            description="BI Worker Repair：基于故障类型提供查询计划修复建议。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
    ]


def build_datalogue_select_candidate_datasets_tool(
    *,
    worker_context: dict[str, str | None] | None = None,
) -> FunctionTool:
    """创建 Agent Team BI worker 可见的候选数据集筛选工具。"""

    async def datalogue_select_candidate_datasets(question: str, limit: int = 5) -> ToolChunk:
        """Select safe dataset candidates for user confirmation before querying."""

        safe_limit = max(1, min(int(limit or 5), 8))
        payload = select_candidate_datasets_for_agent_team(question=question, limit=safe_limit)
        safe_payload = sanitize_event_payload(payload)
        if not isinstance(safe_payload, dict):
            safe_payload = {"summary": "BI worker 未能生成候选数据集。"}
        if safe_payload.get("requires_user_confirmation"):
            # 候选数据集确认是本轮用户可见终点；即使 LLM 忘记调用 TeamSay，也不能让主链落到空 final。
            _publish_worker_business_final(worker_context=worker_context, payload=safe_payload)
        return _tool_success_chunk(safe_payload)

    return FunctionTool(
        datalogue_select_candidate_datasets,
        description=(
            "Agent Team BI Worker 的候选数据集筛选工具；用于缺少 dataset_id 时根据用户问题返回"
            "安全候选卡 payload，不返回 schema、SQL、raw rows 或表字段明细。"
        ),
        is_concurrency_safe=True,
        is_read_only=True,
    )


def _publish_worker_business_final(
    *,
    worker_context: dict[str, str | None] | None,
    payload: dict[str, Any],
) -> None:
    """把 BI worker 已脱敏业务结果直投到当前 Datalogue SSE，作为 TeamSay 缺失时的兜底终态。"""

    if not worker_context:
        return
    publish_agent_event(
        user_id=worker_context.get("user_id"),
        event_type="message.completed",
        payload=payload,
    )


def select_candidate_datasets_for_agent_team(*, question: str, limit: int = 5) -> dict[str, Any]:
    """根据用户问题筛选安全数据集候选，只返回前端候选卡需要的字段。"""

    safe_limit = max(1, min(int(limit or 5), 8))
    with SessionLocal() as db:
        datasets = db.query(SemanticDataset).order_by(SemanticDataset.id.desc()).limit(80).all()

    ranked = sorted(
        ((_dataset_match_score(question, dataset), dataset) for dataset in datasets),
        key=lambda item: (item[0], getattr(item[1], "id", 0) or 0),
        reverse=True,
    )
    matched = [item for item in ranked if item[0] > 0]
    selected = (matched or ranked)[:safe_limit]
    candidates = [
        _dataset_candidate_payload(dataset=dataset, score=score, matched=bool(matched))
        for score, dataset in selected
    ]
    decision = "ambiguous" if candidates else "no_match"
    summary = "BI worker 已筛选候选数据集，请用户确认。" if candidates else "未找到可供选择的数据集。"
    route_decision = {
        "decision": decision,
        "dataset_id": None,
        "score": candidates[0]["score"] if candidates else 0,
        "candidates": candidates,
        "reason": "BI worker 根据用户问题筛选出候选数据集，需要用户确认后再执行查询。",
    }
    return {
        "datalogue_event_type": "dataset_candidates",
        "summary": summary,
        "title": "请选择数据集",
        "route_decision": route_decision,
        "clarification": {
            "kind": "dataset_choice",
            "candidates": candidates,
        },
        "requires_user_confirmation": bool(candidates),
    }


def _dataset_match_score(question: str, dataset: SemanticDataset) -> int:
    question_text = _normalize_dataset_match_text(question)
    dataset_text = _normalize_dataset_match_text(
        " ".join(
            str(part or "")
            for part in (
                dataset.name,
                dataset.description,
                dataset.prompt_instructions,
            )
        )
    )
    if not question_text or not dataset_text:
        return 0
    score = 0
    for token in _candidate_match_tokens(question_text):
        if token and token in dataset_text:
            score += max(1, min(len(token), 8))
    if dataset.name and _normalize_dataset_match_text(str(dataset.name)) in question_text:
        score += 10
    return score


def _candidate_match_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)
    # 中文短词没有天然空格；补充常见二字窗口，避免“2025年日志”只因为整段不匹配而漏召回“日志”数据集。
    chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
    tokens.extend(chinese_text[index : index + 2] for index in range(max(0, len(chinese_text) - 1)))
    return list(dict.fromkeys(tokens))


def _normalize_dataset_match_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _dataset_candidate_payload(*, dataset: SemanticDataset, score: int, matched: bool) -> dict[str, Any]:
    dataset_name = str(dataset.name or f"数据集 {dataset.id}")[:100]
    reason = "名称或描述与本轮问题匹配。" if matched and score > 0 else "可供用户确认选择。"
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset_name,
        "reason": reason,
        "score": score,
        "requires_confirmation": True,
    }
