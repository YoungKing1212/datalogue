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
from agentscope.tool import FunctionTool, ToolBase, ToolChunk

from app.agentscope_service.bi_worker_context import BIWorkerContextProvider
from app.agentscope_service.bi_worker_contracts import BIWorkerQueryPlan
from app.agentscope_service.bi_worker_runtime import BIWorkerQueryRuntime
from app.agentscope_service.bi_worker_validator import BIWorkerQueryValidator, ProgressiveContextState
from app.agentscope_service.dataset_query_executor import execute_dataset_query_for_agent_team
from app.agentscope_service.progress_bridge import publish_agent_event
from app.core.database import SessionLocal
from app.models.dataset import SemanticDataset
from app.schemas.bi_workbench import sanitize_event_payload


AgentToolFactory = Callable[[str | None, str | None, str | None], Awaitable[list[ToolBase]]]


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


def build_datalogue_progressive_bi_worker_tools(
    worker_context: dict[str, str | None] | None = None,
) -> list[ToolBase]:
    """创建 Agent Team BI Worker 可见的 L0-L5 渐进式上下文工具。"""

    def datalogue_describe_dataset_capability(dataset_id: int, confirmed_question: str) -> ToolChunk:
        """Describe dataset capability before recalling detailed query context."""

        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).describe_dataset_capability(
                dataset_id=dataset_id,
                question=confirmed_question,
            ).model_dump()
        return _tool_success_chunk(payload)

    def datalogue_recall_query_assets(dataset_id: int, confirmed_question: str) -> ToolChunk:
        """Recall coarse query assets for the confirmed dataset and question."""

        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).recall_query_assets(
                dataset_id=dataset_id,
                question=confirmed_question,
            ).model_dump()
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

    def datalogue_profile_candidate_values(
        dataset_id: int,
        confirmed_question: str,
        probes: list[dict[str, Any]],
    ) -> ToolChunk:
        """Profile candidate value probes using safe metadata-only context."""

        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).profile_candidate_values(
                dataset_id=dataset_id,
                question=confirmed_question,
                probes=probes,
            ).model_dump()
        return _tool_success_chunk(payload)

    def datalogue_validate_query_support(
        query_plan: dict[str, Any],
        context_state: dict[str, Any],
    ) -> ToolChunk:
        """Validate whether the current progressive context supports the query plan."""

        plan = BIWorkerQueryPlan.model_validate(query_plan)
        state = ProgressiveContextState(**context_state)
        payload = BIWorkerQueryValidator().validate(plan, state).model_dump()
        return _tool_success_chunk(payload)

    async def datalogue_execute_query_plan(
        dataset_id: int,
        confirmed_question: str,
        query_plan: dict[str, Any],
        context_state: dict[str, Any],
        trace_id: str | None = None,
    ) -> ToolChunk:
        """Execute a validated BI Worker query plan and return safe result refs."""

        plan = BIWorkerQueryPlan.model_validate(query_plan)
        state = ProgressiveContextState(**context_state)
        with SessionLocal() as db:
            runtime = BIWorkerQueryRuntime(db)
            payload = await runtime.execute_query_plan(
                dataset_id=dataset_id,
                confirmed_question=confirmed_question,
                query_plan=plan,
                context_state=state,
                trace_id=trace_id,
            )
            db.commit()  # L5 可能写入 artifact/checkpoint 引用，成功路径统一提交事务。
        if payload.get("datalogue_event_type") == "dataset_query_result":
            _publish_worker_business_final(worker_context=worker_context, payload=payload)
        return _tool_success_chunk(payload)

    return [
        FunctionTool(
            datalogue_describe_dataset_capability,
            description="BI Worker L0：描述已确认数据集的业务能力边界，不返回 schema 或明细数据。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        FunctionTool(
            datalogue_recall_query_assets,
            description="BI Worker L1：召回与确认问题相关的数据资产摘要，不展开字段清单或 SQL。",
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
            datalogue_profile_candidate_values,
            description="BI Worker L3：基于元数据画像候选值探针，不访问业务明细数据。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        FunctionTool(
            datalogue_validate_query_support,
            description="BI Worker L4：校验查询计划是否被当前渐进式上下文支持。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        FunctionTool(
            datalogue_execute_query_plan,
            description="BI Worker L5：执行已通过上下文校验的查询计划，只返回安全结果引用。",
            is_concurrency_safe=False,
            is_read_only=False,
        ),
    ]


def build_datalogue_query_dataset_tool(*, worker_context: dict[str, str | None] | None = None) -> FunctionTool:
    """创建 Agent Team worker 可见的 Dataset 查询工具。"""

    async def datalogue_query_dataset(
        dataset_id: int,
        confirmed_question: str,
        task_goal: str | None = None,
        user_confirmation_id: str | None = None,
        routing_rationale: str | None = None,
        trace_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> ToolChunk:
        """Run the confirmed Datalogue Dataset query and return safe result refs."""

        result = await execute_dataset_query_for_agent_team(
            dataset_id=dataset_id,
            confirmed_question=confirmed_question,
            task_goal=task_goal,
            user_confirmation_id=user_confirmation_id,
            routing_rationale=routing_rationale,
            trace_id=trace_id,
            parent_run_id=parent_run_id,
        )
        payload = result.to_tool_payload()
        _publish_worker_business_final(worker_context=worker_context, payload=payload)
        return _tool_success_chunk(payload)

    return FunctionTool(
        datalogue_query_dataset,
        description=(
            "Agent Team BI Worker 的 Datalogue Dataset 查询工具；只返回 answer_summary、"
            "artifact_ref、checkpoint_ref、row_count、column_count。"
        ),
        is_concurrency_safe=False,
        is_read_only=False,
    )


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
