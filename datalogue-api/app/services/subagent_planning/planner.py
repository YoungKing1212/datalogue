# ============================================================
# File Name   : planner.py
# Description:
#   DatasetSubAgent 查询规划的规则规划器与 LLM Planner 编排入口。
#
# Responsibilities:
#   - 在调用 LLM 前执行确定性预判，短路低风险查询计划。
#   - 在 LLM 规划不可用或输出不合法时，根据候选资产生成保守查询计划。
#   - 支持明细查询、指标查询和蓝图缺参澄清的规则分流。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import json
import logging
import re
from json import JSONDecodeError
from copy import deepcopy
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.graph.llm import get_llm
from app.services.subagent_planning.asset_detail import AssetDetailRequest
from app.services.subagent_planning.contracts import (
    CANDIDATE_ASSET_TYPES,
    CandidateAsset,
    QueryPlan,
    QueryPlanValidationError,
    normalize_query_plan,
)

logger = logging.getLogger(__name__)

DETAIL_PATTERNS = ("明细", "列表", "日志", "记录", "最近", "前", "条", "limit")  # LLM 前预判和 fallback 共用信号。
METRIC_PATTERNS = ("统计", "数量", "总数", "平均", "占比", "汇总", "趋势")
AGGREGATE_FIELD_PATTERNS = (
    "总共",
    "一共",
    "合计",
    "总计",
    "累计",
    "多少钱",
    "多少金额",
    "金额",
    "万元",
    "省了",
    "节省",
    "节约",
)
BLUEPRINT_PATTERNS = ("日报", "周报", "月报", "分析", "报告")
LOG_DETAIL_PATTERNS = ("日志", "工作日志", "用户日志", "记录")
DAILY_BLUEPRINT_PATTERNS = ("日报", "个人日报", "任务日报")
BLUEPRINT_MIN_CONFIDENCE = 0.05
PROMPT_ASSET_LIMIT = 40
LIGHTWEIGHT_METADATA_KEYS = {"table_name", "column_name", "parameters", "implementation_type"}
PROMPT_TEXT_LIMIT = 120
PROMPT_LIST_LIMIT = 20
PROMPT_DEPTH_LIMIT = 4
PUBLIC_TEXT_LIMIT = 240
PUBLIC_LIST_LIMIT = 12
PUBLIC_DICT_LIMIT = 20
PUBLIC_DEPTH_LIMIT = 4
LIGHTWEIGHT_ASSET_KEYS = {
    "asset_type",
    "asset_id",
    "name",
    "display_name",
    "source",
    "confidence",
    "usage",
    "match_reason",
    "reject_reason",
}
LIGHTWEIGHT_SIGNAL_KEYS = {"type", "value", "score", "field", "table", "name"}
DETAIL_LOOP_DANGEROUS_PUBLIC_KEYS = {
    "asset_detail_context",
    "columns",
    "column_defs",
    "ddl",
    "expr",
    "field_list",
    "fields",
    "payload",
    "raw_schema",
    "schema",
    "schema_context",
    "schema_structured",
    "sql",
    "sql_template",
    "table_schemas",
}
DETAIL_LOOP_DANGEROUS_TEXT_MARKERS = (
    "asset_detail_context",
    "sql_template",
    "table_schemas",
    "create table",
    "select * from",
    "\"fields\"",
    "'fields'",
    "fields:",
    "field_list",
    "schema:",
    "payload:",
    "expr:",
    "字段列表",
    "字段明细",
)
LLM_ERROR_MODULE_PREFIXES = ("openai", "httpx", "langchain_openai")
LLM_ERROR_TYPE_KEYWORDS = (
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "ConnectError",
    "ConnectionError",
    "HTTPStatusError",
    "OpenAIError",
    "RateLimitError",
    "ReadError",
    "ReadTimeout",
    "RequestError",
    "Timeout",
    "TimeoutException",
    "TransportError",
)


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(pattern.lower() in normalized for pattern in patterns)


CandidateAssetInput = list[dict[str, Any] | CandidateAsset] | dict[str, Any] | None


def _settings_int(name: str, default: int) -> int:
    try:
        value = int(getattr(get_settings(), name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _prompt_asset_limit() -> int:
    return _settings_int("SUBAGENT_PLANNER_PROMPT_ASSET_LIMIT", PROMPT_ASSET_LIMIT)


def _prompt_text_limit() -> int:
    return _settings_int("SUBAGENT_PLANNER_PROMPT_TEXT_LIMIT", PROMPT_TEXT_LIMIT)


def _prompt_list_limit() -> int:
    return _settings_int("SUBAGENT_PLANNER_PROMPT_LIST_LIMIT", PROMPT_LIST_LIMIT)


def _public_text_limit() -> int:
    return _settings_int("SUBAGENT_PLANNER_PUBLIC_TEXT_LIMIT", PUBLIC_TEXT_LIMIT)


def _public_list_limit() -> int:
    return _settings_int("SUBAGENT_PLANNER_PUBLIC_LIST_LIMIT", PUBLIC_LIST_LIMIT)


def _asset_items(candidate_assets: CandidateAssetInput) -> list[dict[str, Any] | CandidateAsset]:
    if isinstance(candidate_assets, dict):
        items = candidate_assets.get("assets")
        return items if isinstance(items, list) else []
    if isinstance(candidate_assets, list):
        return candidate_assets
    return []


def _assets(candidate_assets: CandidateAssetInput) -> list[CandidateAsset]:
    assets: list[CandidateAsset] = []
    for item in _asset_items(candidate_assets):
        try:
            if isinstance(item, CandidateAsset):
                if item.asset_type in CANDIDATE_ASSET_TYPES:
                    assets.append(item)
                continue
            if not isinstance(item, dict):
                continue
            assets.append(CandidateAsset.from_dict(item))
        except (QueryPlanValidationError, TypeError, ValueError):
            continue  # 单个坏资产不能拖垮整轮 planner，后续分支会按剩余资产降级。
    return assets


def _parameter_items(parameters: Any) -> list[dict[str, Any]]:
    if isinstance(parameters, list):
        return [parameter for parameter in parameters if isinstance(parameter, dict)]
    if not isinstance(parameters, dict):
        return []

    items: list[dict[str, Any]] = []
    properties = parameters.get("properties")
    required_names = parameters.get("required")
    required_set = {str(name) for name in required_names} if isinstance(required_names, list) else set()
    if isinstance(properties, dict):
        for name, spec in properties.items():
            item = dict(spec) if isinstance(spec, dict) else {}
            item.setdefault("name", name)
            if name in required_set:
                item["required"] = True
            items.append(item)

    for name, spec in parameters.items():
        if name in {"properties", "required"}:
            continue
        if isinstance(spec, dict):
            item = dict(spec)
            item.setdefault("name", name)
            items.append(item)
        elif isinstance(spec, bool):
            items.append({"name": name, "required": spec})
    return items


def _routing_has_input(routing: Any, name: str) -> bool:
    if not name:
        return False
    if isinstance(routing, dict):
        for key, value in routing.items():
            if str(key) == name and value not in (None, "", [], {}):
                return True
            if _routing_has_input(value, name):
                return True
    elif isinstance(routing, list):
        for item in routing:
            if isinstance(item, dict):
                item_name = item.get("name") or item.get("key")
                item_value = item.get("value") or item.get("resolved_value") or item.get("text")
                if item_name and str(item_name) == name and item_value not in (None, "", [], {}):
                    return True
            if _routing_has_input(item, name):
                return True
    return False


def _required_inputs(blueprint: CandidateAsset | None, routing: Any = None) -> list[dict[str, Any]]:
    if not blueprint:
        return []
    required: list[dict[str, Any]] = []
    for parameter in _parameter_items(blueprint.metadata.get("parameters")):
        if not isinstance(parameter, dict) or not parameter.get("required"):
            continue
        name = parameter.get("name") or parameter.get("key")
        if not name:
            continue
        if _routing_has_input(routing, str(name)):
            continue
        required.append(  # 蓝图缺参转 clarify，避免 blueprint_execute 带空参数执行。
            {
                "name": str(name),
                "required": True,
                "source": "blueprint.parameters",
                "display_name": parameter.get("display_name") or parameter.get("label") or str(name),
            }
        )
    return required


def _with_usage(asset: CandidateAsset, usage: str) -> CandidateAsset:
    return CandidateAsset(
        asset_type=asset.asset_type,
        asset_id=asset.asset_id,
        name=asset.name,
        display_name=asset.display_name,
        source=asset.source,
        confidence=asset.confidence,
        match_signals=deepcopy(asset.match_signals),
        metadata=deepcopy(asset.metadata),
        usage=usage,
        match_reason=asset.match_reason,
        reject_reason=asset.reject_reason,
    )


def _asset_label(asset: CandidateAsset | None) -> str | None:
    if not asset:
        return None
    return str(asset.display_name or asset.name or asset.asset_id)


def _factor(code: str, message: str, evidence: Any = None) -> dict[str, Any]:
    factor = {"code": code, "message": message}
    if evidence not in (None, "", [], {}):
        factor["evidence"] = evidence
    return factor


def _warning(code: str, message: str, evidence: Any = None) -> dict[str, Any]:
    warning = {"code": code, "message": message}
    if evidence not in (None, "", [], {}):
        warning["evidence"] = evidence
    return warning


def _governance_suggestion(
    suggestion_type: str,
    message: str,
    evidence: Any = None,
) -> dict[str, Any]:
    suggestion = {"type": suggestion_type, "message": message}
    if evidence not in (None, "", [], {}):
        suggestion["evidence"] = evidence
    return suggestion


def _fallback_warnings(fallback_reason: str | None) -> list[dict[str, Any]]:
    if not fallback_reason:
        return []
    return [
        _warning(
            "planner_fallback",
            "LLM 查询规划不可用或输出不合法，已切换到规则兜底。",
            fallback_reason,
        )
    ]


def _quality_suggestions(
    *,
    assets: list[CandidateAsset],
    field_table_assets: list[CandidateAsset],
    metric_dimension_assets: list[CandidateAsset],
    blueprint: CandidateAsset | None,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if not assets:
        suggestions.append(
            _governance_suggestion(
                "candidate_assets",
                "当前问题没有召回候选资产，可补充表字段描述、业务术语或分析蓝图触发样例。",
            )
        )
    if assets and not field_table_assets:
        suggestions.append(
            _governance_suggestion(
                "schema_metadata",
                "候选资产中缺少字段或表，建议补充数据集选表和字段业务描述。",
            )
        )
    if assets and not metric_dimension_assets:
        suggestions.append(
            _governance_suggestion(
                "semantic_assets",
                "候选资产中缺少指标或维度，统计类问题可能需要补充语义资产。",
            )
        )
    if blueprint and not blueprint.metadata.get("parameters"):
        suggestions.append(
            _governance_suggestion(
                "blueprint_parameters",
                "命中蓝图缺少参数定义，建议补齐 parameters 以提升规划稳定性。",
                _asset_label(blueprint),
            )
        )
    return suggestions


def _top_asset(assets: list[CandidateAsset], asset_type: str) -> CandidateAsset | None:
    filtered = [asset for asset in assets if asset.asset_type == asset_type]
    if not filtered:
        return None
    return max(filtered, key=lambda asset: float(asset.confidence or 0))


def _assets_by_type(
    assets: list[CandidateAsset],
    asset_type: str,
    *,
    matched_only: bool = False,
) -> list[CandidateAsset]:
    filtered = [asset for asset in assets if asset.asset_type == asset_type]
    if matched_only:
        filtered = [
            asset for asset in filtered
            if float(asset.confidence or 0) >= BLUEPRINT_MIN_CONFIDENCE or asset.match_signals
        ]
    return sorted(filtered, key=lambda asset: float(asset.confidence or 0), reverse=True)


def _rejected_alternative_blueprints(blueprints: list[CandidateAsset]) -> list[CandidateAsset]:
    rejected: list[CandidateAsset] = []
    for asset in blueprints[1:]:
        candidate = _with_usage(asset, "rejected")
        candidate.reject_reason = "存在更匹配的蓝图候选，本蓝图仅作为备选未采用。"
        rejected.append(candidate)
    return rejected


def _blueprint_comparison_factor(blueprints: list[CandidateAsset]) -> list[dict[str, Any]]:
    if len(blueprints) <= 1:
        return []
    return [
        _factor(
            "blueprint_candidate_comparison",
            "已比较多个蓝图候选，并选择最高匹配项。",
            [
                {
                    "asset_id": asset.asset_id,
                    "name": _asset_label(asset),
                    "confidence": round(float(asset.confidence or 0), 4),
                }
                for asset in blueprints[:5]
            ],
        )
    ]


def _asset_table_name(asset: CandidateAsset) -> str:
    value = asset.metadata.get("table_name") or asset.name
    return str(value or "").strip()


def _asset_column_name(asset: CandidateAsset) -> str:
    value = asset.metadata.get("column_name") or asset.name
    return str(value or "").split(".")[-1].strip()


def _is_log_detail_query(question: str) -> bool:
    return _contains_any(question, LOG_DETAIL_PATTERNS)


def _is_aggregate_field_query(question: str) -> bool:
    return _contains_any(question, AGGREGATE_FIELD_PATTERNS)


def _routing_entry_intent(routing: Any) -> str:
    if not isinstance(routing, dict):
        return ""
    return str(routing.get("entry_intent") or "").strip()


def _routing_payload(routing: Any) -> dict[str, Any]:
    if not isinstance(routing, dict):
        return {}
    payload = routing.get("route_payload")
    return payload if isinstance(payload, dict) else {}


def _routing_multiturn_refinement(routing: Any) -> dict[str, Any]:
    """从路由载荷读取 LeadAgent 生成的抽象多轮追问槽位。"""

    refinement = _routing_payload(routing).get("multiturn_refinement")
    return refinement if isinstance(refinement, dict) else {}


def _refinement_slots(routing: Any) -> dict[str, Any]:
    slots = _routing_multiturn_refinement(routing).get("slots")
    return slots if isinstance(slots, dict) else {}


def _slot_value(slots: dict[str, Any], key: str) -> Any:
    value = slots.get(key)
    return None if value in (None, "", [], {}) else value


def _routing_is_detail_query(routing: Any) -> bool:
    payload = _routing_payload(routing)
    return (
        _routing_entry_intent(routing) == "detail_query"
        or payload.get("kind") == "detail_query"
    )


def _routing_is_filter_refinement(routing: Any) -> bool:
    payload = _routing_payload(routing)
    if payload.get("source") in {"multiturn_filter_refinement", "llm_multiturn_refinement"}:
        return True
    return _routing_multiturn_refinement(routing).get("intent") == "continue"


def _is_daily_blueprint(asset: CandidateAsset | None) -> bool:
    if asset is None:
        return False
    text = " ".join(
        str(value or "")
        for value in (
            asset.name,
            asset.display_name,
            asset.metadata.get("description"),
            asset.metadata.get("when_to_use"),
        )
    )
    return _contains_any(text, DAILY_BLUEPRINT_PATTERNS)


def _selected_main_table(field_table_assets: list[CandidateAsset]) -> str | None:
    table_names = [_asset_table_name(asset) for asset in field_table_assets]
    if "plan_task_daily_record" in table_names:
        return "plan_task_daily_record"
    table_assets = [asset for asset in field_table_assets if asset.asset_type == "table"]
    if table_assets:
        return _asset_table_name(table_assets[0]) or None
    field_assets = [asset for asset in field_table_assets if asset.asset_type == "field"]
    if field_assets:
        return _asset_table_name(field_assets[0]) or None
    return None


def _join_hints_for_assets(field_table_assets: list[CandidateAsset]) -> list[dict[str, Any]]:
    table_names = {_asset_table_name(asset) for asset in field_table_assets}
    if {"plan_task_daily_record", "eas_personofile"}.issubset(table_names):
        return [
            {
                "left_table": "plan_task_daily_record",
                "left_column": "account",
                "right_table": "eas_personofile",
                "right_column": "person_card",
                "purpose": "日志账号关联人员姓名",
            }
        ]
    return []


def _selected_detail_assets(field_table_assets: list[CandidateAsset]) -> list[CandidateAsset]:
    main_table = _selected_main_table(field_table_assets)
    join_hints = _join_hints_for_assets(field_table_assets)
    selected: list[CandidateAsset] = []
    for asset in field_table_assets:
        candidate = _with_usage(asset, "selected")
        table_name = _asset_table_name(candidate)
        metadata = dict(candidate.metadata or {})
        if table_name == main_table:
            metadata["main_table_role"] = "fact"
        elif table_name:
            metadata["dimension_table_role"] = "dimension"
        if join_hints:
            metadata["join_hints"] = join_hints
        candidate.metadata = metadata
        selected.append(candidate)
    return selected


def _query_plan_debug(field_table_assets: list[CandidateAsset]) -> dict[str, Any]:
    debug: dict[str, Any] = {}
    main_table = _selected_main_table(field_table_assets)
    if main_table:
        debug["selected_main_table"] = main_table
    join_hints = _join_hints_for_assets(field_table_assets)
    if join_hints:
        debug["join_hints"] = join_hints
    return debug


def _extract_limit(question: str, default: int = 100) -> int:
    match = re.search(r"(?:查询|查|看|前|最近)?\s*(\d+)\s*条", str(question or ""))
    if not match:
        return default
    try:
        return max(1, min(int(match.group(1)), 1000))
    except ValueError:
        return default


def _sql_string_literal(value: str) -> str:
    """生成 SQL 字符串字面量，避免用户输入里的单引号破坏模板 SQL。"""
    return "'" + str(value).strip().replace("'", "''") + "'"


def _extract_dataset10_log_filter_value(question: str, names: tuple[str, ...]) -> str | None:
    """从“字段为XX/字段是XX”这类短语中提取过滤值。"""
    name_pattern = "|".join(re.escape(name) for name in names)
    match = re.search(
        rf"(?:{name_pattern})\s*(?:为|是|=|等于|叫)\s*"
        rf"[\"“']?([^，,。；;、\s\"”'的]+)",
        str(question or ""),
    )
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _extract_dataset10_log_person_name(question: str) -> str | None:
    """从“查询杨凯 2024 年工作日志”这类自然问法中提取人员姓名。"""
    text = str(question or "")
    placeholders = {"某人", "某员工", "员工", "用户", "人员"}
    patterns = (
        r"(?:查询|查看|看下|看一下|帮我查一下)?\s*([\u4e00-\u9fff]{2,4})\s*(?:20\d{2}\s*年|今年|去年|本年|最近|本月|上月)?\s*(?:的)?\s*(?:工作日志|日志|日报)",
        r"(?:工作日志|日志|日报).*?(?:人员|员工|姓名|名字)\s*(?:为|是|=|等于|叫)\s*([\u4e00-\u9fff]{2,4})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        person_name = match.group(1).strip()
        if person_name and person_name not in placeholders:
            return person_name
    return None


def _dataset10_log_time_filters(question: str, routing: Any) -> list[str]:
    """数据集 10 日志模板的时间过滤，优先使用 LeadAgent 抽象时间槽位。"""

    time_range = _slot_value(_refinement_slots(routing), "time_range")
    if isinstance(time_range, dict):
        start_date = str(time_range.get("start_date") or "").strip()
        end_date = str(time_range.get("end_date") or "").strip()
        if start_date and end_date:
            return [
                f"p.rzrq >= {_sql_string_literal(start_date)}",
                f"p.rzrq < {_sql_string_literal(end_date)}",
            ]
    time_text = str(time_range or question or "")
    year_match = re.search(r"(20\d{2})\s*年", time_text)
    if year_match:
        year = int(year_match.group(1))
        return [
            f"p.rzrq >= {_sql_string_literal(f'{year}-01-01')}",
            f"p.rzrq < {_sql_string_literal(f'{year + 1}-01-01')}",
        ]
    return ["p.rzrq >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"]


def _dataset10_log_filters(
    question: str,
    *,
    routing: Any = None,
    enable_person_filters: bool,
) -> list[str]:
    """数据集 10 日志模板支持的确定性过滤条件。"""

    filters: list[str] = []
    slots = _refinement_slots(routing)
    account_slot = _slot_value(slots, "account")
    if account_slot:
        filters.append(f"p.account = {_sql_string_literal(str(account_slot))}")
    person_slot = _slot_value(slots, "person")
    if enable_person_filters and person_slot:
        filters.append(f"ep.person_name = {_sql_string_literal(str(person_slot))}")
    dept_slot = _slot_value(slots, "department")
    if dept_slot:
        filters.append(f"d.dept_name = {_sql_string_literal(str(dept_slot))}")
    status_slot = _slot_value(slots, "status")
    if status_slot:
        filters.append(f"p.zt = {_sql_string_literal(str(status_slot))}")

    account = _extract_dataset10_log_filter_value(
        question, ("账号", "账户", "工号", "account")
    )
    if account and not account_slot:
        filters.append(f"p.account = {_sql_string_literal(account)}")
    if enable_person_filters:
        person_name = _extract_dataset10_log_filter_value(
            question, ("姓名", "名字", "人员姓名", "用户姓名", "员工姓名")
        )
        if person_name and not person_slot:
            filters.append(f"ep.person_name = {_sql_string_literal(person_name)}")
        elif not person_slot:
            inferred_person_name = _extract_dataset10_log_person_name(question)
            if inferred_person_name:
                filters.append(f"ep.person_name = {_sql_string_literal(inferred_person_name)}")
    dept_name = _extract_dataset10_log_filter_value(question, ("部门", "部门名称"))
    if dept_name and not dept_slot:
        filters.append(f"d.dept_name = {_sql_string_literal(dept_name)}")
    return filters


def _dataset10_log_detail_sql(
    question: str,
    *,
    routing: Any = None,
    enable_person_filters: bool = False,
) -> str:
    limit = _extract_limit(question)
    filters = [
        *_dataset10_log_time_filters(question, routing),
        *_dataset10_log_filters(
            question,
            routing=routing,
            enable_person_filters=enable_person_filters,
        ),
    ]
    where_clause = " AND ".join(filters)
    return (
        "SELECT "
        "p.id, p.rzrq, p.cjsj, p.account, ep.person_name, "
        "p.deptcode, d.dept_name, p.xmid, pm.XMMC AS project_name, "
        "p.jhgznr, p.jtgznr, p.zt, p.rzbz "
        "FROM plan_task_daily_record p "
        "LEFT JOIN eas_personofile ep ON p.account = ep.person_card "
        "LEFT JOIN sys_dept d ON p.deptcode = d.dept_id "
        "LEFT JOIN project_manager pm ON p.xmid = pm.XMID "
        f"WHERE {where_clause} "
        f"ORDER BY p.rzrq DESC, p.cjsj DESC LIMIT {limit}"
    )


def _routing_dataset_id(routing: Any) -> int | None:
    if not isinstance(routing, dict):
        return None
    for key in ("dataset_id", "locked_dataset_id"):
        value = routing.get(key)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None


def _is_dataset10_log_template_query(question: str, routing: Any) -> bool:
    return _is_log_detail_query(question) or (
        _routing_is_detail_query(routing) and _routing_is_filter_refinement(routing)
    )


def _dataset10_log_template_debug(
    question: str,
    routing: Any,
    field_table_assets: list[CandidateAsset],
) -> dict[str, Any]:
    if _routing_dataset_id(routing) != 10:
        return {}
    if not _is_dataset10_log_template_query(question, routing):
        return {}
    table_names = {_asset_table_name(asset) for asset in field_table_assets}
    if "plan_task_daily_record" not in table_names:
        return {}
    enable_person_filters = "eas_personofile" in table_names
    return {
        "template_name": "dataset10_log_detail",
        "schema_token_budget": "template_bypass",
        "multiturn_refinement": _routing_multiturn_refinement(routing) or None,
        "sql_template": _dataset10_log_detail_sql(
            question,
            routing=routing,
            enable_person_filters=enable_person_filters,
        ),
    }


def _reject_blueprint_for_detail(asset: CandidateAsset) -> CandidateAsset:
    rejected = _with_usage(asset, "rejected")
    rejected.reject_reason = "日志明细查询不强套日报蓝图，避免错误主表和必填参数污染 DSL。"
    return rejected


def build_rule_based_query_plan(
    question: str,
    candidate_assets: CandidateAssetInput = None,
    *,
    routing: Any = None,
    fallback_reason: str | None = None,
) -> QueryPlan:
    """根据候选资产构造规则查询计划。

    该接口同时服务两个阶段：
    - `fallback_reason is None`：作为 LLM 调用前的确定性预判器，允许明显可执行的
      明细查询直接进入 QueryGraph。
    - `fallback_reason` 有值：作为 LLM 调用失败或响应校验失败后的规则兜底，并在
      QueryPlan 中保留失败原因与 planner warning。

    本函数不调用 LLM，只基于问题文本、路由信息和候选资产生成保守的 QueryPlan。
    """

    assets = _assets(candidate_assets)
    all_blueprints = _assets_by_type(assets, "blueprint")
    blueprints = _assets_by_type(assets, "blueprint", matched_only=True)
    blueprint = blueprints[0] if blueprints else None
    rejected_blueprints = [
        *_rejected_alternative_blueprints(blueprints),
        *[
            _with_usage(asset, "rejected")
            for asset in all_blueprints
            if asset not in blueprints
        ],
    ]
    for asset in rejected_blueprints:
        if not asset.reject_reason:
            asset.reject_reason = "蓝图候选没有有效匹配信号，不能用于执行或参考。"
    blueprint_comparison_factors = _blueprint_comparison_factor(blueprints)
    field_table_assets = [asset for asset in assets if asset.asset_type in {"field", "table"}]
    metric_dimension_assets = [asset for asset in assets if asset.asset_type in {"metric", "dimension"}]
    is_detail_query = _contains_any(question, DETAIL_PATTERNS) or _routing_is_detail_query(routing)
    is_metric_query = _contains_any(question, METRIC_PATTERNS) or _is_aggregate_field_query(question)
    is_blueprint_query = _contains_any(question, BLUEPRINT_PATTERNS)
    detail_with_field_context = is_detail_query and bool(field_table_assets)
    planner_source = "fallback" if fallback_reason else "deterministic"

    required_inputs = _required_inputs(blueprint, routing)
    common_warnings = _fallback_warnings(fallback_reason)
    common_suggestions = _quality_suggestions(
        assets=assets,
        field_table_assets=field_table_assets,
        metric_dimension_assets=metric_dimension_assets,
        blueprint=blueprint,
    )
    template_debug = _dataset10_log_template_debug(question, routing, field_table_assets)
    if is_blueprint_query and blueprint and required_inputs and not detail_with_field_context:
        return QueryPlan(  # 蓝图缺必填参数必须早退澄清，防止模板误执行。
            query_type="blueprint_query",
            execution_strategy="clarify",
            confidence=0.78,
            required_inputs=required_inputs,
            rejected_assets=rejected_blueprints,
            clarification={
                "message": "需要补充蓝图查询的必要参数后才能继续。",
                "required_inputs": required_inputs,
            },
            fallback_reason=fallback_reason or "blueprint_required_inputs_missing",
            planner_source=planner_source,
            explanation={
                "summary": "问题命中蓝图类查询，但缺少必填参数。",
                "matched_blueprint": blueprint.display_name or blueprint.name,
            },
            decision_factors=[
                _factor("blueprint_query_signal", "问题包含蓝图类查询信号。", list(BLUEPRINT_PATTERNS)),
                _factor("blueprint_matched", "候选蓝图得分最高。", _asset_label(blueprint)),
                _factor("required_inputs_missing", "蓝图必填参数尚未满足。", required_inputs),
                *blueprint_comparison_factors,
            ],
            planner_warnings=common_warnings,
            governance_suggestions=common_suggestions,
        )

    if is_blueprint_query and blueprint and not detail_with_field_context:
        return QueryPlan(  # 参数满足且非明细时才允许 blueprint_execute。
            query_type="blueprint_query",
            execution_strategy="blueprint_execute",
            confidence=0.82,
            selected_assets=[_with_usage(blueprint, "selected")],
            rejected_assets=rejected_blueprints,
            fallback_reason=fallback_reason or "blueprint_query_ready",
            planner_source="fallback" if fallback_reason else "template",
            explanation={
                "summary": "问题命中蓝图类查询，且必要参数已满足或无需参数。",
                "matched_blueprint": blueprint.display_name or blueprint.name,
            },
            decision_factors=[
                _factor("blueprint_query_signal", "问题包含蓝图类查询信号。", list(BLUEPRINT_PATTERNS)),
                _factor("blueprint_matched", "候选蓝图得分最高。", _asset_label(blueprint)),
                _factor("required_inputs_ready", "蓝图必填参数已满足或无需参数。"),
                *blueprint_comparison_factors,
            ],
            planner_warnings=common_warnings,
            governance_suggestions=common_suggestions,
        )

    if (
        is_detail_query
        and field_table_assets
        and _is_dataset10_log_template_query(question, routing)
        and _is_daily_blueprint(blueprint)
    ):
        template_source = "template" if template_debug and not fallback_reason else planner_source  # 明细问法走 QueryGraph。
        rejected_daily_blueprints = [
            _reject_blueprint_for_detail(asset)
            for asset in blueprints
            if _is_daily_blueprint(asset)
        ]
        rejected_asset_keys = {
            (asset.asset_type, str(asset.asset_id))
            for asset in [*rejected_blueprints, *rejected_daily_blueprints]
        }
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.78,
            selected_assets=_selected_detail_assets(field_table_assets),
            rejected_assets=[
                *rejected_daily_blueprints,
                *rejected_blueprints,
                *[
                    _with_usage(asset, "rejected")
                    for asset in all_blueprints
                    if (asset.asset_type, str(asset.asset_id)) not in rejected_asset_keys
                ],
            ],
            fallback_reason=fallback_reason,
            planner_source=template_source,
            explanation={
                "summary": "识别为日志明细查询，使用字段和表构建 QueryGraph。",
                "why_not_blueprint_execute": "用户问题是日志明细查询，不能强制执行日报蓝图。",
                "why_continue_without_metric": "明细查询不要求必须命中指标或维度。",
            },
            decision_factors=[
                _factor("detail_query_signal", "问题包含明细查询信号。", list(DETAIL_PATTERNS)),
                _factor(
                    "field_table_coverage",
                    "已召回字段或表，可继续构建 QueryGraph。",
                    [_asset_label(asset) for asset in field_table_assets[:8]],
                ),
                _factor("blueprint_rejected_for_detail", "日志明细查询拒绝套用日报蓝图。", _asset_label(blueprint)),
                *blueprint_comparison_factors,
            ],
            planner_warnings=[
                *common_warnings,
                _warning(
                    "blueprint_rejected_for_detail",
                    "用户问题是日志明细查询，命中日报蓝图不能作为执行或 DSL 参考上下文。",
                    _asset_label(blueprint),
                ),
            ],
            governance_suggestions=common_suggestions,
            debug={**_query_plan_debug(field_table_assets), **template_debug},
        )

    if is_detail_query and blueprint and field_table_assets:
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="blueprint_as_reference",
            confidence=0.74,
            selected_assets=_selected_detail_assets(field_table_assets),
            reference_assets=[_with_usage(blueprint, "reference")],
            rejected_assets=rejected_blueprints,
            fallback_reason=fallback_reason,
            planner_source=planner_source,
            explanation={
                "summary": "识别为明细查询，蓝图仅作为字段和表推理参考。",
                "why_not_blueprint_execute": "用户问题不是固定蓝图分析，不能强制执行蓝图。",
                "why_continue_without_metric": "明细查询不要求必须命中指标或维度。",
            },
            decision_factors=[
                _factor("detail_query_signal", "问题包含明细查询信号。", list(DETAIL_PATTERNS)),
                _factor(
                    "field_table_coverage",
                    "已召回字段或表，可继续构建 QueryGraph。",
                    [_asset_label(asset) for asset in field_table_assets[:8]],
                ),
                _factor("blueprint_reference", "蓝图可作为业务口径参考，但不适合强执行。", _asset_label(blueprint)),
                *blueprint_comparison_factors,
            ],
            planner_warnings=[
                *common_warnings,
                _warning(
                    "blueprint_reference_only",
                    "用户问题是明细查询，命中蓝图只能作为参考，不能强套蓝图 SQL。",
                    _asset_label(blueprint),
                ),
            ],
            governance_suggestions=common_suggestions,
            debug={**_query_plan_debug(field_table_assets), **template_debug},
        )

    if is_detail_query and field_table_assets:
        template_source = "template" if template_debug and not fallback_reason else planner_source
        return QueryPlan(
            query_type="detail_query",
            execution_strategy="query_graph",
            confidence=0.86 if template_debug else 0.7,
            selected_assets=_selected_detail_assets(field_table_assets),
            fallback_reason=fallback_reason,
            planner_source=template_source,
            explanation={
                "summary": "命中数据集日志明细模板。" if template_debug else "识别为明细查询，使用字段和表构建查询图。",
                "why_continue_without_metric": "明细查询不要求必须命中指标或维度。",
            },
            decision_factors=[
                _factor("detail_query_signal", "问题包含明细查询信号。", list(DETAIL_PATTERNS)),
                _factor(
                    "field_table_coverage",
                    "已召回字段或表，可继续构建 QueryGraph。",
                    [_asset_label(asset) for asset in field_table_assets[:8]],
                ),
            ],
            planner_warnings=common_warnings,
            governance_suggestions=common_suggestions,
            debug={**_query_plan_debug(field_table_assets), **template_debug},
        )

    if is_metric_query and metric_dimension_assets:
        return QueryPlan(
            query_type="metric_query",
            execution_strategy="query_graph",
            confidence=0.68,
            selected_assets=[_with_usage(asset, "selected") for asset in metric_dimension_assets],
            fallback_reason=fallback_reason or "metric_query_semantic_asset_fallback",
            planner_source=planner_source,
            explanation={"summary": "识别为指标类查询，使用指标或维度资产构建查询图。"},
            decision_factors=[
                _factor("metric_query_signal", "问题包含统计或聚合查询信号。", list(METRIC_PATTERNS)),
                _factor(
                    "semantic_asset_coverage",
                    "已召回指标或维度，可继续构建 QueryGraph。",
                    [_asset_label(asset) for asset in metric_dimension_assets[:8]],
                ),
            ],
            planner_warnings=common_warnings,
            governance_suggestions=common_suggestions,
        )

    if is_metric_query and field_table_assets:
        return QueryPlan(
            query_type="metric_query",
            execution_strategy="query_graph",
            confidence=0.62,
            selected_assets=_selected_detail_assets(field_table_assets),
            fallback_reason=fallback_reason or "aggregate_field_table_fallback",
            planner_source=planner_source,
            explanation={
                "summary": "识别为统计类查询，使用字段和表资产构建 QueryGraph。",
                "why_continue_without_metric": "字段和表资产已覆盖问题，缺少指标或维度资产时仍可尝试生成聚合查询。",
            },
            decision_factors=[
                _factor(
                    "metric_query_signal",
                    "问题包含统计、金额或聚合查询信号。",
                    [*METRIC_PATTERNS, *AGGREGATE_FIELD_PATTERNS],
                ),
                _factor(
                    "aggregate_field_table_coverage",
                    "已召回字段或表，可继续构建 QueryGraph。",
                    [_asset_label(asset) for asset in field_table_assets[:8]],
                ),
            ],
            planner_warnings=common_warnings,
            governance_suggestions=common_suggestions,
            debug=_query_plan_debug(field_table_assets),
        )

    rejected_asset_keys = {
        (asset.asset_type, str(asset.asset_id))
        for asset in rejected_blueprints
    }
    rejected_assets = [
        *rejected_blueprints,
        *[
            _with_usage(asset, "rejected")
            for asset in assets
            if (asset.asset_type, str(asset.asset_id)) not in rejected_asset_keys
        ],
    ]

    logger.info(
        "build_rule_based_query_plan 触发规则拒绝: question_preview=%s,"
        " is_detail_query=%s, is_metric_query=%s, is_blueprint_query=%s,"
        " metric_dimension_asset_count=%d, field_table_asset_count=%d,"
        " blueprint_count=%d, fallback_reason=%s, candidate_asset_count=%d",
        str(question)[:120],
        is_detail_query,
        is_metric_query,
        is_blueprint_query,
        len(metric_dimension_assets),
        len(field_table_assets),
        len(blueprints),
        fallback_reason,
        len(assets),
    )

    return QueryPlan(
        query_type="unsupported",
        execution_strategy="reject",
        confidence=0.2,
        rejected_assets=rejected_assets,
        fallback_reason=fallback_reason or "insufficient_assets_for_rule_planning",
        planner_source="fallback",
        explanation={"summary": "候选资产不足，规则兜底无法形成可执行查询计划。"},
        decision_factors=[
            _factor("insufficient_assets", "候选资产不足或查询类型无法被规则稳定识别。"),
        ],
        planner_warnings=common_warnings,
        governance_suggestions=common_suggestions
        or [
            _governance_suggestion(
                "candidate_assets",
                "建议补充业务术语、指标维度、字段描述或分析蓝图触发样例。",
            )
        ],
    )


def _planner_system_prompt(*, detail_loop_enabled: bool = False) -> str:
    rules = [
        "你是数语 DatasetSubAgent 的查询规划器，只能输出严格 JSON。",
        "不要输出 Markdown、解释文字或代码块之外的任何内容。",
        "JSON 必须符合 QueryPlan 契约：query_type、execution_strategy、confidence、planner_source、explanation。",
        "planner_source 必须为 llm。",
        "可选资产字段包括 selected_assets、reference_assets、rejected_assets、required_inputs、clarification、debug。",
        "可选审计字段包括 decision_factors、planner_warnings、governance_suggestions，均为对象数组。",
        "execution_strategy 可选：blueprint_execute、blueprint_as_reference、query_graph、clarify、reject。",
        "明细查询命中 field/table 时，应优先 query_graph 或 blueprint_as_reference，不要因为缺少指标而 clarify。",
    ]
    if detail_loop_enabled:
        rules.extend(
            [
                "当候选资产目录不足以生成可靠 SQL 时，可以输出 asset_detail_requests，请求目录中的资产详情。",
                "asset_detail_requests 只能请求本轮候选资产目录中的 metric、dimension、table、blueprint。",
                "表详情优先请求 full_schema；如果返回 too_large，再使用 field_search 自然语言搜索字段。",
                "资产详情最多 3 轮；3 轮后仍缺上下文时，不允许硬生成 SQL，必须输出 clarify 或 reject。",
                "如果无法确定时间字段、join 字段、指标口径或业务过滤条件，应在 missing_context 和 why_not_generate_sql 中说明原因。",
            ]
        )
    else:
        rules.append("普通规划模式下必须输出 QueryPlan 契约 JSON，不要输出详情请求或其他包装结构。")
    return "\n".join(rules)


def _compact_error_text(exc: Exception, max_length: int = 200) -> str:
    text = str(exc) or exc.__class__.__name__
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _truncate_text(value: str, max_length: int | None = None) -> str:
    max_length = max_length or _prompt_text_limit()
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return f"{value[: max_length - 3]}..."


def _compact_prompt_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= PROMPT_DEPTH_LIMIT:
        return _truncate_text(str(value))
    if isinstance(value, list):
        return [_compact_prompt_value(item, depth=depth + 1) for item in value[:_prompt_list_limit()]]
    if isinstance(value, dict):
        return {
            str(key): _compact_prompt_value(item, depth=depth + 1)
            for key, item in list(value.items())[:_prompt_list_limit()]
        }
    return _truncate_text(str(value))


def _planner_response_debug(response: Any) -> str:
    """生成 LLM 原始响应的安全诊断摘要，供响应内容为空或 JSON 非法时排查。"""

    content = _planner_response_content(response)
    payload: dict[str, Any] = {
        "response_type": f"{type(response).__module__}.{type(response).__name__}",
        "content_type": f"{type(content).__module__}.{type(content).__name__}",
        "response_repr": _truncate_text(repr(response), 2000),
    }
    if content not in (None, ""):
        payload["content_preview"] = _truncate_text(str(content), 2000)
    for attr in ("id", "name", "response_metadata", "usage_metadata", "additional_kwargs"):
        value = getattr(response, attr, None)
        if value not in (None, "", [], {}):
            payload[attr] = _compact_prompt_value(value)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _detail_loop_public_key_is_dangerous(key: Any) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in DETAIL_LOOP_DANGEROUS_PUBLIC_KEYS


def _detail_loop_public_text(value: str) -> str:
    normalized = value.lower()
    if any(marker in normalized for marker in DETAIL_LOOP_DANGEROUS_TEXT_MARKERS):
        return "[removed_detail_context]"
    return _truncate_text(value, _public_text_limit())


def _sanitize_public_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _detail_loop_public_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= PUBLIC_DEPTH_LIMIT:
        return _detail_loop_public_text(str(value))
    if isinstance(value, list):
        sanitized_items = []
        for item in value[:_public_list_limit()]:
            sanitized = _sanitize_public_value(item, depth=depth + 1)
            if sanitized not in (None, "", [], {}):
                sanitized_items.append(sanitized)
        return sanitized_items
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, item in list(value.items())[:PUBLIC_DICT_LIMIT]:
            if _detail_loop_public_key_is_dangerous(key):
                continue
            sanitized = _sanitize_public_value(item, depth=depth + 1)
            if sanitized not in (None, "", [], {}):
                sanitized_dict[str(key)] = sanitized
        return sanitized_dict
    return _detail_loop_public_text(str(value))


def _sanitize_public_dict(value: Any) -> dict[str, Any]:
    sanitized = _sanitize_public_value(value)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_public_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sanitized_items = []
    for item in value[:_public_list_limit()]:
        sanitized = _sanitize_public_value(item)
        if isinstance(sanitized, dict) and sanitized:
            sanitized_items.append(sanitized)
    return sanitized_items


def _sanitize_public_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    sanitized_items = []
    for item in value[:_public_list_limit()]:
        sanitized = _sanitize_public_value(item)
        if sanitized not in (None, "", [], {}):
            sanitized_items.append(str(sanitized))
    return sanitized_items


def _lightweight_asset_index(lightweight_catalog: CandidateAssetInput) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _asset_items(lightweight_catalog):
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type") or "")
        asset_id = item.get("asset_id")
        if not asset_type or asset_id in (None, ""):
            continue
        index[(asset_type, str(asset_id))] = item
    return index


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rebuild_detail_loop_asset(
    asset: CandidateAsset,
    *,
    usage: str,
    lightweight_assets: dict[tuple[str, str], dict[str, Any]],
) -> CandidateAsset:
    lightweight = lightweight_assets.get((asset.asset_type, str(asset.asset_id))) or {}
    metadata = {
        key: _sanitize_public_value(lightweight[key])
        for key in ("schema_version", "manifest_version")
        if lightweight.get(key) not in (None, "", [], {})
    }
    match_signals = _sanitize_public_value(lightweight.get("match_signals") or [])
    return CandidateAsset(
        asset_type=str(lightweight.get("asset_type") or asset.asset_type),
        asset_id=lightweight.get("asset_id", asset.asset_id),
        name=str(lightweight.get("name") or asset.name or lightweight.get("asset_id") or asset.asset_id),
        display_name=_sanitize_public_value(lightweight.get("display_name") or asset.display_name),
        source=str(lightweight.get("source") or "recall"),
        confidence=_safe_float(lightweight.get("confidence"), asset.confidence),
        match_signals=match_signals if isinstance(match_signals, list) else [],
        metadata=metadata,
        usage=usage,
        match_reason=_sanitize_public_value(asset.match_reason),
        reject_reason=_sanitize_public_value(asset.reject_reason),
    )


def _rebuild_detail_loop_assets(
    assets: list[CandidateAsset],
    *,
    usage: str,
    lightweight_assets: dict[tuple[str, str], dict[str, Any]],
) -> list[CandidateAsset]:
    rebuilt = []
    for asset in assets[:_public_list_limit()]:
        rebuilt.append(
            _rebuild_detail_loop_asset(
                asset,
                usage=usage,
                lightweight_assets=lightweight_assets,
            )
        )
    return rebuilt


def _sanitize_detail_loop_query_plan(
    plan: QueryPlan,
    *,
    lightweight_catalog: CandidateAssetInput,
) -> QueryPlan:
    lightweight_assets = _lightweight_asset_index(lightweight_catalog)
    plan.selected_assets = _rebuild_detail_loop_assets(
        plan.selected_assets,
        usage="selected",
        lightweight_assets=lightweight_assets,
    )
    plan.reference_assets = _rebuild_detail_loop_assets(
        plan.reference_assets,
        usage="reference",
        lightweight_assets=lightweight_assets,
    )
    plan.rejected_assets = _rebuild_detail_loop_assets(
        plan.rejected_assets,
        usage="rejected",
        lightweight_assets=lightweight_assets,
    )
    plan.explanation = _sanitize_public_dict(plan.explanation)
    plan.decision_factors = _sanitize_public_dict_list(plan.decision_factors)
    plan.planner_warnings = _sanitize_public_dict_list(plan.planner_warnings)
    plan.governance_suggestions = _sanitize_public_dict_list(plan.governance_suggestions)
    plan.required_inputs = _sanitize_public_dict_list(plan.required_inputs)
    plan.debug = _sanitize_public_dict(plan.debug)
    plan.asset_detail_coverage = _sanitize_public_dict(plan.asset_detail_coverage)
    plan.attempted_detail_requests = _sanitize_public_dict_list(plan.attempted_detail_requests)
    plan.clarification = (
        _sanitize_public_dict(plan.clarification) if isinstance(plan.clarification, dict) else None
    )
    plan.missing_context = _sanitize_public_string_list(plan.missing_context)
    plan.risk_flags = _sanitize_public_string_list(plan.risk_flags)
    if plan.why_not_generate_sql is not None:
        plan.why_not_generate_sql = str(_sanitize_public_value(plan.why_not_generate_sql))
    if plan.fallback_reason is not None:
        plan.fallback_reason = str(_sanitize_public_value(plan.fallback_reason))
    return plan


def _pick_keys(payload: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        key: _compact_prompt_value(payload[key])
        for key in keys
        if key in payload and payload[key] not in (None, "", [], {})
    }


def _manifest_summary(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return _pick_keys(
        value,
        (
            "manifest_id",
            "id",
            "name",
            "display_name",
            "dataset_id",
            "version",
            "status",
        ),
    )


def _routing_summary(routing: Any) -> dict[str, Any]:
    summary = _pick_keys(
        routing,
        (
            "entry_route",
            "entry_intent",
            "dataset_id",
            "manifest_id",
            "matched_manifest_id",
        ),
    )
    if isinstance(routing, dict):
        for source_key in ("matched_manifest", "manifest"):
            if source_key in routing:
                manifest = _manifest_summary(routing[source_key])
                if manifest not in (None, "", [], {}):
                    summary["matched_manifest"] = manifest
                break
        if "route" in routing and "entry_route" not in summary:
            summary["entry_route"] = routing["route"]
        if "intent" in routing and "entry_intent" not in summary:
            summary["entry_intent"] = routing["intent"]
        route_payload = _routing_payload(routing)
        if route_payload:
            summary["route_payload"] = _pick_keys(
                route_payload,
                ("kind", "source", "missing", "multiturn_refinement"),
            )
    return summary


def _multiturn_summary(multiturn_context: Any) -> dict[str, Any]:
    return _pick_keys(
        multiturn_context,
        (
            "question_context",
            "resolved_references",
            "active_filters",
            "previous_query_summary",
        ),
    )


def _lead_agent_context_summary(lead_agent_context: Any) -> dict[str, Any]:
    return _pick_keys(
        lead_agent_context,
        (
            "time_context",
            "schema_status",
            "dataset_selection",
            "permission_scope",
        ),
    )


def _lightweight_match_signal(signal: Any) -> dict[str, Any] | None:
    if not isinstance(signal, dict):
        return None
    compact = _pick_keys(signal, tuple(LIGHTWEIGHT_SIGNAL_KEYS))
    return compact or None


def _lightweight_asset(asset: CandidateAsset) -> dict[str, Any]:
    payload = asset.to_dict()
    compact = _pick_keys(payload, tuple(LIGHTWEIGHT_ASSET_KEYS))
    signals = [
        signal
        for signal in (_lightweight_match_signal(item) for item in payload.get("match_signals") or [])
        if signal
    ]
    if signals:
        compact["match_signals"] = signals[:5]
    metadata = {
        key: _compact_prompt_value(value)
        for key, value in (payload.get("metadata") or {}).items()
        if key in LIGHTWEIGHT_METADATA_KEYS and value not in (None, "", [], {})
    }
    if metadata:
        compact["metadata"] = metadata
    return compact


def _planner_human_prompt(
    *,
    question: str,
    routing: Any,
    candidate_assets: CandidateAssetInput,
    multiturn_context: Any = None,
    lead_agent_context: Any = None,
    asset_details: list[dict[str, Any]] | None = None,
    previous_detail_requests: list[dict[str, Any]] | None = None,
    detail_warnings: list[dict[str, Any]] | None = None,
) -> str:
    assets = [_lightweight_asset(asset) for asset in _assets(candidate_assets)]
    asset_counts: dict[str, int] = {}
    for asset in assets:
        asset_type = str(asset.get("asset_type") or "unknown")
        asset_counts[asset_type] = asset_counts.get(asset_type, 0) + 1

    detail_loop_enabled = (
        asset_details is not None
        or previous_detail_requests is not None
        or detail_warnings is not None
    )
    rules = [
        "blueprint_execute 只能用于固定蓝图查询，且不能携带 required_inputs。",
        "blueprint_as_reference 必须提供 reference_assets。",
        "reject 必须提供 explanation.summary。",
        "detail_query 如果候选中已有 field/table，不应返回 clarify。",
    ]
    if detail_loop_enabled:
        rules.extend(
            [
                "详情循环模式下，如果轻量目录不足以规划 SQL，可输出 asset_detail_requests 数组请求资产详情。",
                "asset_detail_requests 只能请求 candidate_assets 目录中的资产，purpose 必须为 sql_generation。",
                "资产详情循环最多 3 轮；达到 3 轮仍缺少时间、join、口径或过滤条件时，不允许硬生成 SQL。",
                "无法安全生成 SQL 时，返回 QueryPlan，并在 missing_context 和 why_not_generate_sql 中说明缺口。",
            ]
        )

    payload = {
        "question": question,
        "routing": _routing_summary(routing),
        "candidate_summary": {
            "total": len(assets),
            "counts_by_type": asset_counts,
        },
        "candidate_assets": assets[:_prompt_asset_limit()],
        "multiturn_context": _multiturn_summary(multiturn_context),
        "lead_agent_context_summary": _lead_agent_context_summary(lead_agent_context),
        "rules": rules,
    }
    if detail_loop_enabled:
        payload["asset_detail_context"] = _compact_prompt_value(asset_details or [])
        payload["previous_detail_requests"] = _compact_prompt_value(previous_detail_requests or [])
        payload["detail_loop_warnings"] = _compact_prompt_value(detail_warnings or [])
    return json.dumps(payload, ensure_ascii=False, default=str)


def _safe_json_parse(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise QueryPlanValidationError("planner output must be a JSON object")
    return parsed


def parse_asset_detail_requests(payload: Any) -> list[AssetDetailRequest]:
    if not isinstance(payload, dict):
        return []
    requests = payload.get("asset_detail_requests") or []
    if not isinstance(requests, list):
        return []
    parsed: list[AssetDetailRequest] = []
    for item in requests:
        if isinstance(item, dict):
            parsed.append(AssetDetailRequest.from_dict(item))
    return parsed


def _required_input_value_present(item: dict[str, Any]) -> bool:
    """判断 required_inputs 是否已携带可执行值；只缺值时才让蓝图执行转澄清。"""
    if not isinstance(item, dict):
        return False
    if item.get("required") is False:
        return True
    for field in ("value", "input_value", "selected_value", "default", "default_value"):
        value = item.get(field)
        if value not in (None, "", [], {}):
            return True
    return False


def _validate_hard_rules(
    plan: QueryPlan,
    *,
    question: str,
    candidate_assets: CandidateAssetInput,
) -> None:
    del question
    if plan.execution_strategy == "blueprint_execute" and any(
        not _required_input_value_present(item) for item in plan.required_inputs
    ):
        raise QueryPlanValidationError("blueprint_execute cannot include missing required_inputs")
    if plan.execution_strategy == "blueprint_as_reference" and not plan.reference_assets:
        raise QueryPlanValidationError("blueprint_as_reference requires reference_assets")
    if plan.execution_strategy == "reject" and not str(plan.explanation.get("summary") or "").strip():
        raise QueryPlanValidationError("reject requires explanation.summary")

    has_field_or_table = any(asset.asset_type in {"field", "table"} for asset in _assets(candidate_assets))
    if plan.query_type == "detail_query" and plan.execution_strategy == "clarify" and has_field_or_table:
        raise QueryPlanValidationError("detail_query cannot clarify when field/table candidates exist")

    # 记录通过校验的关键信息，方便排查
    logger.debug(
        "subagent_query_planner hard rules passed: query_type=%s, execution_strategy=%s, "
        "has_field_or_table=%s, candidate_asset_count=%d",
        plan.query_type,
        plan.execution_strategy,
        has_field_or_table,
        len(_assets(candidate_assets)),
    )


def _is_llm_call_error(exc: BaseException) -> bool:
    if isinstance(exc, (RuntimeError, TimeoutError, ConnectionError)):
        return True

    for cls in type(exc).mro():
        module = str(getattr(cls, "__module__", "") or "")
        name = str(getattr(cls, "__name__", "") or "")
        if module.startswith(LLM_ERROR_MODULE_PREFIXES) and any(
            keyword in name for keyword in LLM_ERROR_TYPE_KEYWORDS
        ):
            return True
    return False


def _planner_response_content(response: Any) -> Any:
    return getattr(response, "content", response)


def _with_validation_error(plan: QueryPlan, validation_error: str | None) -> QueryPlan:
    if validation_error:
        plan.debug = {**(plan.debug or {}), "validation_error": validation_error}
    return plan


def plan_query(
    *,
    db: Any,
    question: str,
    routing: Any,
    candidate_assets: CandidateAssetInput,
    multiturn_context: Any = None,
    lead_agent_context: Any = None,
) -> QueryPlan:
    """生成 DatasetSubAgent 查询计划。

    执行顺序：
    1. 先调用 `build_rule_based_query_plan` 做确定性预判；低风险明细查询可直接返回。
    2. 预判不能短路时调用 LLM Planner，并校验 QueryPlan 契约和硬规则。
    3. LLM 不可用、返回空内容或响应不合法时，再调用同一规则规划器生成兜底计划。
    """

    deterministic_plan = build_rule_based_query_plan(
        question=question,
        routing=routing,
        candidate_assets=candidate_assets,
    )
    if (
        deterministic_plan.planner_source in {"deterministic", "template"}
        and deterministic_plan.query_type == "detail_query"
        and deterministic_plan.execution_strategy == "query_graph"
    ):
        # 可信规则模板已带受控 SQL 旁路信息，继续交给 LLM 会把计划扩散成宽字段 QueryGraph。
        return deterministic_plan

    messages = [
        SystemMessage(content=_planner_system_prompt()),
        HumanMessage(
            content=_planner_human_prompt(
                question=question,
                routing=routing,
                candidate_assets=candidate_assets,
                multiturn_context=multiturn_context,
                lead_agent_context=lead_agent_context,
            )
        ),
    ]
    try:
        llm = get_llm(temperature=0.0, role="lead_agent", db=db)
    except Exception as exc:
        if not _is_llm_call_error(exc):
            raise
        validation_error = _compact_error_text(exc)
        return _with_validation_error(
            build_rule_based_query_plan(
                question=question,
                routing=routing,
                candidate_assets=candidate_assets,
                fallback_reason=validation_error,
            ),
            validation_error,
        )

    try:
        response = llm.invoke(messages)
    except Exception as exc:
        if not _is_llm_call_error(exc):
            raise
        validation_error = _compact_error_text(exc)
        logger.warning(
            "subagent_query_planner LLM 调用失败，回退到规则兜底 plan。"
            " validation_error=%s",
            validation_error,
        )
        plan = _with_validation_error(
            build_rule_based_query_plan(
                question=question,
                routing=routing,
                candidate_assets=candidate_assets,
                fallback_reason=validation_error,
            ),
            validation_error,
        )
        logger.info(
            "subagent_query_planner LLM 调用失败 fallback plan: execution_strategy=%s, "
            "explanation_summary=%s, fallback_reason=%s",
            plan.execution_strategy,
            (plan.explanation or {}).get("summary"),
            plan.fallback_reason,
        )
        return plan

    response_content = _planner_response_content(response)
    logger.debug(
        "subagent_query_planner LLM 原始响应: raw_response_debug=%s",
        _planner_response_debug(response),
    )
    try:
        payload = _safe_json_parse(response_content)
        plan = normalize_query_plan(payload)
        _validate_hard_rules(plan, question=question, candidate_assets=candidate_assets)
        logger.info(
            "subagent_query_planner LLM 规划成功: query_type=%s, execution_strategy=%s, "
            "confidence=%.2f, selected_asset_count=%d",
            plan.query_type,
            plan.execution_strategy,
            plan.confidence,
            len(plan.selected_assets),
        )
        return plan
    except (JSONDecodeError, QueryPlanValidationError, ValueError, TypeError) as exc:
        validation_error = _compact_error_text(exc)
        # 详细日志：记录 LLM 返回但校验失败的完整响应，便于排查回退原因
        logger.warning(
            "subagent_query_planner LLM 响应校验失败，回退到规则兜底 plan。"
            " validation_error=%s, raw_response_length=%d, raw_response_preview=%s,"
            " raw_response_debug=%s",
            validation_error,
            len(str(response_content)),
            str(response_content)[:2000],
            _planner_response_debug(response),
        )
        plan = _with_validation_error(
            build_rule_based_query_plan(
                question=question,
                routing=routing,
                candidate_assets=candidate_assets,
                fallback_reason=validation_error,
            ),
            validation_error,
        )
        logger.info(
            "subagent_query_planner fallback plan: execution_strategy=%s, planner_source=%s, "
            "explanation_summary=%s, fallback_reason=%s",
            plan.execution_strategy,
            plan.planner_source,
            (plan.explanation or {}).get("summary"),
            plan.fallback_reason,
        )
        return plan


def plan_query_with_detail_context(
    *,
    db: Any,
    question: str,
    routing: Any,
    lightweight_catalog: dict[str, Any],
    asset_details: list[dict[str, Any]],
    previous_detail_requests: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    multiturn_context: Any = None,
    lead_agent_context: Any = None,
) -> QueryPlan | dict[str, Any]:
    """在资产详情补合循环中生成查询计划或下一轮详情请求。

    与 `plan_query` 不同，本接口的 LLM 允许先返回 `asset_detail_requests`，请求补充
    表结构或资产详情；当 LLM 调用失败或最终计划不合法时，仍回到规则规划器生成保守计划。
    """

    messages = [
        SystemMessage(content=_planner_system_prompt(detail_loop_enabled=True)),
        HumanMessage(
            content=_planner_human_prompt(
                question=question,
                routing=routing,
                candidate_assets=lightweight_catalog,
                multiturn_context=multiturn_context,
                lead_agent_context=lead_agent_context,
                asset_details=asset_details,
                previous_detail_requests=previous_detail_requests,
                detail_warnings=warnings,
            )
        ),
    ]
    try:
        llm = get_llm(temperature=0.0, role="lead_agent", db=db)
    except Exception as exc:
        if not _is_llm_call_error(exc):
            raise
        validation_error = _compact_error_text(exc)
        return _with_validation_error(
            build_rule_based_query_plan(
                question=question,
                routing=routing,
                candidate_assets=lightweight_catalog,
                fallback_reason=validation_error,
            ),
            validation_error,
        )

    try:
        response = llm.invoke(messages)
    except Exception as exc:
        if not _is_llm_call_error(exc):
            raise
        validation_error = _compact_error_text(exc)
        plan = _with_validation_error(
            build_rule_based_query_plan(
                question=question,
                routing=routing,
                candidate_assets=lightweight_catalog,
                fallback_reason=validation_error,
            ),
            validation_error,
        )
        return plan

    response_content = _planner_response_content(response)
    logger.debug(
        "subagent_query_planner (detail loop) LLM 原始响应: raw_response_debug=%s",
        _planner_response_debug(response),
    )
    try:
        payload = _safe_json_parse(response_content)
        if parse_asset_detail_requests(payload):
            return payload

        plan = normalize_query_plan(payload)
        _validate_hard_rules(plan, question=question, candidate_assets=lightweight_catalog)
        plan = _sanitize_detail_loop_query_plan(
            plan,
            lightweight_catalog=lightweight_catalog,
        )
        logger.info(
            "subagent_query_planner (detail loop) LLM 规划成功: query_type=%s, execution_strategy=%s, "
            "confidence=%.2f, selected_asset_count=%d",
            plan.query_type,
            plan.execution_strategy,
            plan.confidence,
            len(plan.selected_assets),
        )
        return plan
    except (JSONDecodeError, QueryPlanValidationError, ValueError, TypeError) as exc:
        validation_error = _compact_error_text(exc)
        logger.warning(
            "subagent_query_planner (detail loop) LLM 响应校验失败，回退到规则兜底 plan。"
            " validation_error=%s, raw_response_length=%d, raw_response_preview=%s,"
            " raw_response_debug=%s",
            validation_error,
            len(str(response_content)),
            str(response_content)[:2000],
            _planner_response_debug(response),
        )
        plan = _with_validation_error(
            build_rule_based_query_plan(
                question=question,
                routing=routing,
                candidate_assets=lightweight_catalog,
                fallback_reason=validation_error,
            ),
            validation_error,
        )
        logger.info(
            "subagent_query_planner (detail loop) fallback plan: execution_strategy=%s, "
            "explanation_summary=%s, fallback_reason=%s",
            plan.execution_strategy,
            (plan.explanation or {}).get("summary"),
            plan.fallback_reason,
        )
        return plan
