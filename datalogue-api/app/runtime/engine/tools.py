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
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.app.storage import StorageBase
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import FunctionTool, ToolBase, ToolChunk
from pydantic import ValidationError

from app.domains.bi.worker.context import BIWorkerContextProvider
from app.domains.bi.worker.contracts import (
    BIWorkerQueryPlan,
    BIWorkerQueryResult,
    FAILURE_DIAGNOSIS_MAP,
    RepairRequest,
)
from app.domains.bi.worker.runtime import BIWorkerQueryRuntime
from app.domains.bi.worker.validator import ProgressiveContextState
from app.domains.agent_team.progress_bridge import publish_agent_event
from app.core.database import SessionLocal
from app.core.models.dataset import SemanticDataset
from app.core.schemas.bi_workbench import sanitize_event_payload

AgentToolFactory = Callable[[str | None, str | None, str | None], Awaitable[list[ToolBase]]]
logger = logging.getLogger(__name__)

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
    "target_shape": {
        "asset_ref": "asset_or_field_ref_from_L1_or_L2",
        "alias": "entity_alias",
        "field": "field_name",
    },
    "join_requirement_shape": {
        "left_alias": "primary_entity_alias",
        "right_alias": "supporting_entity_alias",
        "relationship_ref": "relationship_ref_from_L2",
        "join_type": "inner",
        "required": True,
        "reason": "为什么必须关联该实体",
        # join_keys 用来显式声明真实 join 字段（例如蓝图 SQL 中的 p.account=ep.person_card）；
        # 不需要时留空列表；禁止把 SQL 片段作为字符串塞进来。
        "join_keys": [
            {"left_field": "left_table_field_name", "right_field": "right_table_field_name"}
        ],
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
                "target": {
                    "asset_ref": "asset:primary.date",
                    "alias": "main",
                    "field": "date_field",
                },
                "operator": "between",
                "value": ["2025-01-01", "2025-12-31"],
                "reason": "限定用户指定时间范围",
            }
        ],
        "selects": [
            {
                "target": {
                    "asset_ref": "asset:primary.content",
                    "alias": "main",
                    "field": "content_field",
                },
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
                "target": {
                    "asset_ref": "asset:primary.metric",
                    "alias": "main",
                    "field": "metric_field",
                },
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
            return (
                []
            )  # Dataset 查询只能由 Team worker 调用；拿不到身份时 fail-closed，避免 Leader 直接查数。
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


def _safe_plan_contract_error_details(exc: Exception) -> list[dict[str, Any]]:
    """生成面向 BI Worker 的中文契约诊断，不回显原始输入值。"""

    if isinstance(exc, ValidationError):
        details = []
        for item in exc.errors(include_url=False, include_context=False, include_input=False):
            code = str(item.get("type") or "validation_error")
            loc = tuple(item.get("loc") or ("root",))
            path = _safe_plan_contract_detail_path(code=code, loc=loc)
            details.append(
                {
                    "code": code,
                    "path": path,
                    "message": _plan_contract_error_message(code=code, loc=loc),
                    "expected": _plan_contract_error_expected(code=code, loc=loc),
                }
            )
        return sorted(details, key=lambda item: (item["path"], item["code"])) or [
            {
                "code": "validation_error",
                "path": "root",
                "message": "Query Plan 未通过 BI Worker 契约校验。",
                "expected": "按 query_plan_contract_hint 重新生成完整 Query Plan。",
            }
        ]
    return [
        {
            "code": type(exc).__name__,
            "path": "context_state",
            "message": "context_state 形状不符合 BI Worker 渐进式上下文契约。",
            "expected": BI_WORKER_QUERY_PLAN_CONTRACT_HINT["context_state_usage"],
        }
    ]


def _safe_plan_contract_detail_path(*, code: str, loc: tuple[Any, ...]) -> str:
    """详情 path 只暴露契约位置；顶层额外字段名可能来自模型臆造，统一收敛。"""

    if code == "extra_forbidden" and len(loc) == 1:
        return "root.extra_field"
    return ".".join(str(part) for part in loc)


def _plan_contract_error_message(*, code: str, loc: tuple[Any, ...]) -> str:
    path = _safe_plan_contract_detail_path(code=code, loc=loc)
    field_name = str(loc[-1]) if loc else "root"
    if code == "missing":
        if _is_join_requirement_path(loc):
            return f"`{path}` 缺失，关联关系必须声明左右实体 alias 和关系引用。"
        return f"`{path}` 缺失，Query Plan 必须补齐该必填字段。"
    if code == "extra_forbidden":
        if _is_join_requirement_path(loc):
            return f"`{path}` 是额外字段，BI Worker JoinRequirement 不接收 `{field_name}`。"
        return f"`{path}` 是额外字段，BI Worker 安全契约默认拒绝未声明字段。"
    if code == "literal_error":
        if path.endswith(".operator"):
            return "`filters.*.operator` 使用了不被允许的操作符。"
        if path.endswith(".join_type"):
            return "`join_requirements.*.join_type` 使用了不被允许的关联类型。"
        return f"`{path}` 的枚举值不在契约允许范围内。"
    if code == "value_error":
        return (
            "Query Plan 的业务形状不完整，例如 detail_query 缺 selects 或 metric_query 缺 metrics。"
        )
    return f"`{path}` 未通过 `{code}` 校验。"


def _plan_contract_error_expected(*, code: str, loc: tuple[Any, ...]) -> str:
    path = _safe_plan_contract_detail_path(code=code, loc=loc)
    field_name = str(loc[-1]) if loc else "root"
    if _is_join_requirement_path(loc):
        replacement = {
            "left": "删除 left，改用 left_alias，值必须来自 data_graph.primary_entity/supporting_entities 的 alias。",
            "right": "删除 right，改用 right_alias，值必须来自 data_graph.primary_entity/supporting_entities 的 alias。",
            "type": "删除 type，改用 join_type，通常填写 inner 或 left。",
            "left_asset_ref": "删除 left_asset_ref，关联两端用 left_alias/right_alias 表达，真实关系用 relationship_ref 表达。",
            "right_asset_ref": "删除 right_asset_ref，关联两端用 left_alias/right_alias 表达，真实关系用 relationship_ref 表达。",
            "left_alias": "补充 left_alias，值必须是 data_graph 中左侧实体的 alias，例如 main。",
            "right_alias": "补充 right_alias，值必须是 data_graph 中右侧实体的 alias，例如 person。",
            "relationship_ref": "补充 relationship_ref，值必须来自 L2 schema slice 返回的 relationship_ref。",
            "reason": "补充 reason，用一句业务话说明为什么必须关联该实体。",
            # LLM 常见错误：把 SQL 片段塞进 join_condition 字符串。正确做法是使用结构化 join_keys。
            "join_condition": (
                "删除 join_condition，禁止把 SQL 片段作为字符串传入。若需要显式声明 join 键，"
                '改用 join_keys=[{"left_field": "左表字段名", "right_field": "右表字段名"}]，'
                "字段名必须来自 L2 schema slice 返回的物理列。"
            ),
        }.get(field_name)
        if replacement:
            return replacement
        return (
            "join_requirements 的合法形状是 left_alias/right_alias/relationship_ref/"
            "join_type/required/reason/join_keys。"
        )
    if path.endswith(".operator"):
        allowed = ", ".join(BI_WORKER_QUERY_PLAN_CONTRACT_HINT["allowed_filter_operators"])
        return f"把 operator 改为允许值之一：{allowed}。例如等值筛选使用 `=`，不要使用 `eq`。"
    if path.endswith(".target"):
        return "target 必须包含 asset_ref、alias、field，且引用来自 L1/L2 返回的资产或字段。"
    if code == "extra_forbidden":
        return "删除该字段；只保留 query_plan_contract_hint 中列出的字段。"
    if code == "missing":
        return (
            "补齐该字段；顶层和嵌套结构以 query_plan_contract_hint 的 minimal_*_query_plan 为准。"
        )
    if code == "value_error":
        return "detail_query 至少提供 selects；metric_query 至少提供 metrics。"
    return "按 query_plan_contract_hint 重新生成对应位置的结构。"


def _is_join_requirement_path(loc: tuple[Any, ...]) -> bool:
    return len(loc) >= 2 and loc[0] == "join_requirements"


def _bi_worker_plan_contract_repair_payload(
    *, failure_counts: dict[str, int], exc: Exception
) -> dict[str, Any]:
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
        "validation_error_details": _safe_plan_contract_error_details(exc),
        "query_plan_contract_hint": BI_WORKER_QUERY_PLAN_CONTRACT_HINT,
    }


async def _is_team_worker(
    *, storage: StorageBase | None, user_id: str | None, agent_id: str | None
) -> bool:
    """判断当前工具装配对象是否是 AgentScope Team worker。"""

    return (
        await _team_worker_context(
            storage=storage, user_id=user_id, agent_id=agent_id, session_id=None
        )
        is not None
    )


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


class DatalogueBIWorkerReadOnlyTool(FunctionTool):
    """所有 BI Worker 只读 progressive tools 的通用基类。

    绕过 AgentScope 2.0.3 DONT_ASK 权限引擎在 SubAgentTemplate 场景下
    对 FunctionTool 的误拦截：默认策略会把新出现/未预注册的工具当作
    需要用户 confirmation 甚至直接 DENY。BI Worker 内部的只读工具
    (search_assets/prepare_query_context/request_schema_slice/
    describe_tables/repair_query_plan/select_candidate_datasets)
    都是安全内省能力,无副作用,统一 ALLOW。
    执行类工具 (execute_query_plan_bundle) 因为 is_read_only=False
    继续走原权限引擎,不能套用此基类。
    """

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message=f"{self.name} is always allowed for BI workers.",
            decision_reason="ALLOWED_BY_TOOL",
        )


# 向后兼容别名:曾经只给 search_assets 用的类名,现在保留为别名避免破坏引用。
DatalogueSearchAssetsTool = DatalogueBIWorkerReadOnlyTool


def build_datalogue_search_assets_tool(
    *, worker_context: dict[str, str | None] | None = None
) -> DatalogueSearchAssetsTool:
    """列出数据集下所有候选蓝图、指标、维度；蓝图只作为 QueryPlan 生成参考。"""

    def datalogue_search_assets(dataset_id: int) -> ToolChunk:
        """列出已确认数据集的所有蓝图、指标和维度候选清单。

        蓝图含 call_template（SQL 模板）和 parameters（参数提取规则），
        命中后用于提取筛选参数和选择字段；真实执行仍必须走 QueryPlan bundle。

        Args:
            dataset_id: 已被用户确认的数据集 ID；工具会返回该数据集下所有可选蓝图、指标、维度。
        """
        _ = worker_context
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).search_assets(dataset_id=dataset_id)
        return _tool_success_chunk(payload)

    return DatalogueSearchAssetsTool(
        datalogue_search_assets,
        name="datalogue_search_assets",
        description="列出数据集下所有蓝图、指标和维度；蓝图命中时作为 QueryPlan 生成参考，不直接执行 SQL。",
        is_concurrency_safe=True,
        is_read_only=True,
    )


def build_datalogue_progressive_bi_worker_tools(
    worker_context: dict[str, str | None] | None = None,
) -> list[ToolBase]:
    """创建 Agent Team BI Worker 可见的查询工具集。"""

    plan_contract_failure_counts: dict[str, int] = {}

    def datalogue_prepare_query_context(dataset_id: int, confirmed_question: str) -> ToolChunk:
        """描述数据集能力并召回本轮问题相关的查询资产（合并 L0+L1）。

        返回统一的查询上下文摘要：数据集能力概况、可用蓝图/指标/维度候选，
        为后续 request_schema_slice 与 execute_query_plan_bundle 提供入口线索。

        Args:
            dataset_id: 已被用户确认的数据集 ID。
            confirmed_question: 用户已经确认的自然语言查询问题；用于按问题语义召回相关资产。
        """

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
        """请求数据集全部表清单与跨表关系（含真实 join keys），面向 QueryPlan 生成。

        字段级细节请改用 datalogue_describe_tables 逐表按需拉取，
        本工具只返回 asset 级形状：table_refs / relationship_refs 等。

        Args:
            dataset_id: 已确认的数据集 ID。
            confirmed_question: 用户确认的问题文本；用于按语义收敛 schema slice 输出。
            focus: 可选聚焦提示，如 {"table_names": ["orders", "users"]} 或
                {"metrics": ["gmv"]}，用于告知后端 preferred 表/字段范围；不传则返回全量结构。
        """

        with SessionLocal() as db:
            payload = (
                BIWorkerContextProvider(db)
                .request_schema_slice(
                    dataset_id=dataset_id,
                    question=confirmed_question,
                    focus=focus,
                )
                .model_dump()
            )
        return _tool_success_chunk(payload)

    def datalogue_describe_tables(
        dataset_id: int,
        table_names: list[str],
    ) -> ToolChunk:
        """按表名精确返回指定表的字段清单、字段注释和前 3 条样例值，一次可查多张表。

        用于在 request_schema_slice 之后针对候选表补齐字段细节，
        避免一次性拉取整个 schema 造成上下文膨胀；空列表会 fail-closed 返回 TABLE_NAMES_REQUIRED。

        Args:
            dataset_id: 已确认的数据集 ID。
            table_names: 需要描述的物理表名列表；必须为非空 list，允许一次传多张表。
        """

        # table_names 必填、必须为非空 list;fail-closed 返回错误 payload
        if not isinstance(table_names, list) or not table_names:
            return _tool_success_chunk(
                {
                    "status": "failed",
                    "code": "TABLE_NAMES_REQUIRED",
                    "message": "table_names 必须是非空 list,一次可传多张表。",
                }
            )
        with SessionLocal() as db:
            payload = BIWorkerContextProvider(db).describe_tables(
                dataset_id=dataset_id,
                table_names=table_names,
            )
        return _tool_success_chunk(payload)

    async def datalogue_execute_query_plan_bundle(
        dataset_id: int,
        confirmed_question: str,
        query_plan: dict[str, Any],
        context_state: dict[str, Any],
        trace_id: str | None = None,
    ) -> ToolChunk:
        """校验查询计划的支持度并执行，一次返回结果摘要或失败诊断（合并 L4+L5）。

        契约层会先按 BIWorkerQueryPlan 校验 query_plan 结构，
        校验失败自动进入 Repair 链路返回可回填的 hint；校验通过后由 BIWorkerQueryRuntime
        编译并执行 SQL，最终产出 artifact_ref、row_count、column_count 等安全摘要。

        Args:
            dataset_id: 已确认的数据集 ID。
            confirmed_question: 用户已确认的自然语言问题；用于结果摘要与失败诊断的语境化描述。
            query_plan: 结构化查询计划 dict，形状必须匹配 query_plan_contract_hint。
                至少包含 intent/result_shape/data_graph/filters/selects 或 metrics 等顶层字段。
            context_state: 渐进式上下文状态 dict，形状匹配 ProgressiveContextState（例如
                asset_refs / relationship_refs / field_refs / lookup_dependencies 等）；
                多余字段会被安全过滤。
            trace_id: 可选调用追踪 ID，透传到 runtime 与 artifact 落库以便串联日志。
        """

        # wrapper 入口摘要:一眼看到 LLM 传入的顶层 keys 和 dimension 规模,
        # 便于反查契约错误(pydantic ValidationError 在这里就挂,进不到 runtime)。
        logger.info(
            "[datalogue_execute_query_plan_bundle] REQUEST dataset_id=%s trace_id=%s "
            "query_plan_keys=%s context_state_keys=%s question_len=%d",
            dataset_id,
            trace_id,
            (
                sorted(query_plan.keys())[:20]
                if isinstance(query_plan, dict)
                else type(query_plan).__name__
            ),
            (
                sorted(context_state.keys())[:20]
                if isinstance(context_state, dict)
                else type(context_state).__name__
            ),
            len(confirmed_question or ""),
        )

        try:
            plan = BIWorkerQueryPlan.model_validate(query_plan)
            # 打印完整 query_plan 结构，便于排查 LLM 生成的 DSL 是否与校验规则对齐
            logger.info(
                "[datalogue_execute_query_plan_bundle] QUERY_PLAN dataset_id=%s trace_id=%s "
                "intent=%s primary_entity=%s supporting_entities=%d "
                "selects=%s metrics=%s filters=%s join_requirements=%s",
                dataset_id,
                trace_id,
                plan.intent,
                plan.data_graph.primary_entity.asset_ref,
                len(plan.data_graph.supporting_entities),
                [s.target.asset_ref for s in (plan.selects or [])],
                [m.target.asset_ref for m in (plan.metrics or [])],
                [json.dumps(f.model_dump(), ensure_ascii=False) for f in (plan.filters or [])],
                [json.dumps(j.model_dump(), ensure_ascii=False) for j in (plan.join_requirements or [])],
            )
            # 只保留 ProgressiveContextState 认识的字段；
            # LLM 可能把 prepare_query_context 返回的 dataset_summary 等额外字段一并传入。
            valid_keys = ProgressiveContextState.field_names()
            filtered_state = {
                key: value for key, value in context_state.items() if key in valid_keys
            }
            dropped_keys = [k for k in context_state.keys() if k not in valid_keys]
            if dropped_keys:
                logger.info(
                    "[datalogue_execute_query_plan_bundle] context_state 过滤未知 keys "
                    "dataset_id=%s trace_id=%s dropped=%s",
                    dataset_id,
                    trace_id,
                    dropped_keys[:20],
                )
            state = ProgressiveContextState(**filtered_state)
        except (TypeError, ValidationError) as exc:
            # 契约错误:直接进入 Repair 链路 A。记录错误摘要便于事后排查 LLM 传入结构。
            logger.warning(
                "[datalogue_execute_query_plan_bundle] CONTRACT ERROR dataset_id=%s "
                "trace_id=%s exc_type=%s signature=%s",
                dataset_id,
                trace_id,
                type(exc).__name__,
                _safe_plan_contract_signature(exc),
            )
            return _tool_success_chunk(
                _bi_worker_plan_contract_repair_payload(
                    failure_counts=plan_contract_failure_counts,
                    exc=exc,
                )
            )
        try:
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
        except Exception:
            logger.exception(
                "BI Worker query plan execution failed: dataset_id=%s trace_id=%s",
                dataset_id,
                trace_id,
            )
            diagnosis = FAILURE_DIAGNOSIS_MAP["EXECUTE_FAILED"]
            payload = BIWorkerQueryResult(
                answer_summary="查询执行失败（受控查询运行时异常）。",
                artifact_ref=None,
                checkpoint_ref=None,
                row_count=None,
                column_count=None,
                failure_type="EXECUTE_FAILED",
                safe_diagnosis=diagnosis["safe_diagnosis"],
                recommended_action=diagnosis["recommended_action"],
            ).to_tool_payload()
        if (
            payload.get("datalogue_event_type") == "dataset_query_result"
            and payload.get("status") == "completed"
        ):
            _publish_worker_business_final(worker_context=worker_context, payload=payload)

        # 结果分类日志:让运维/开发用一行就能看清最终 outcome(成功/失败类型)。
        # runtime 层已经打过详细失败原因,这里只做面向 wrapper 的收口摘要。
        status = payload.get("status")
        failure_type = payload.get("failure_type")
        if status == "completed" and not failure_type:
            logger.info(
                "[datalogue_execute_query_plan_bundle] RESPONSE OK dataset_id=%s trace_id=%s "
                "row_count=%s artifact_ref=%s",
                dataset_id,
                trace_id,
                payload.get("row_count"),
                payload.get("artifact_ref"),
            )
        else:
            logger.warning(
                "[datalogue_execute_query_plan_bundle] RESPONSE FAILED dataset_id=%s "
                "trace_id=%s status=%s failure_type=%s event_type=%s",
                dataset_id,
                trace_id,
                status,
                failure_type,
                payload.get("datalogue_event_type"),
            )
        return _tool_success_chunk(payload)

    def datalogue_repair_query_plan(
        failure_type: str,
        current_query_plan: dict[str, Any] | None = None,
        context_state: dict[str, Any] | None = None,
    ) -> ToolChunk:
        """基于失败类型返回可执行的查询计划修复建议，用于 execute 失败后的自愈重试。

        工具内部按 failure_type 命中 RepairRequest 模板，返回 safe_reason、
        recommended_action 与结构化 hints；同类失败次数达到上限后会置 stop_retry=True，
        由 BI Worker 上层决定停止重试并汇报 leader。

        Args:
            failure_type: 失败类型枚举字符串，允许值包括 FIELD_NOT_FOUND、
                FILTER_MISSING、AGGREGATION_WRONG、VALUE_BINDING_FAILED、SQL_GUARD_BLOCKED、
                EMPTY_RESULT；未识别值会兜底为 FIELD_NOT_FOUND。
            current_query_plan: 上一次尝试的查询计划 dict，可选；用于让 hint 定位到具体字段路径。
            context_state: 上一次的渐进式上下文状态 dict，可选；用于让 hint 引用已知的
                asset_refs / relationship_refs 等参考。
        """

        retry_key = f"repair:{failure_type}"
        retry_attempt = plan_contract_failure_counts.get(retry_key, 0) + 1
        total_repair = plan_contract_failure_counts.get(_BI_WORKER_REPAIR_ATTEMPT_KEY, 0) + 1
        plan_contract_failure_counts[retry_key] = retry_attempt
        plan_contract_failure_counts[_BI_WORKER_REPAIR_ATTEMPT_KEY] = total_repair

        stop_retry = (
            retry_attempt > _BI_WORKER_REPAIR_MAX_RETRIES
            or total_repair > _BI_WORKER_REPAIR_MAX_RETRIES
        )
        valid_failure_types = {
            "FIELD_NOT_FOUND",
            "FILTER_MISSING",
            "AGGREGATION_WRONG",
            "VALUE_BINDING_FAILED",
            "SQL_GUARD_BLOCKED",
            "EMPTY_RESULT",
            "EXECUTE_FAILED",
        }
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
        DatalogueBIWorkerReadOnlyTool(
            datalogue_prepare_query_context,
            description="BI Worker L0+L1：描述数据集能力并召回相关资产，返回统一查询上下文。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        DatalogueBIWorkerReadOnlyTool(
            datalogue_request_schema_slice,
            description="BI Worker L2a:返回数据集全部表清单和跨表关系(含蓝图 SQL 解析的真实 join keys),字段详情走 datalogue_describe_tables。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        DatalogueBIWorkerReadOnlyTool(
            datalogue_describe_tables,
            description="BI Worker L2b:按 table_names 精确返回指定表的字段清单/注释/前 3 条样例值,一次可查多张表。",
            is_concurrency_safe=True,
            is_read_only=True,
        ),
        FunctionTool(
            datalogue_execute_query_plan_bundle,
            description="BI Worker L4+L5：校验查询计划支持度并执行，一路返回结果或失败诊断。",
            is_concurrency_safe=False,
            is_read_only=False,
        ),
        DatalogueBIWorkerReadOnlyTool(
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
        """在缺少 dataset_id 时，根据用户问题筛选候选数据集卡片供用户二次确认。

        返回值只包含 dataset_id/dataset_name/reason/score 等安全字段，
        不返回 schema、SQL、raw rows 或字段明细；候选存在时会同时下发一次
        message.completed SSE 兜底事件，避免 LLM 忘记 TeamSay 导致空 final。

        Args:
            question: 用户当前的自然语言查询问题；用于按名称/描述/同义词做关键词匹配。
            limit: 期望返回的候选数量上限，默认 5，安全区间为 1~8，超出会被夹紧到该区间。
        """

        safe_limit = max(1, min(int(limit or 5), 8))
        payload = select_candidate_datasets_for_agent_team(question=question, limit=safe_limit)
        safe_payload = sanitize_event_payload(payload)
        if not isinstance(safe_payload, dict):
            safe_payload = {"summary": "BI worker 未能生成候选数据集。"}
        if safe_payload.get("requires_user_confirmation"):
            # 候选数据集确认是本轮用户可见终点；即使 LLM 忘记调用 TeamSay，也不能让主链落到空 final。
            _publish_worker_business_final(worker_context=worker_context, payload=safe_payload)
        return _tool_success_chunk(safe_payload)

    return DatalogueBIWorkerReadOnlyTool(
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
    summary = (
        "BI worker 已筛选候选数据集，请用户确认。" if candidates else "未找到可供选择的数据集。"
    )
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


def _dataset_candidate_payload(
    *, dataset: SemanticDataset, score: int, matched: bool
) -> dict[str, Any]:
    dataset_name = str(dataset.name or f"数据集 {dataset.id}")[:100]
    reason = "名称或描述与本轮问题匹配。" if matched and score > 0 else "可供用户确认选择。"
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset_name,
        "reason": reason,
        "score": score,
        "requires_confirmation": True,
    }
