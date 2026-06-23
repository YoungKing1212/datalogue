# ============================================================
# File Name   : nodes.py
# Description:
#   NL2DSL2SQL 流程的 LangGraph 节点实现。
#
# Responsibilities:
#   - 执行意图识别、Schema 召回、DSL/SQL 生成和查询执行。
#   - 审核 SQL 失败原因并生成面向用户的回答。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# LangGraph 工作流节点实现 — NL2DSL2SQL 核心链路

import copy
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

import logging
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from app.core.config import get_settings
from app.graph.llm import get_llm
from app.graph.state import AgentState
from app.schemas.dsl import get_dsl_asset_id, get_dsl_item_name, normalize_dsl
from app.prompts.intent_router import INTENT_RECOGNITION_SYSTEM
from app.prompts.dsl_generate import (
    build_real_schema_system,
    build_inferred_system,
    build_semantic_system,
    build_no_schema_system,
)
from app.prompts.sql_audit import SQL_AUDIT_SYSTEM
from app.prompts.report_generate import build_report_system
from app.services.observability.prompts import get_prompt_manager
from app.services.observability.tracer import get_observability_tracer
from app.models.dataset import (
    AnalysisBlueprint,
    BusinessTerm,
    SemanticDataset,
)
from app.models.conversation import PendingClarification, SQLDiagnosisLog
from app.models.datasource import Datasource
from app.services.analysis_blueprint import blueprint_params_from_time_context, execute_analysis_blueprint
from app.services.dataset_context import build_dataset_query_context
from app.services.datasource import create_engine_for_datasource
from app.services.report_generation import generate_sql_result_report
from app.utils.query_constraints import (
    normalize_query_constraints,
    render_query_constraints_instruction,
)
from app.utils.think import strip_think_blocks

logger = logging.getLogger(__name__)

DEFAULT_MAX_SQL_RETRY_COUNT = 3
REPORT_RESULT_MAX_ROWS = 30
REPORT_CELL_MAX_CHARS = 120
DSL_FIELD_CATALOG_LIMIT = 20


def _settings_int(name: str, default: int) -> int:
    try:
        value = int(getattr(get_settings(), name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _sql_max_retry_count() -> int:
    return _settings_int("SQL_MAX_RETRY_COUNT", DEFAULT_MAX_SQL_RETRY_COUNT)


def _report_result_max_rows() -> int:
    return _settings_int("REPORT_RESULT_MAX_ROWS", REPORT_RESULT_MAX_ROWS)


def _report_cell_max_chars() -> int:
    return _settings_int("REPORT_CELL_MAX_CHARS", REPORT_CELL_MAX_CHARS)


def _dsl_field_catalog_limit() -> int:
    return _settings_int("DSL_FIELD_CATALOG_LIMIT", DSL_FIELD_CATALOG_LIMIT)


def _strip_think_blocks(text: str) -> str:
    """移除模型泄露的思考标签，避免最终回答和 trace 被推理草稿污染。"""

    return strip_think_blocks(text)


def _llm_thinking_enabled(llm) -> bool:
    """读取模型配置中的 Think 开关，未知客户端默认保留原始输出。"""

    return bool(getattr(llm, "datalogue_thinking_enabled", True))


def _clean_llm_content_if_needed(llm, content: Any) -> Any:
    """Think 关闭时清理模型泄露的思考标签。"""

    if _llm_thinking_enabled(llm) or not isinstance(content, str):
        return content
    return _strip_think_blocks(content)


def _clean_llm_response_if_needed(llm, response):
    """返回清理后的 LLM 响应，并尽量保留 usage/metadata。"""

    content = getattr(response, "content", response)
    cleaned = _clean_llm_content_if_needed(llm, content)
    if cleaned == content:
        return response
    return AIMessage(
        content=cleaned,
        additional_kwargs=getattr(response, "additional_kwargs", {}) or {},
        response_metadata=getattr(response, "response_metadata", {}) or {},
        usage_metadata=getattr(response, "usage_metadata", None),
        id=getattr(response, "id", None),
        name=getattr(response, "name", None),
    )


def _compact_report_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """压缩报告生成输入，控制 LLM 上下文体量。"""

    compact_rows = []
    cell_max_chars = _report_cell_max_chars()
    for row in rows[:_report_result_max_rows()]:
        compact_row: dict[str, Any] = {}
        for key, value in row.items():
            text = str(value)
            if len(text) > cell_max_chars:
                text = text[:cell_max_chars] + "..."
            compact_row[key] = text
        compact_rows.append(compact_row)
    return compact_rows, max(0, len(rows) - len(compact_rows))


def _llm_perf_metadata(
    *,
    started_at: float,
    ended_at: float,
    first_token_at: float | None = None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成 LLM 性能观测指标，供 Langfuse metadata 展示。"""

    latency_ms = max(0, int((ended_at - started_at) * 1000))
    output_tokens = int((usage or {}).get("completion_tokens") or (usage or {}).get("output_tokens") or 0)
    metadata: dict[str, Any] = {"latency_ms": latency_ms}
    if first_token_at is not None:
        ttft_ms = max(0, int((first_token_at - started_at) * 1000))
        decode_seconds = max(ended_at - first_token_at, 0.001)
        metadata["ttft_ms"] = ttft_ms
        metadata["tps"] = round(output_tokens / decode_seconds, 2) if output_tokens else 0
    else:
        total_seconds = max(ended_at - started_at, 0.001)
        metadata["ttft_ms"] = None
        metadata["tps"] = round(output_tokens / total_seconds, 2) if output_tokens else 0
        metadata["ttft_source"] = "unavailable_non_streaming"
    return metadata


def _invoke_llm_with_metrics(llm, messages: list):
    """优先用流式聚合调用 LLM，以便获取真实首 token 时间。"""

    stream = getattr(llm, "stream", None)
    if getattr(llm, "streaming", False) is True and callable(stream):
        content_parts: list[str] = []
        usage = None
        response_metadata: dict[str, Any] = {}
        first_token_at = None
        first_token_wall = None
        for chunk in stream(messages):
            content = getattr(chunk, "content", "") or ""
            if content and first_token_at is None:
                first_token_at = time.perf_counter()
                first_token_wall = datetime.now(timezone.utc)
            content_parts.append(content)
            chunk_usage = getattr(chunk, "usage_metadata", None)
            if chunk_usage:
                usage = chunk_usage
            chunk_metadata = getattr(chunk, "response_metadata", None)
            if isinstance(chunk_metadata, dict):
                response_metadata.update(chunk_metadata)
        response = AIMessage(
            content=_clean_llm_content_if_needed(llm, "".join(content_parts)),
            response_metadata=response_metadata,
            usage_metadata=usage,
        )
        return response, first_token_at, first_token_wall
    return _clean_llm_response_if_needed(llm, llm.invoke(messages)), None, None

# 通用工具（json 解析 / token 计量 / prompt 构建 / 跨方言 SQL）拆到 app.utils
from app.utils import (
    safe_json_parse as _safe_json_parse,
    extract_token_usage as _extract_token_usage,
    merge_token_usage as _merge_token_usage,
    resolve_dialect as _resolve_dialect,
    quote_ident as _quote_ident,
    sanitize_filter_sql as _sanitize_filter_sql,
    build_column_labels as _build_column_labels,
    fetch_sample_rows as _fetch_sample_rows,
    guard_readonly_sql as _guard_readonly_sql,
    classify_sql_execution_error as _classify_sql_execution_error,
    merge_llm_sql_diagnosis as _merge_llm_sql_diagnosis,
)

def _safe_llm_invoke(llm, messages: list, path: str = ""):
    """统一封装 llm.invoke，捕获 API 级错误并转为结构化异常信息。
    返回 (response, error_str)，正常时 error_str 为 None。
    """
    tracer = get_observability_tracer()
    generation = tracer.start_generation(
        name=f"llm.{path or 'invoke'}",
        model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
        messages=messages,
        metadata={"path": path, "thinking_enabled": _llm_thinking_enabled(llm)},
    )
    started_at = time.perf_counter()
    try:
        response, first_token_at, first_token_wall = _invoke_llm_with_metrics(llm, messages)
        ended_at = time.perf_counter()
        usage = _extract_token_usage(response, messages)
        tracer.end_generation(
            generation,
            output=getattr(response, "content", response),
            usage=usage,
            completion_start_time=first_token_wall,
            metadata={
                "path": path,
                "thinking_enabled": _llm_thinking_enabled(llm),
                **_llm_perf_metadata(
                    started_at=started_at,
                    ended_at=ended_at,
                    first_token_at=first_token_at,
                    usage=usage,
                ),
            },
        )
        return response, None
    except Exception as e:
        ended_at = time.perf_counter()
        err_str = str(e)
        tracer.end_generation(
            generation,
            output=f"LLM 调用失败: {err_str[:300]}",
            usage=None,
            metadata={
                "path": path,
                "thinking_enabled": _llm_thinking_enabled(llm),
                "status": "error",
                "error": err_str[:1000],
                **_llm_perf_metadata(started_at=started_at, ended_at=ended_at),
            },
        )
        logger.error(f"LLM 调用失败 path={path}: {err_str[:300]}")
        # 敏感内容过滤（422 / new_sensitive）：不可重试
        if "new_sensitive" in err_str or "422" in err_str:
            return None, f"LLM 拒绝处理该请求（内容敏感过滤），请换一种提问方式。[{err_str[:120]}]"
        # 限速 / 超配额（429）：可提示重试
        if "429" in err_str or "rate_limit" in err_str.lower():
            return None, f"LLM 请求频率超限，请稍后重试。[{err_str[:120]}]"
        # 其他 API 错误
        return None, f"LLM 调用异常：{err_str[:200]}"


def _sql_retry_trace(state: AgentState) -> list[dict[str, Any]]:
    """读取 SQL 自动修复重试记录，复制后再写回，避免原地修改状态。"""
    trace = state.get("sql_retry_trace") or []
    return [dict(item) for item in trace if isinstance(item, dict)]


def _start_sql_retry_trace(
    state: AgentState,
    diagnosis: dict[str, Any],
    *,
    original_error: str,
) -> list[dict[str, Any]]:
    """诊断可修复时登记一次待执行的 SQL 自动修复重试。"""
    trace = _sql_retry_trace(state)
    retry_count = state.get("retry_count", 0)
    max_retry = state.get("max_retry_count", _sql_max_retry_count())
    attempt = retry_count + 1
    trace.append(
        {
            "attempt": attempt,
            "max_attempts": max_retry,
            "original_sql": state.get("sql"),
            "repair_reason": diagnosis.get("suggested_action")
            or diagnosis.get("suggested_fix")
            or diagnosis.get("detail")
            or diagnosis.get("title"),
            "diagnosis_code": diagnosis.get("code"),
            "diagnosis_title": diagnosis.get("title"),
            "diagnosis_detail": diagnosis.get("detail") or diagnosis.get("root_cause"),
            "original_error": original_error,
            "status": "pending",
            "result": "等待自动修复重试",
        }
    )
    return trace


def _finish_latest_sql_retry_trace(
    state: AgentState,
    *,
    status: str,
    result: str,
    repaired_sql: str | None = None,
    error: str | None = None,
    row_count: int | None = None,
) -> list[dict[str, Any]] | None:
    """回填最近一次 SQL 自动修复重试结果。"""
    trace = _sql_retry_trace(state)
    if not trace:
        return None
    idx = None
    for i in range(len(trace) - 1, -1, -1):
        if trace[i].get("status") == "pending":
            idx = i
            break
    if idx is None:
        idx = len(trace) - 1
    item = dict(trace[idx])
    item.update(
        {
            "status": status,
            "result": result,
            "repaired_sql": repaired_sql if repaired_sql is not None else state.get("sql"),
        }
    )
    if error:
        item["error"] = error
    if row_count is not None:
        item["row_count"] = row_count
    trace[idx] = item
    return trace


def _attach_sql_retry_failure(
    state: AgentState,
    output: dict[str, Any],
    *,
    result: str,
    error: str | None = None,
) -> dict[str, Any]:
    """节点提前失败时，把失败原因写回最近一次自动修复记录。"""
    retry_trace = _finish_latest_sql_retry_trace(
        state,
        status="failed",
        result=result,
        error=error or output.get("error"),
    )
    if retry_trace is not None:
        output["sql_retry_trace"] = retry_trace
    return output


# ── 节点 1: 意图识别 ──────────────────────────────────

_PERMISSION_PATTERNS = (
    "权限不足",
    "没有权限",
    "无权限",
    "无权",
    "不能访问",
    "无法访问",
    "未授权",
    "forbidden",
    "permission denied",
)
_DETAIL_PATTERNS = (
    "明细",
    "列表",
    "记录",
    "清单",
    "详情",
    "逐条",
    "每一条",
    "有哪些",
    "所有",
)
_METRIC_PATTERNS = (
    "多少",
    "统计",
    "汇总",
    "合计",
    "总数",
    "趋势",
    "同比",
    "环比",
    "排名",
    "top",
    "平均",
    "占比",
    "gmv",
    "订单数",
    "销售额",
    "收入",
    "利润",
    "成本",
)
_BLUEPRINT_PATTERNS = (
    "分析",
    "归因",
    "诊断",
    "日报",
    "周报",
    "月报",
    "报表",
    "报告",
    "拆解",
    "复盘",
)
_KNOWLEDGE_PATTERNS = (
    "是什么",
    "什么意思",
    "定义",
    "解释",
    "口径",
    "怎么算",
    "如何计算",
    "规则",
    "知识库",
)
_AMBIGUOUS_PATTERNS = (
    "这个",
    "那个",
    "它",
    "上面",
    "刚才",
    "继续",
    "看一下",
    "查一下",
)
def _normalized_text(text: str) -> str:
    """归一化问题文本，便于做确定性入口路由匹配。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _as_dict(value: Any) -> dict[str, Any]:
    """把未知状态片段安全收敛为 dict，避免多轮胶囊污染主状态。"""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """把未知状态片段安全收敛为 list。"""
    return value if isinstance(value, list) else []


def _dedupe_jsonable(items: list[Any]) -> list[Any]:
    """对 JSON 友好对象做稳定去重，保留首次出现顺序。"""
    output: list[Any] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(jsonable_encoder(item), ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _format_query_context_for_prompt(multiturn_context: dict[str, Any] | None) -> str:
    """把多轮合并上下文压缩成 DSL 生成可消费的提示词片段。

    Phase 1 保留在 nodes.py：DSL 生成节点（nodes.py:2322）继续调用本函数，
    builder 不承担 prompt 格式化（builder 只产 MergeDecision 纯决策）。
    """
    if not multiturn_context or multiturn_context.get("turn_type") != "continue":
        return ""
    payload = {
        "prior_query_context": multiturn_context.get("prior_query_context") or {},
        "delta": multiturn_context.get("delta") or {},
        "merged_query_context": multiturn_context.get("merged_query_context") or {},
    }
    return json.dumps(jsonable_encoder(payload), ensure_ascii=False)[:3000]


def _format_query_plan_for_prompt(query_plan: dict | None) -> str:
    """把 SubAgent 查询规划压缩成 DSL 生成 prompt 可直接消费的约束文本。"""
    if not isinstance(query_plan, dict):
        return ""

    query_type = query_plan.get("query_type") or ""
    execution_strategy = query_plan.get("execution_strategy") or ""
    planner_source = query_plan.get("planner_source") or ""
    explanation = query_plan.get("explanation") or {}
    debug = query_plan.get("debug") or {}
    summary = explanation.get("summary") if isinstance(explanation, dict) else ""

    lines = ["【查询规划】"]
    if query_type:
        lines.append(f"查询类型: {query_type}")
    if execution_strategy:
        lines.append(f"执行策略: {execution_strategy}")
    if planner_source:
        lines.append(f"规划来源: {planner_source}")
    if summary:
        lines.append(f"规划说明: {summary}")
    selected_main_table = debug.get("selected_main_table") if isinstance(debug, dict) else None
    if selected_main_table:
        lines.append(f"事实主表: {selected_main_table}")
    join_hints = debug.get("join_hints") if isinstance(debug, dict) else None
    if isinstance(join_hints, list) and join_hints:
        lines.append("必要 JOIN 线索:")
        for hint in join_hints[:5]:
            if not isinstance(hint, dict):
                continue
            left_table = hint.get("left_table")
            left_column = hint.get("left_column")
            right_table = hint.get("right_table")
            right_column = hint.get("right_column")
            if left_table and left_column and right_table and right_column:
                purpose = hint.get("purpose")
                suffix = f" ({purpose})" if purpose else ""
                lines.append(f"- {left_table}.{left_column} = {right_table}.{right_column}{suffix}")
    if execution_strategy == "blueprint_as_reference":
        lines.append("硬性要求: 命中的蓝图只能作为参考证据，不能原样执行蓝图 SQL。")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


_TASK_CAPSULE_BLOCKED_PROMPT_KEYS = {
    "data",
    "dataset",
    "direct_sql",
    "dsl",
    "raw",
    "raw_sql",
    "records",
    "result",
    "result_rows",
    "rows",
    "sample_rows",
    "sql",
    "sql_result",
}
_TASK_CAPSULE_ALLOWED_REF_KEYS = {"id", "ref", "task_id", "type"}
_TASK_CAPSULE_SQL_VALUE_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)
_TASK_CAPSULE_STRUCTURED_VALUE_RE = re.compile(
    r"(?is)(?:\b(rows|records|data|result_rows|raw_sql|sql_result|sql|dsl)\b\s*[:=])"
    r"|(?:[\"'](?:rows|records|data|result_rows|raw_sql|sql_result|sql|dsl)[\"']\s*:)"
    r"|```"
)
_TASK_CAPSULE_SECRET_VALUE_RE = re.compile(r"(?i)\b(password|secret|access_token|secret_token)\b")
_TASK_CAPSULE_TABLE_NAME_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$"
)


def _sanitize_task_capsule_prompt_value(value: Any, *, key_name: str = "") -> Any:
    key_lower = key_name.lower()
    if key_lower in _TASK_CAPSULE_BLOCKED_PROMPT_KEYS or "sql" in key_lower:
        return None
    if isinstance(value, dict):
        allowed_keys = _TASK_CAPSULE_ALLOWED_REF_KEYS if key_lower == "base_task_ref" else None
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            item_key_lower = key.lower()
            if allowed_keys is not None and item_key_lower not in allowed_keys:
                continue
            if item_key_lower in _TASK_CAPSULE_BLOCKED_PROMPT_KEYS or "sql" in item_key_lower:
                continue
            safe_item = _sanitize_task_capsule_prompt_value(item, key_name=key)
            if safe_item in (None, "", [], {}):
                continue
            sanitized[key] = safe_item
            if len(sanitized) >= 8:
                break
        return sanitized
    if isinstance(value, list):
        sanitized_list = [
            item
            for item in (
                _sanitize_task_capsule_prompt_value(item, key_name=key_name)
                for item in value[:5]
            )
            if item not in (None, "", [], {})
        ]
        return sanitized_list
    if isinstance(value, str):
        text = value.strip()
        if key_lower == "base_main_table" and not _TASK_CAPSULE_TABLE_NAME_RE.fullmatch(text):
            return None
        if (
            _TASK_CAPSULE_SQL_VALUE_RE.search(text)
            or _TASK_CAPSULE_STRUCTURED_VALUE_RE.search(text)
            or _TASK_CAPSULE_SECRET_VALUE_RE.search(text)
        ):
            return None
        return text[:300]
    return value


def _task_capsule_prompt_value(value: Any, *, key_name: str = "") -> str:
    safe_value = _sanitize_task_capsule_prompt_value(value, key_name=key_name)
    if isinstance(safe_value, dict):
        return json.dumps(safe_value, ensure_ascii=False)
    if isinstance(safe_value, list):
        return json.dumps(safe_value, ensure_ascii=False)
    return str(safe_value)


def _format_task_capsule_for_prompt(capsule: Any) -> str:
    """把 QueryTaskCapsule 压缩成 DSL prompt 可消费的安全字段摘要。"""
    if not isinstance(capsule, dict):
        return ""

    lines = ["【任务胶囊】"]
    for key in (
        "turn_type",
        "base_task_ref",
        "base_main_table",
        "standalone_question",
        "base_question",
    ):
        value = capsule.get(key)
        if value in (None, "", [], {}):
            continue
        prompt_value = _task_capsule_prompt_value(value, key_name=key)
        if prompt_value in ("", "{}", "[]", "None"):
            continue
        lines.append(f"{key}: {prompt_value}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _append_query_planning_context(
    human_text: str,
    query_plan_prompt: str,
    task_capsule_prompt: str,
    blueprint_context: str,
) -> str:
    """在 DSL prompt 末尾追加查询规划和蓝图上下文，避免改变原有提示词顺序。"""
    if query_plan_prompt:
        human_text += f"\n\n{query_plan_prompt}"
    task_capsule_prompt = (task_capsule_prompt or "").strip()
    if task_capsule_prompt and task_capsule_prompt not in human_text:
        human_text += f"\n\n{task_capsule_prompt}"
    blueprint_context = (blueprint_context or "").strip()
    if blueprint_context and blueprint_context not in human_text:
        human_text += f"\n\n{blueprint_context}"
    return human_text


_TRUSTED_FALLBACK_SQL_TEMPLATES = {"dataset10_log_detail"}


def _template_sql_from_query_plan(query_plan: dict | None) -> str:
    if not isinstance(query_plan, dict):
        return ""
    debug = query_plan.get("debug") if isinstance(query_plan.get("debug"), dict) else {}
    planner_source = query_plan.get("planner_source")
    template_name = str(debug.get("template_name") or "").strip()
    if planner_source != "template" and not (
        planner_source == "fallback" and template_name in _TRUSTED_FALLBACK_SQL_TEMPLATES
    ):
        return ""
    sql = debug.get("sql_template")
    return str(sql).strip() if sql else ""


def _empty_detail_query_error(state: AgentState) -> str | None:
    """为空明细 DSL 返回更可操作的诊断，避免误导为语义层整体损坏。"""

    query_plan = state.get("query_plan")
    if not isinstance(query_plan, dict):
        return None
    if query_plan.get("query_type") != "detail_query":
        return None

    debug = query_plan.get("debug") if isinstance(query_plan.get("debug"), dict) else {}
    selected_assets = query_plan.get("selected_assets")
    has_selected_assets = isinstance(selected_assets, list) and bool(selected_assets)
    template_name = str(debug.get("template_name") or "").strip()
    selected_main_table = str(debug.get("selected_main_table") or "").strip()

    if template_name:
        template_hint = f"已识别模板 {template_name}，但未拿到可用 SQL 模板"
    else:
        template_hint = "未命中可用明细模板"
    if selected_main_table:
        asset_hint = f"当前主表候选为 {selected_main_table}"
    elif has_selected_assets:
        asset_hint = "已有字段/表候选，但 DSL LLM 未生成 fields"
    else:
        asset_hint = "字段/表候选资产不足"

    return (
        "字段召回不足或模板未命中：明细查询没有生成可展示字段，也没有可用模板 SQL。"
        f"{asset_hint}；{template_hint}。"
        "请检查 candidate_assets 是否召回到日志主表字段、routing.dataset_id 是否正确，"
        "以及 query_plan.debug.template_name/sql_template 是否存在。"
    )


def merge_prior_context_node(state: AgentState) -> Dict[str, Any]:
    """虚拟 span 节点：决策已由 LeadAgent `merge_multiturn_decision_for_chat` 在
    LangGraph 之外完成（Phase 2 上提）。本节点仅保留供 `_merge_prior_context_router`
    按 state["entry_route"] 路由后续分支，以及 SSE 阶段标签和 observability 链路。
    """
    return {}


def _query_context_from_state(state: AgentState) -> dict[str, Any]:
    """为 out_capsule 组装可供下一轮继续追问的查询上下文。"""
    multiturn_context = _as_dict(state.get("multiturn_context"))
    merged = multiturn_context.get("merged_query_context")
    if isinstance(merged, dict):
        query_context = copy.deepcopy(merged)
    else:
        query_context = copy.deepcopy(state.get("dsl") or {})
    query_context.setdefault("question", state.get("question"))
    query_context.setdefault("dataset_id", state.get("dataset_id"))
    query_context.setdefault("generation_mode", state.get("generation_mode"))
    return query_context


def _result_columns(columns: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ResultDigest 只保存列结构，不保存结果行。"""

    if isinstance(columns, list) and columns:
        return [
            {"name": str(item), "type": _infer_column_type(str(item), rows)}
            if not isinstance(item, dict)
            else {
                "name": str(item.get("name") or item.get("column") or ""),
                "type": str(item.get("type") or "unknown"),
            }
            for item in columns
        ]
    if not rows:
        return []
    return [
        {"name": key, "type": _infer_column_type(key, rows)}
        for key in rows[0].keys()
    ]


def _infer_column_type(column: str, rows: list[dict[str, Any]]) -> str:
    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float, Decimal)):
            return "number"
        return "string"
    return "unknown"


def _numeric_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    values_by_column: dict[str, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float, Decimal)):
                values_by_column.setdefault(key, []).append(float(value))
    for key, values in values_by_column.items():
        if not values:
            continue
        summary[key] = {
            "min": min(values),
            "max": max(values),
            "sum": sum(values),
        }
    return summary


def _top_values(rows: list[dict[str, Any]], max_values: int = 5) -> dict[str, list[dict[str, Any]]]:
    values: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                continue
            bucket = values.setdefault(key, [])
            text = str(value)
            if not any(item["value"] == text for item in bucket):
                bucket.append({"value": text, "count": 1})
            else:
                for item in bucket:
                    if item["value"] == text:
                        item["count"] += 1
                        break
    return {
        key: sorted(items, key=lambda item: item["count"], reverse=True)[:max_values]
        for key, items in values.items()
    }


def _sql_audit_id(merged_state: dict[str, Any]) -> str | None:
    audit = _as_dict(merged_state.get("sql_audit_result"))
    for key in ("audit_id", "id", "sql_audit_id"):
        value = audit.get(key) or merged_state.get(key)
        if value is not None:
            return str(value)
    return None


def build_out_capsule(state: AgentState, updates: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成 SubAgent 输出胶囊，包含下一轮可复用的 query_context 和 ResultDigest 骨架。"""
    merged_state: dict[str, Any] = {**state, **(updates or {})}
    sql_result = _as_dict(merged_state.get("sql_result"))
    rows = _as_list(sql_result.get("rows"))
    error = merged_state.get("error")
    answer = merged_state.get("answer")
    result_digest = {
        "status": "failed" if error else ("ok" if sql_result else "empty"),
        "row_count": sql_result.get("row_count", len(rows) if rows else 0),
        "columns": _result_columns(sql_result.get("columns"), rows),
        "numeric_summary": _numeric_summary(rows),
        "top_values": _top_values(rows),
        "sql_count": len(_as_list(merged_state.get("sql_list"))),
        "sql_audit_id": _sql_audit_id(merged_state),
        "has_answer": bool(answer),
        "answer_preview": str(answer)[:300] if answer else None,
        "error": str(error)[:500] if error else None,
    }
    return jsonable_encoder(
        {
            "capsule_version": "subagent.v1",
            "dataset_id": merged_state.get("dataset_id"),
            "manifest_version": merged_state.get("manifest_version"),
            "bound_schema_version": merged_state.get("bound_schema_version"),
            "schema_version": merged_state.get("bound_schema_version"),
            "updated_turn": merged_state.get("turn_index") or 0,
            "question": merged_state.get("question"),
            "original_question": merged_state.get("original_question"),
            "resolved_question": merged_state.get("resolved_question") or merged_state.get("question"),
            "turn_type": merged_state.get("turn_type") or "new",
            "query_context": _query_context_from_state(merged_state),
            "multiturn_context": merged_state.get("multiturn_context"),
            "result_digest": result_digest,
            "last_result_digest": result_digest,
            "sql": merged_state.get("sql"),
            "sql_list": _as_list(merged_state.get("sql_list")),
            "generation_mode": merged_state.get("generation_mode"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    """判断文本是否包含任意入口分类关键词。"""
    return any(pattern in text for pattern in patterns)


def _collect_blueprint_terms(bp: AnalysisBlueprint) -> list[str]:
    """提取蓝图可用于路由匹配的关键词和示例。"""
    terms: list[str] = []
    values: list[Any] = [bp.name, bp.description, bp.when_to_use]
    if isinstance(bp.trigger_keywords, list):
        values.extend(bp.trigger_keywords)
    if isinstance(bp.trigger_examples, list):
        values.extend(bp.trigger_examples)
    for value in values:
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    return terms


def _format_blueprint_list(items: Any, *, key: str = "") -> list[str]:
    """将蓝图 JSON 列表字段转换为适合提示词消费的短文本。"""
    if not isinstance(items, list):
        return []
    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, str) and item.strip():
            lines.append(f"{idx}. {item.strip()}")
            continue
        if not isinstance(item, dict):
            continue
        if key and item.get(key):
            title = str(item.get(key)).strip()
        else:
            title = str(item.get("name") or item.get("column") or f"第{idx}项").strip()
        details = []
        for field in (
            "type",
            "semantic",
            "role",
            "purpose",
            "extract_hint",
            "default_expr",
            "required",
            "key_rules",
        ):
            value = item.get(field)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            details.append(f"{field}={value}")
        suffix = f"；{'; '.join(details)}" if details else ""
        lines.append(f"{idx}. {title}{suffix}")
    return lines


def _format_blueprint_semantic_context(bp: AnalysisBlueprint) -> str:
    """把手动创建的语义计划蓝图转成 QueryGraph 可使用的业务约束。"""
    lines = [
        "【命中的分析蓝图语义计划】",
        f"蓝图名称: {bp.name}",
        "执行方式: semantic_plan，不能要求用户提供 SQL；请基于数据集语义层和所选表结构生成查询。",
    ]
    if bp.when_to_use:
        lines.append(f"适用场景: {bp.when_to_use}")
    if bp.description:
        lines.append(f"业务描述: {bp.description}")
    # trigger_keywords / trigger_examples / attribution_hints 属路由阶段数据，SQL 生成不需要
    parameter_lines = _format_blueprint_list(bp.parameters, key="name")
    if parameter_lines:
        lines.append("需要从用户问题中理解的业务参数:")
        lines.extend(parameter_lines)
    output_lines = _format_blueprint_list(bp.output_schema, key="column")
    if output_lines:
        lines.append("期望输出列或结果口径:")
        lines.extend(output_lines)
    step_lines = _format_blueprint_list(bp.steps, key="name")
    if step_lines:
        lines.append("业务分析步骤:")
        lines.extend(step_lines)
    lines.append("硬性要求: 不要向用户索要 SQL；不要把参数占位符当成输出内容；优先按蓝图业务步骤组织查询。")
    return "\n".join(lines)


def _query_constraints_text(state: AgentState) -> str:
    """读取状态中的数据集查询约束，并渲染为 LLM 规则文本。"""
    return render_query_constraints_instruction(state.get("query_constraints"))


def _dsl_item_names(items: Any) -> list[str]:
    """读取 DSL 列表中的名称，兼容旧字符串和 v2 资产引用对象。"""
    if not isinstance(items, list):
        return []
    return [name for item in items if (name := get_dsl_item_name(item))]


def _dsl_field_name(field: Any) -> str:
    """读取 filter/order_by/time_range 中的字段名。"""
    return get_dsl_item_name(field)


def _structured_asset_index(structured: dict | None, section: str) -> tuple[set[str], set[int]]:
    """从 schema_structured 中提取指定语义资产的名称与 ID。"""
    names: set[str] = set()
    ids: set[int] = set()
    if not isinstance(structured, dict):
        return names, ids
    for item in structured.get(section) or []:
        if not isinstance(item, dict):
            continue
        for key in ("name", "display_name"):
            value = str(item.get(key) or "").strip()
            if value:
                names.add(value)
        asset_id = item.get("id") or item.get("asset_id")
        if isinstance(asset_id, int):
            ids.add(asset_id)
    return names, ids


def _dsl_unknown_assets(items: Any, valid_names: set[str], valid_ids: set[int]) -> list[str]:
    """校验 DSL 中的术语/蓝图资产引用是否存在。"""
    if not isinstance(items, list):
        return []
    unknown: list[str] = []
    for item in items:
        name = get_dsl_item_name(item)
        asset_id = get_dsl_asset_id(item)
        if asset_id is not None:
            if asset_id not in valid_ids:
                unknown.append(f"{name or '未命名'}#{asset_id}")
            continue
        if name and name not in valid_names:
            unknown.append(name)
    return unknown


def _coerce_text_list(value: Any) -> list[str]:
    """把 JSON / 字符串 / 列表里的别名清洗成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        raw_items = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            parsed = _safe_json_parse(stripped)
            raw_items = parsed if isinstance(parsed, list) else [stripped]
        else:
            raw_items = re.split(r"[,，、;/；\n]+", stripped)
    else:
        raw_items = [value]

    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _semantic_match_text(text: Any) -> str:
    """统一语义资产匹配用文本，忽略大小写、空白、下划线和常见引用符。"""
    if text is None:
        return ""
    return re.sub(r"[\s_`'\".]+", "", str(text).strip().lower())


def _dedupe_texts(values: list[Any]) -> list[str]:
    """按语义匹配规则去重，保留原始展示文本。"""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        norm = _semantic_match_text(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(text)
    return out


def _field_aliases(field: dict) -> list[str]:
    """字段资产可匹配名称，排除样例值，避免把查询参数值误当资产名。"""
    column_name = field.get("column_name") or field.get("name")
    short_column = str(column_name).split(".")[-1] if column_name else None
    return _dedupe_texts(
        [
            column_name,
            short_column,
            field.get("display_name"),
            field.get("column_comment"),
            field.get("business_desc"),
            field.get("effective_desc"),
            field.get("user_description"),
            field.get("ai_description"),
            *_coerce_text_list(field.get("synonyms")),
        ]
    )


def _query_plan_selected_asset_names(query_plan: dict | None) -> tuple[set[str], set[str]]:
    """提取 QueryPlan 已选字段和表，用于裁剪 DSL 资产目录。"""

    field_names: set[str] = set()
    table_names: set[str] = set()
    if not isinstance(query_plan, dict):
        return field_names, table_names
    for asset in query_plan.get("selected_assets") or []:
        if not isinstance(asset, dict):
            continue
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        asset_type = asset.get("asset_type")
        table_name = str(metadata.get("table_name") or "").strip()
        column_name = str(metadata.get("column_name") or asset.get("name") or "").split(".")[-1].strip()
        if table_name:
            table_names.add(table_name)
        if asset_type == "field" and column_name:
            field_names.add(column_name)
    return field_names, table_names


def _filter_catalog_fields(items: list[dict[str, Any]], query_plan: dict | None) -> list[dict[str, Any]]:
    field_names, table_names = _query_plan_selected_asset_names(query_plan)
    if not field_names and not table_names:
        return items[:_dsl_field_catalog_limit()]
    filtered: list[dict[str, Any]] = []
    for item in items:
        table_name = str(item.get("table_name") or "").strip()
        column_name = str(item.get("column_name") or item.get("name") or "").split(".")[-1].strip()
        if (table_name and table_name in table_names) or (column_name and column_name in field_names):
            filtered.append(item)
    return filtered[:_dsl_field_catalog_limit()]


def _format_dsl_asset_catalog(structured: dict | None, query_plan: dict | None = None) -> str:
    """把结构化语义层资产整理成 NL2DSL v2 可引用目录。fields 使用紧凑格式，unused 字段自动过滤。"""
    if not structured:
        return ""
    from app.utils.schema_formatter import format_fields_compact
    lines = ["【可引用语义资产（生成 DSL 时必须优先使用这里的 asset_id）】"]
    for asset_type, title, items in (
        ("metric", "指标", structured.get("metrics") or []),
        ("dimension", "维度", structured.get("dimensions") or []),
        ("field", "字段", structured.get("fields") or []),
        ("term", "业务术语", structured.get("terms") or []),
        ("blueprint", "分析蓝图", structured.get("blueprints") or []),
    ):
        if not items:
            continue
        if asset_type == "field":
            items = _filter_catalog_fields(items, query_plan)
            if not items:
                continue
        lines.append(f"{title}:")
        if asset_type == "field":
            # fields 使用紧凑行格式，unused 在 format_fields_compact 内部过滤
            compact = format_fields_compact(items)
            if compact:
                lines.append(compact)
            else:
                for item in items:
                    lines.append(
                        "- "
                        f"asset_type=field, asset_id={item.get('id')}, "
                        f"name={item.get('name')}, table={item.get('table_name')}, "
                        f"column={item.get('column_name') or item.get('name')}"
                    )
            continue
        for item in items:
            aliases = item.get("synonyms") or item.get("aliases") or []
            alias_text = f"，同义词={aliases}" if aliases else ""
            detail_parts: list[str] = []
            if asset_type == "metric":
                if item.get("expr"):
                    detail_parts.append(f"expr={item.get('expr')}")
                if item.get("table_name"):
                    detail_parts.append(f"table={item.get('table_name')}")
                if item.get("time_field"):
                    detail_parts.append(f"time_field={item.get('time_field')}")
            elif asset_type == "dimension":
                if item.get("table_name"):
                    detail_parts.append(f"table={item.get('table_name')}")
                if item.get("column_name"):
                    detail_parts.append(f"column={item.get('column_name')}")
            detail_text = f"，{', '.join(detail_parts)}" if detail_parts else ""
            lines.append(
                "- "
                f"asset_type={asset_type}, asset_id={item.get('id')}, "
                f"name={item.get('name')}, display_name={item.get('display_name') or item.get('name')}"
                f"{detail_text}{alias_text}"
            )
    return "\n".join(lines) if len(lines) > 1 else ""


def _extract_dataset_name(schema: str) -> str:
    match = re.search(r"^数据集:\s*(.+)$", schema or "", re.MULTILINE)
    return match.group(1).strip() if match else ""


def _format_progressive_semantic_context(
    state: AgentState,
    *,
    schema: str,
    structured: dict | None,
    asset_catalog: str,
    query_constraints_text: str,
) -> str:
    """为 DSL 生成构造渐进式披露上下文，避免重复注入完整 schema_context。"""

    if not structured:
        return schema

    query_plan = state.get("query_plan") if isinstance(state.get("query_plan"), dict) else {}
    debug = query_plan.get("debug") if isinstance(query_plan.get("debug"), dict) else {}
    dataset_name = structured.get("dataset_name") or _extract_dataset_name(schema) or "未知数据集"
    dataset_prompt = (state.get("dataset_prompt_instructions") or "").strip()
    context_debug = state.get("dataset_context_debug") or {}
    asset_counts = context_debug.get("asset_counts") or {}
    retained_counts = context_debug.get("retained_counts") or {}

    lines = [
        "【渐进式语义层上下文】",
        "说明: 以下内容按 L0-L3 渐进披露。优先使用 L0/L1/L2；只有必要时参考 L3 预算信息。",
        "",
        "【L0 数据集与任务】",
        f"- 数据集: {dataset_name}",
    ]
    query_type = query_plan.get("query_type")
    execution_strategy = query_plan.get("execution_strategy")
    if query_type:
        lines.append(f"- 查询类型: {query_type}")
    if execution_strategy:
        lines.append(f"- 执行策略: {execution_strategy}")
    selected_main_table = debug.get("selected_main_table")
    if selected_main_table:
        lines.append(f"- 事实主表: {selected_main_table}")
    if query_type == "detail_query":
        lines.append("- 明细查询允许使用 fields；不要求必须生成 metrics。")

    lines.extend(["", "【L1 硬约束】"])
    if query_constraints_text:
        lines.append(query_constraints_text)
    else:
        lines.append("（无额外查询约束）")
    if dataset_prompt:
        lines.append("")
        lines.append("【数据集级 LLM 约束（硬性要求）】")
        lines.append(dataset_prompt)

    lines.extend(["", "【L2 相关语义资产】"])
    if asset_catalog:
        lines.append(asset_catalog)
    else:
        lines.append("（当前未召回可引用语义资产，不能编造 asset_id）")

    lines.extend(["", "【L3 召回预算摘要】"])
    if asset_counts or retained_counts:
        lines.append(f"- asset_counts: {json.dumps(asset_counts, ensure_ascii=False)}")
        lines.append(f"- retained_counts: {json.dumps(retained_counts, ensure_ascii=False)}")
    else:
        lines.append("（无预算摘要）")
    return "\n".join(lines).strip()


def _match_analysis_blueprint(db: Session, dataset_id: int | None, question: str) -> dict | None:
    """在当前数据集的已发布分析蓝图中查找最匹配的路由目标。"""
    if not dataset_id:
        return None

    q_norm = _normalized_text(question)
    blueprints = (
        db.query(AnalysisBlueprint)
        .filter(
            AnalysisBlueprint.dataset_id == dataset_id,
            AnalysisBlueprint.status == "active",
        )
        .order_by(AnalysisBlueprint.usage_count.desc(), AnalysisBlueprint.updated_at.desc())
        .all()
    )

    best: dict | None = None
    for bp in blueprints:
        matched_terms: list[str] = []
        score = 0
        for term in _collect_blueprint_terms(bp):
            term_norm = _normalized_text(term)
            if not term_norm:
                continue
            if term_norm in q_norm:
                matched_terms.append(term)
                score += 3 if term in (bp.trigger_keywords or []) else 2
            elif q_norm in term_norm and len(q_norm) >= 4:
                matched_terms.append(term)
                score += 1

        if score <= 0:
            continue
        candidate = {
            "blueprint_id": bp.id,
            "name": bp.name,
            "score": score,
            "matched_terms": matched_terms[:5],
            "call_template": bp.call_template,
        }
        if best is None or score > best["score"]:
            best = candidate
    return best


def _match_business_term(db: Session, dataset_id: int | None, question: str) -> dict | None:
    """按业务术语名称和别名匹配知识库问答目标。"""
    if not dataset_id:
        return None

    q_norm = _normalized_text(question)
    terms = (
        db.query(BusinessTerm)
        .filter(BusinessTerm.dataset_id == dataset_id, BusinessTerm.status == "active")
        .order_by(BusinessTerm.updated_at.desc(), BusinessTerm.id.desc())
        .all()
    )

    for term in terms:
        candidates = [term.name, term.display_name, *(term.aliases or [])]
        matched = [
            c
            for c in candidates
            if isinstance(c, str) and c.strip() and _normalized_text(c) in q_norm
        ]
        if matched:
            return {
                "term_id": term.id,
                "name": term.display_name or term.name,
                "definition": term.definition,
                "matched_terms": matched[:5],
            }
    return None


def intent_recognition_node(state: AgentState, db: Session | None = None) -> Dict[str, Any]:
    """识别用户意图，判断是数据查询、闲聊还是功能操作。

    DEPRECATED (Phase 3): 入口路由逻辑已上提到 app.services.lead_agent_routing.route_query_intent，
    由 chat.py 在驱动 LangGraph 之前调用。本节点保留为 noop 兜底（返回 {}），仅供旧测试 import 路径不破。

    实际逻辑迁出到 lead_agent_routing.py；该函数保留为空 stub。
    """
    return {}


def entry_intent_classification_node(db: Session):
    """构建 QueryGraph 前置入口分类节点。

    DEPRECATED (Phase 3): 入口路由逻辑已上提到 app.services.lead_agent_routing.route_query_intent，
    由 chat.py 在驱动 LangGraph 之前调用。本节点保留为 noop 兜底（返回 {}），仅供旧测试 import 路径不破。
    """

    def _node(state: AgentState) -> Dict[str, Any]:
        return {}

    return _node


def lead_agent_node(state: AgentState) -> Dict[str, Any]:
    """LeadAgent 总入口 noop 节点：入口路由决策已由 chat.py 在驱动 LangGraph 之前
    通过 `route_query_intent` 完成。LangGraph 入口指向本节点仅用于：
    1. 保留 SSE `lead_agent` 步骤事件，兼容前端按节点展示的约定
    2. 作为 `_merge_prior_context_router` 的入口（按 state["entry_route"] 路由后续分支）

    真正的工作流主线从 clarification_resolution 开始（query_graph 主链）。
    """
    return {"lead_agent_context": state.get("lead_agent_context") or {}}


def analysis_blueprint_execute_node(db: Session):
    """执行已发布分析蓝图，或将手动语义蓝图交回 QueryGraph。"""

    def _node(state: AgentState) -> Dict[str, Any]:
        blueprint_id = state.get("blueprint_id")
        question = state.get("question") or ""
        dataset_id = state.get("dataset_id")
        logger.info("分析蓝图执行开始: blueprint_id=%s, dataset_id=%s", blueprint_id, dataset_id)

        if not blueprint_id:
            return {
                "sql_result": None,
                "error": "未命中分析蓝图，无法执行",
                "should_retry": False,
            }

        bp = db.get(AnalysisBlueprint, blueprint_id)
        if not bp or (dataset_id and bp.dataset_id != dataset_id):
            return {
                "sql_result": None,
                "error": "分析蓝图不存在或不属于当前数据集",
                "should_retry": False,
            }

        implementation_type = (bp.implementation_type or "").strip()
        if implementation_type == "semantic_plan":
            blueprint_context = _format_blueprint_semantic_context(bp)
            logger.info(
                "分析蓝图为语义计划，转入 QueryGraph: blueprint_id=%s, context_len=%s",
                bp.id,
                len(blueprint_context),
            )
            return jsonable_encoder({
                "sql_result": None,
                "sql": None,
                "sql_list": [],
                "blueprint_context": blueprint_context,
                "generation_mode": "analysis_blueprint_semantic",
                "error": None,
                "should_retry": False,
                "route_payload": {
                    "kind": "analysis_blueprint_semantic",
                    "blueprint_id": bp.id,
                    "name": bp.name,
                    "implementation_type": implementation_type,
                },
            })

        result = execute_analysis_blueprint(
            db,
            bp,
            question=question,
            input_params=blueprint_params_from_time_context(bp, state.get("time_context")),
            require_active=True,
            count_usage=True,
        )
        if not result.get("ok"):
            missing = result.get("missing") or []
            answer = result.get("error") or "分析蓝图执行失败"
            display_sql = result.get("sql_preview") or result.get("sql")
            route_payload = {
                "kind": "clarification" if missing else "analysis_blueprint_error",
                "blueprint_id": bp.id,
                "params": result.get("params") or {},
                "sql_template": result.get("sql"),
                "original_question": state.get("original_question") or question,
                "resolved_question": state.get("resolved_question") or question,
            }
            if missing:
                route_payload["missing"] = missing
            return jsonable_encoder({
                "sql_result": None,
                "sql": display_sql,
                "sql_list": [display_sql] if display_sql else [],
                "error": answer,
                "answer": answer,
                "route_payload": {
                    **route_payload,
                },
                "should_retry": False,
            })

        display_sql = result.get("sql_preview") or result["sql"]
        return jsonable_encoder({
            "sql": display_sql,
            "sql_list": [display_sql],
            "sql_result": result["sql_result"],
            "generation_mode": "analysis_blueprint",
            "error": None,
            "should_retry": False,
            "route_payload": {
                "kind": "analysis_blueprint",
                "blueprint_id": bp.id,
                "name": bp.name,
                "params": result["params"],
                "sql_template": result["sql"],
                "original_question": state.get("original_question") or question,
                "resolved_question": state.get("resolved_question") or question,
                "execution_time_ms": result["execution_time_ms"],
            },
        })

    return _node


# ── 节点 2: Schema 召回（可选）──────────────────────────


def schema_recall_node(db: Session):
    """根据 dataset_id 召回语义层信息，注入 LLM prompt。
    - 有 dataset_id + 语义层存在 → 构建【语义层】上下文 + 结构化对象
    - 无 dataset_id → 从已连接数据源拉真实表结构 → 【数据源真实表结构】
    """

    def _node(state: AgentState) -> Dict[str, Any]:
        dataset_id = state.get("dataset_id")
        blueprint_context = (state.get("blueprint_context") or "").strip()
        default_constraints = normalize_query_constraints(None)
        logger.info(f"Schema召回节点开始: dataset_id={dataset_id}")
        if not dataset_id:
            datasource = db.query(Datasource).filter(Datasource.status == "connected").first()
            if datasource:
                logger.info(
                    f"未提供dataset_id，从数据源获取真实表结构: datasource_id={datasource.id}"
                )
                try:
                    from app.services.datasource import get_schema as fetch_schema

                    real_tables = fetch_schema(datasource)
                    lines = ["【数据源真实表结构】", ""]
                    for t in real_tables[:20]:
                        cols = ", ".join(
                            [f"{c['name']} ({c['type']})" for c in t.get("columns", [])]
                        )
                        lines.append(f"表: {t['name']} | 列: {cols}")
                    if len(lines) == 2:
                        lines.append("（数据源无可用表）")
                    schema_context = "\n".join(lines)
                    if blueprint_context:
                        schema_context = f"{schema_context}\n\n{blueprint_context}"
                    return {
                        "schema_context": schema_context,
                        "dataset_id": None,
                        "schema_structured": None,
                        "ddl_context": None,
                        "query_constraints": default_constraints,
                        "dataset_prompt_instructions": blueprint_context or None,
                    }
                except Exception as e:
                    logger.error(f"读取数据源Schema失败: {e}")
                    return {
                        "schema_context": f"无法读取数据源 Schema: {e}",
                        "dataset_id": None,
                        "schema_structured": None,
                        "ddl_context": None,
                        "query_constraints": default_constraints,
                    }
            else:
                return {
                    "schema_context": "",
                    "dataset_id": None,
                    "schema_structured": None,
                    "ddl_context": None,
                    "query_constraints": default_constraints,
                }

        ds = db.get(SemanticDataset, dataset_id)
        if not ds:
            logger.warning(f"数据集不存在: dataset_id={dataset_id}")
            return {
                "schema_context": "",
                "dataset_id": None,
                "schema_structured": None,
                "ddl_context": None,
                "query_constraints": default_constraints,
            }

        context_result = build_dataset_query_context(
            db,
            ds.id,
            question=state.get("question") or "",
            blueprint_context=blueprint_context,
            matched_assets=state.get("semantic_asset_resolution"),
        )
        debug = context_result.get("dataset_context_debug") or {}
        asset_counts = debug.get("asset_counts") or {}
        retained_counts = debug.get("retained_counts") or {}
        logger.info(
            "使用数据集问数上下文: dataset=%s(id=%s), assets=%s, retained=%s, tokens=%s/%s",
            ds.name,
            ds.id,
            asset_counts,
            retained_counts,
            debug.get("estimated_tokens"),
            debug.get("token_budget"),
        )
        if not (asset_counts.get("metrics") or asset_counts.get("dimensions")):
            logger.warning(
                "【Schema 召回未命中】dataset=%s(id=%s) | metrics=0, dimensions=0",
                ds.name,
                ds.id,
            )
        return {
            **context_result,
            "dataset_id": ds.id,
        }

    return _node



# ── 节点 3: DSL / SQL 生成 ──────────────────────────────────


def dsl_generate_node(state: AgentState, db: Session | None = None) -> Dict[str, Any]:
    """三条路径：
    1. 【语义层】→ LLM 生成结构化 DSL JSON
    2. 【数据源真实表结构】→ LLM 直接生成 SQL
    3. 完全没有 schema → LLM 猜 SQL
    """
    question = state["question"]
    logger.info(f"DSL生成节点开始: question={question[:50]}...")
    schema = state.get("schema_context", "")
    entities = state.get("entities", {})
    retry_count = state.get("retry_count", 0)
    error = state.get("error")
    query_constraints = normalize_query_constraints(state.get("query_constraints"))
    query_constraints_text = _query_constraints_text(state)
    multiturn_prompt = _format_query_context_for_prompt(state.get("multiturn_context"))
    query_plan_prompt = _format_query_plan_for_prompt(state.get("query_plan"))
    task_capsule_prompt = _format_task_capsule_for_prompt(state.get("query_task_capsule"))
    blueprint_context = (state.get("blueprint_context") or "").strip()
    if query_constraints["enabled"]:
        dsl_limit_example = query_constraints["default_limit"]
        semantic_time_rule = (
            f"3. 用户没有明确时间范围时，默认查询最近 {query_constraints['default_time_range_days']} 天\n"
        )
        semantic_limit_rule = (
            f"5. 用户没有明确返回条数时，默认 limit={query_constraints['default_limit']}；"
            f"最大不能超过 {query_constraints['max_limit']}\n"
        )
    else:
        dsl_limit_example = "null"
        semantic_time_rule = "3. 时间范围只在用户明确提出时设置，不要自行添加默认时间范围\n"
        semantic_limit_rule = "5. 用户明确要求返回条数时再设置 limit；否则可以省略或设为 null\n"

    template_sql = _template_sql_from_query_plan(state.get("query_plan"))
    if template_sql:
        logger.info("DSL生成命中模板旁路: template_sql_len=%s", len(template_sql))
        return {
            "dsl": {"direct_sql": template_sql, "template": True},
            "sql": template_sql,
            "sql_list": [template_sql],
            "generation_mode": "template",
            "error": None,
            "should_retry": False,
            "llm_skipped_reason": "query_plan_template_sql",
            "token_usage": state.get("token_usage"),
        }

    llm = get_llm(temperature=0.1, role="dsl", db=db)

    has_semantic = bool(schema and "【语义层】" in schema)
    has_real_schema = bool(schema and "【数据源真实表结构】" in schema)
    logger.info(f"DSL生成路径判断: has_semantic={has_semantic}, has_real_schema={has_real_schema}")

    # ── 路径 2: 真实数据源 Schema，直接生成 SQL ──
    if has_real_schema:
        query_rules = (
            f"3. 请遵守以下查询约束：\n{query_constraints_text}\n"
            if query_constraints_text
            else ""
        )
        system = SystemMessage(content=build_real_schema_system(query_rules))
        human_text = f"用户问题: {question}\n\n真实表结构:\n{schema}"
        if multiturn_prompt:
            human_text += f"\n\n【多轮查询上下文】\n{multiturn_prompt}"
        if error:
            human_text += f"\n\n上一轮错误: {error}"
        human_text = _append_query_planning_context(
            human_text,
            query_plan_prompt,
            task_capsule_prompt,
            blueprint_context,
        )
        human = HumanMessage(content=human_text)
        logger.debug(
            "【DSL生成提示词】路径=真实Schema\n[System]\n%s\n[Human]\n%s\n---END OF DSL PROMPT---",
            system.content,
            human_text,
        )
        response, llm_err = _safe_llm_invoke(llm, [system, human], path="真实Schema")
        if llm_err:
            return {"dsl": {}, "sql": None, "sql_list": [], "error": llm_err, "should_retry": False}
        result = _safe_json_parse(str(response.content))
        sql = result.get("sql", "")
        usage = _extract_token_usage(response, [system, human])
        merged = _merge_token_usage(state.get("token_usage") or {}, usage)
        logger.debug(
            "【DSL生成 LLM 返回】路径=真实Schema\n[Raw]\n%s\n[Parsed]\n%s\n[Usage]\n%s\n---END OF DSL RESPONSE---",
            response.content,
            json.dumps(result, ensure_ascii=False, indent=2),
            json.dumps(usage, ensure_ascii=False, indent=2),
        )
        if sql:
            logger.info("真实Schema路径: SQL生成成功")
            return {
                "dsl": {"direct_sql": sql},
                "sql": sql,
                "sql_list": [sql],
                "error": None,
                "token_usage": merged,
            }
        logger.warning("真实Schema路径: LLM未生成有效SQL")
        return {
            "dsl": {},
            "sql": None,
            "sql_list": [],
            "error": "LLM 未生成有效 SQL",
            "should_retry": True,
            "token_usage": merged,
        }

    # ── 路径 1: 语义层 DSL（确定性路径 / 推断路径）──
    if has_semantic:
        structured = state.get("schema_structured")
        ddl_context = state.get("ddl_context", "")
        metric_resolution = state.get("metric_resolution") or {}
        term_normalization = state.get("term_normalization") or {}
        semantic_asset_resolution = state.get("semantic_asset_resolution") or {}
        asset_catalog = _format_dsl_asset_catalog(structured, state.get("query_plan"))
        all_matched = metric_resolution.get("all_matched", True)
        unresolved = metric_resolution.get("unresolved", [])

        # 检查语义层中是否存在可用的语义资产（指标/维度/蓝图）
        # 如果语义层资产为空，即便 all_matched 为 True（例如 metric_resolution
        # 未设置或空列表的真空真），确定性路径也无法生成有效 DSL，应回退到
        # 基于 DDL 的推断路径。
        has_semantic_assets = bool(
            (structured or {}).get("metrics")
            or (structured or {}).get("dimensions")
            or (structured or {}).get("blueprints")
        )

        # 推断路径：指标未在语义层中定义 或 语义层无可用的语义资产，
        # 基于表结构（DDL）让 LLM 直接生成 SQL
        if (not all_matched or not has_semantic_assets) and ddl_context:
            logger.info(
                "走推断路径: 未解析指标=%s, has_semantic_assets=%s",
                unresolved,
                has_semantic_assets,
            )
            # 如果数据集没有选择任何表，直接报错，不让 LLM 瞎猜
            if "该数据集尚未选择任何表" in ddl_context:
                return {
                    "dsl": {},
                    "sql": None,
                    "sql_list": [],
                    "generation_mode": "inferred",
                    "error": "该数据集尚未选择任何数据源表，请先在数据集配置中勾选表后再提问。",
                    "should_retry": False,
                    "token_usage": state.get("token_usage"),
                }

            query_rules = (
                f"3. 请遵守以下查询约束：\n{query_constraints_text}\n"
                if query_constraints_text
                else ""
            )
            system = SystemMessage(content=build_inferred_system(query_rules))
            human_text = f"用户问题: {question}\n\n表结构:\n{ddl_context}"
            if multiturn_prompt:
                human_text += f"\n\n【多轮查询上下文】\n{multiturn_prompt}"
            if entities:
                human_text += f"\n\n已识别实体: {json.dumps(entities, ensure_ascii=False)}"
            if error:
                human_text += f"\n\n上一轮错误（请修正）: {error}"
            # 推断路径走 ddl_context 而非 schema_context，约束必须单独追加
            dataset_prompt = state.get("dataset_prompt_instructions") or ""
            if dataset_prompt.strip():
                human_text += (
                    f"\n\n【数据集级 LLM 约束（硬性要求）】\n{dataset_prompt.strip()}"
                )
            human_text = _append_query_planning_context(
                human_text,
                query_plan_prompt,
                task_capsule_prompt,
                blueprint_context,
            )
            human = HumanMessage(content=human_text)
            logger.debug(
                "【DSL生成提示词】路径=语义层-推断\n[System]\n%s\n[Human]\n%s\n---END OF DSL PROMPT---",
                system.content,
                human_text,
            )
            response, llm_err = _safe_llm_invoke(llm, [system, human], path="语义层-推断")
            if llm_err:
                return {"dsl": {}, "sql": None, "sql_list": [], "generation_mode": "inferred", "error": llm_err, "should_retry": False}
            result = _safe_json_parse(str(response.content))
            sql = result.get("sql", "")
            usage = _extract_token_usage(response, [system, human])
            merged = _merge_token_usage(state.get("token_usage") or {}, usage)
            logger.debug(
                "【DSL生成 LLM 返回】路径=语义层-推断\n[Raw]\n%s\n[Parsed]\n%s\n[Usage]\n%s\n---END OF DSL RESPONSE---",
                response.content,
                json.dumps(result, ensure_ascii=False, indent=2),
                json.dumps(usage, ensure_ascii=False, indent=2),
            )
            if sql:
                logger.info("推断路径: SQL生成成功")
                return {
                    "dsl": {"direct_sql": sql, "inferred": True},
                    "sql": sql,
                    "sql_list": [sql],
                    "generation_mode": "inferred",
                    "error": None,
                    "token_usage": merged,
                }
            logger.warning("推断路径: LLM未生成有效SQL")
            return {
                "dsl": {},
                "sql": None,
                "sql_list": [],
                "generation_mode": "inferred",
                "error": "LLM 未生成有效 SQL",
                "should_retry": True,
                "token_usage": merged,
            }

        # 确定性路径：指标在语义层中有定义
        logger.info("走确定性路径: 指标全部匹配语义层")

        # 构建 metric_resolution 的提示文本，告诉 LLM 每个实体对应语义层中的哪个 name
        resolution_text = ""
        if metric_resolution:
            res_lines = ["已识别实体解析:"]
            for r in metric_resolution.get("metrics", []):
                if r["status"] == "matched":
                    matched_metric = None
                    if structured:
                        matched_metric = next(
                            (
                                m
                                for m in structured.get("metrics", [])
                                if m.get("name") == r["resolved"]
                            ),
                            None,
                        )
                    asset_id_text = (
                        f"，asset_id={matched_metric.get('id')}"
                        if matched_metric and matched_metric.get("id") is not None
                        else ""
                    )
                    res_lines.append(
                        f"- 指标 '{r['entity']}' → 语义层名称 '{r['resolved']}' ({r['match_type']}{asset_id_text})"
                    )
                else:
                    res_lines.append(f"- 指标 '{r['entity']}' → 未在语义层中定义")
            for r in metric_resolution.get("dimensions", []):
                if r["status"] == "matched":
                    matched_dimension = None
                    if structured:
                        matched_dimension = next(
                            (
                                d
                                for d in structured.get("dimensions", [])
                                if d.get("name") == r["resolved"]
                            ),
                            None,
                        )
                    asset_id_text = (
                        f"，asset_id={matched_dimension.get('id')}"
                        if matched_dimension and matched_dimension.get("id") is not None
                        else ""
                    )
                    res_lines.append(
                        f"- 维度 '{r['entity']}' → 语义层名称 '{r['resolved']}' ({r['match_type']}{asset_id_text})"
                    )
                else:
                    res_lines.append(f"- 维度 '{r['entity']}' → 未在语义层中定义")
            resolution_text = "\n".join(res_lines)

        system = SystemMessage(
            content=build_semantic_system(dsl_limit_example, semantic_time_rule, semantic_limit_rule)
        )
        semantic_prompt_context = _format_progressive_semantic_context(
            state,
            schema=schema,
            structured=structured,
            asset_catalog=asset_catalog,
            query_constraints_text=query_constraints_text,
        )
        human_text = f"用户问题: {question}\n\n语义层信息:\n{semantic_prompt_context}"
        if multiturn_prompt:
            human_text += f"\n\n【多轮查询上下文】\n{multiturn_prompt}"
        if term_normalization:
            human_text += (
                "\n\n【业务术语归一化结果】\n"
                f"{json.dumps(term_normalization, ensure_ascii=False)[:2000]}"
            )
        if semantic_asset_resolution:
            human_text += (
                "\n\n【语义资产解析结果】\n"
                f"{json.dumps(semantic_asset_resolution, ensure_ascii=False)[:3000]}"
            )
        if resolution_text:
            human_text += f"\n\n{resolution_text}"
        if entities:
            human_text += f"\n\n原始识别实体: {json.dumps(entities, ensure_ascii=False)}"
        if error:
            human_text += f"\n\n上一轮错误（请修正）: {error}"
        human_text = _append_query_planning_context(
            human_text,
            query_plan_prompt,
            task_capsule_prompt,
            blueprint_context,
        )
        human = HumanMessage(content=human_text)
        logger.debug(
            "【DSL生成提示词】路径=语义层-确定性\n[System]\n%s\n[Human]\n%s\n---END OF DSL PROMPT---",
            system.content,
            human_text,
        )
        response, llm_err = _safe_llm_invoke(llm, [system, human], path="语义层-确定性")
        if llm_err:
            return {"dsl": {}, "sql": None, "sql_list": [], "generation_mode": "semantic", "error": llm_err, "should_retry": False}
        dsl = normalize_dsl(_safe_json_parse(str(response.content)))
        usage = _extract_token_usage(response, [system, human])
        merged = _merge_token_usage(state.get("token_usage") or {}, usage)
        logger.debug(
            "【DSL生成 LLM 返回】路径=语义层-确定性\n[Raw]\n%s\n[Parsed]\n%s\n[Usage]\n%s\n---END OF DSL RESPONSE---",
            response.content,
            json.dumps(dsl, ensure_ascii=False, indent=2),
            json.dumps(usage, ensure_ascii=False, indent=2),
        )
        logger.info("确定性路径: DSL生成成功")
        return {
            "dsl": dsl,
            "retry_count": retry_count,
            "should_retry": False,
            "generation_mode": "semantic",
            "error": None,
            "token_usage": merged,
        }

    # ── 路径 3: 完全没有 schema，LLM 猜 SQL ──
    logger.info("走无Schema路径: 让LLM猜测SQL")
    query_rules = (
        f"2. 请遵守以下查询约束：\n{query_constraints_text}\n" if query_constraints_text else ""
    )
    system = SystemMessage(content=build_no_schema_system(query_rules))
    human_text = f"用户问题: {question}"
    if multiturn_prompt:
        human_text += f"\n\n【多轮查询上下文】\n{multiturn_prompt}"
    if error:
        human_text += f"\n\n上一轮错误: {error}"
    human_text = _append_query_planning_context(
        human_text,
        query_plan_prompt,
        task_capsule_prompt,
        blueprint_context,
    )
    human = HumanMessage(content=human_text)
    logger.debug(
        "【DSL生成提示词】路径=无Schema\n[System]\n%s\n[Human]\n%s\n---END OF DSL PROMPT---",
        system.content,
        human_text,
    )
    response, llm_err = _safe_llm_invoke(llm, [system, human], path="无Schema")
    if llm_err:
        return {"dsl": {}, "sql": None, "sql_list": [], "error": llm_err, "should_retry": False}
    result = _safe_json_parse(str(response.content))
    sql = result.get("sql", "")
    usage = _extract_token_usage(response, [system, human])
    merged = _merge_token_usage(state.get("token_usage") or {}, usage)
    logger.debug(
        "【DSL生成 LLM 返回】路径=无Schema\n[Raw]\n%s\n[Parsed]\n%s\n[Usage]\n%s\n---END OF DSL RESPONSE---",
        response.content,
        json.dumps(result, ensure_ascii=False, indent=2),
        json.dumps(usage, ensure_ascii=False, indent=2),
    )
    if sql:
        logger.info("无Schema路径: SQL生成成功")
        return {
            "dsl": {"direct_sql": sql},
            "sql": sql,
            "sql_list": [sql],
            "error": None,
            "token_usage": merged,
        }
    logger.warning("无Schema路径: LLM未生成有效SQL")
    return {
        "dsl": {},
        "sql": None,
        "sql_list": [],
        "error": "LLM 未生成有效 SQL",
        "should_retry": True,
        "token_usage": merged,
    }


# ── 节点 4: DSL 校验 ──────────────────────────────────


def dsl_validate_node(state: AgentState) -> Dict[str, Any]:
    """DSL 基础校验 — 仅做轻量级成员检查：
    - DSL 非空
    - metrics 非空
    - 指标 / 维度 / filter.field 的 name ∈ valid_names（来自 schema_structured）

    **深度判断**（DDL 列名是否存在、time_field 是否合法、join 字段是否匹配等）
    下放给 sql_audit_node，由 LLM 结合 DDL + 样例数据做语义级诊断。
    这样设计的原因：基础校验能在毫秒内拦下 80% 的 LLM 瞎填错误；
    复杂错误（time_field 错填 DDL 列名、!= null 等）由 sql_audit 给 LLM 喂 DDL
    和样例，重试命中率显著提升。
    """
    logger.info("DSL校验节点开始（基础校验，深度判断交由 sql_audit）")
    dsl = normalize_dsl(state.get("dsl") or {})
    schema = state.get("schema_context") or ""
    structured = state.get("schema_structured")

    # direct_sql 模式（真实 Schema 或无 Schema 路径）
    if "direct_sql" in dsl:
        sql = dsl.get("direct_sql", "")
        if not sql:
            return _attach_sql_retry_failure(
                state,
                {
                    "dsl": dsl,
                    "dsl_valid": False,
                    "error": "LLM 未生成有效 SQL",
                    "should_retry": True,
                },
                result="自动修复未生成有效 SQL",
            )
        return {"dsl": dsl, "dsl_valid": True, "error": None, "should_retry": False}

    # 真实数据源 Schema 模式
    if schema and "【数据源真实表结构】" in schema:
        sql = dsl.get("sql") or ""
        if not sql:
            return _attach_sql_retry_failure(
                state,
                {
                    "dsl": dsl,
                    "dsl_valid": False,
                    "error": "LLM 未生成有效 SQL",
                    "should_retry": True,
                },
                result="自动修复未生成有效 SQL",
            )
        return {"dsl": dsl, "dsl_valid": True, "error": None, "should_retry": False}

    # 语义层 DSL 模式
    if not dsl or not isinstance(dsl, dict):
        return _attach_sql_retry_failure(
            state,
            {
                "dsl": dsl,
                "dsl_valid": False,
                "error": "DSL 为空或格式错误",
                "should_retry": True,
            },
            result="自动修复未生成有效 DSL",
        )

    # 优先从结构化对象中提取有效名称（包含原始字段，LLM 可基于上下文推理使用）
    if structured:
        valid_names = {m["name"] for m in structured.get("metrics", [])}
        valid_names.update({d["name"] for d in structured.get("dimensions", [])})
        valid_names.update({f["name"] for f in structured.get("fields", [])})
        valid_term_names, valid_term_ids = _structured_asset_index(structured, "terms")
        valid_blueprint_names, valid_blueprint_ids = _structured_asset_index(
            structured, "blueprints"
        )
    else:
        # fallback: 从文本中提取
        valid_names = set()
        valid_term_names = set()
        valid_term_ids = set()
        valid_blueprint_names = set()
        valid_blueprint_ids = set()
        for line in schema.split("\n"):
            m = re.match(r"-\s+(\w+)\s+\([^)]+\):", line)
            if m:
                valid_names.add(m.group(1))

    errors = []
    metrics = _dsl_item_names(dsl.get("metrics", []))
    dsl_fields_names = _dsl_item_names(dsl.get("fields", []))
    dsl_dim_names = _dsl_item_names(dsl.get("dimensions", []))
    if not metrics and not dsl_fields_names and not dsl_dim_names:
        errors.append(
            _empty_detail_query_error(state)
            or "查询条件不足：metrics/dimensions/fields 至少需要一项"
        )
    for m in metrics:
        if m not in valid_names:
            errors.append(f"指标 '{m}' 不在语义层定义中")
    for d in dsl_dim_names:
        if d not in valid_names:
            errors.append(f"维度 '{d}' 不在语义层定义中")
    for f_name in dsl_fields_names:
        if f_name not in valid_names:
            errors.append(f"字段 '{f_name}' 不在语义层定义中")
    for f in dsl.get("filters", []):
        field = _dsl_field_name(f.get("field"))
        if field and field not in valid_names:
            errors.append(f"过滤字段 '{field}' 不在语义层定义中")
    unknown_terms = _dsl_unknown_assets(
        dsl.get("terms", []), valid_term_names, valid_term_ids
    )
    for term in unknown_terms:
        errors.append(f"业务术语 '{term}' 不在语义层定义中")
    unknown_blueprints = _dsl_unknown_assets(
        dsl.get("blueprints", []), valid_blueprint_names, valid_blueprint_ids
    )
    for blueprint in unknown_blueprints:
        errors.append(f"分析蓝图 '{blueprint}' 不在语义层定义中")

    if errors:
        logger.warning(f"DSL校验失败: {'; '.join(errors)}")
        error_text = "; ".join(errors)
        return _attach_sql_retry_failure(
            state,
            {
                "dsl": dsl,
                "dsl_valid": False,
                "error": error_text,
                "should_retry": True,
            },
            result="自动修复生成的 DSL 未通过校验",
        )
    logger.info("DSL校验通过")
    return {"dsl": dsl, "dsl_valid": True, "error": None, "should_retry": False}


# ── 节点 5: DSL 编译器（代码实现）─────────────────────────


def dsl_compiler_node(db: Session):
    """将 DSL JSON 翻译为可执行 SQL（方言感知）。
    优先从 schema_structured 中读取结构化配置，支持 JOIN 和多表查询。
    根据数据集所属数据源的 db_type 选择 identifier 引号（MySQL/SQLite 用反引号，Postgres/Oracle 用双引号）。"""

    def _node(state: AgentState) -> Dict[str, Any]:
        logger.info("DSL编译节点开始")
        dsl = normalize_dsl(state.get("dsl") or {})
        schema = state.get("schema_context") or ""
        structured = state.get("schema_structured")
        query_constraints = normalize_query_constraints(state.get("query_constraints"))

        datasource_context = state.get("datasource_context") or {}
        allowed_tables = datasource_context.get("allowed_tables") or []
        # 推断方言（优先使用 schema_recall 生成的数据源上下文）
        dataset_id = state.get("dataset_id")
        dialect = datasource_context.get("dialect") or _resolve_dialect(db, dataset_id)
        logger.info(f"DSL编译方言: {dialect} (dataset_id={dataset_id})")

        # direct_sql 模式
        if "direct_sql" in dsl:
            sql = dsl.get("direct_sql", "")
            if not sql:
                logger.error("direct_sql模式: SQL为空")
                return _attach_sql_retry_failure(
                    state,
                    {"sql": None, "error": "未生成有效 SQL"},
                    result="自动修复未生成可执行 SQL",
                )
            guard_result = _guard_readonly_sql(
                sql,
                dialect=dialect,
                query_constraints=query_constraints,
                allowed_tables=allowed_tables,
            )
            if not guard_result.ok:
                logger.error("direct_sql模式: SQL Guard 拦截: %s", guard_result.error)
                return _attach_sql_retry_failure(
                    state,
                    {
                    "sql": None,
                    "error": guard_result.error,
                    "sql_guard": guard_result.__dict__,
                    "should_retry": False,
                    },
                    result="自动修复后的 SQL 未通过安全校验",
                )
            sql = guard_result.normalized_sql or sql
            logger.info("direct_sql模式: 编译成功")
            return {
                "sql": sql,
                "sql_list": [sql],
                "error": None,
                "sql_guard": guard_result.__dict__,
            }

        # 真实数据源 Schema 模式
        if schema and "【数据源真实表结构】" in schema:
            sql = dsl.get("sql") or ""
            if not sql:
                logger.error("真实Schema模式: SQL为空")
                return _attach_sql_retry_failure(
                    state,
                    {"sql": None, "error": "未生成有效 SQL"},
                    result="自动修复未生成可执行 SQL",
                )
            guard_result = _guard_readonly_sql(
                sql,
                dialect=dialect,
                query_constraints=query_constraints,
                allowed_tables=allowed_tables,
            )
            if not guard_result.ok:
                logger.error("真实Schema模式: SQL Guard 拦截: %s", guard_result.error)
                return _attach_sql_retry_failure(
                    state,
                    {
                    "sql": None,
                    "error": guard_result.error,
                    "sql_guard": guard_result.__dict__,
                    "should_retry": False,
                    },
                    result="自动修复后的 SQL 未通过安全校验",
                )
            sql = guard_result.normalized_sql or sql
            logger.info("真实Schema模式: 编译成功")
            return {
                "sql": sql,
                "sql_list": [sql],
                "error": None,
                "sql_guard": guard_result.__dict__,
            }

        if not dsl:
            logger.error("DSL为空，无法编译")
            return _attach_sql_retry_failure(
                state,
                {"sql": None, "error": "DSL 为空，无法编译"},
                result="自动修复未生成有效 DSL",
            )

        # ── 优先使用结构化对象 ──
        if structured:
            metric_map = {m["name"]: m for m in structured.get("metrics", [])}
            dim_map = {d["name"]: d for d in structured.get("dimensions", [])}
            field_map = {f["name"]: f for f in structured.get("fields", [])}
            tables_json = structured.get("tables_json") or {}
        else:
            # fallback: 从文本正则解析（兼容旧逻辑）
            metric_map = {}
            for line in schema.split("\n"):
                m = re.match(
                    r"-\s+(\w+)\s+\([^)]+\):\s+表达式=(.+?)(?:\s+同义词=|\s+过滤=|$)", line
                )
                if m:
                    metric_map[m.group(1)] = {"expr": m.group(2).strip()}
            dim_map = {}
            field_map = {}
            tables_json_match = re.search(r"tables_json[:=]\s*(\{.*\})", schema, re.DOTALL)
            tables_json = json.loads(tables_json_match.group(1)) if tables_json_match else {}

        # ── 构建 SELECT ──
        selects = []
        used_tables = {}  # alias -> table_name

        # 明细查询标志：无 metrics 但有 dimensions/fields，不做聚合、不加 GROUP BY
        _dsl_metric_names = _dsl_item_names(dsl.get("metrics", []))
        _dsl_field_names = _dsl_item_names(dsl.get("fields", []))
        _dsl_dim_names = _dsl_item_names(dsl.get("dimensions", []))
        is_detail_query = (not _dsl_metric_names) and bool(_dsl_field_names or _dsl_dim_names)

        for m_name in _dsl_metric_names:
            m = metric_map.get(m_name)
            if m:
                expr = m.get("expr", m_name)
                selects.append(f"{expr} AS {m_name}")
                tbl = m.get("table_name")
                if tbl:
                    used_tables[tbl] = tbl
            else:
                # fallback：查 field_map，利用 default_agg 自动聚合
                fld = field_map.get(m_name)
                if fld:
                    col = fld.get("column_name", m_name)
                    tbl = fld.get("table_name")
                    agg = (fld.get("default_agg") or "").upper()
                    if tbl:
                        used_tables[tbl] = tbl
                    col_expr = (
                        f"{_quote_ident(tbl, dialect)}.{_quote_ident(col, dialect)}"
                        if tbl
                        else (_quote_ident(col, dialect) or col)
                    )
                    if agg and agg != "NONE":
                        selects.append(f"{agg}({col_expr}) AS {m_name}")
                    else:
                        selects.append(f"{col_expr} AS {m_name}")
                else:
                    selects.append(f"{m_name} AS {m_name}")

        for d_name in _dsl_dim_names:
            d = dim_map.get(d_name)
            if d:
                col = d.get("column_name", d_name)
                tbl = d.get("table_name")
                if tbl:
                    used_tables[tbl] = tbl
                    selects.append(
                        f"{_quote_ident(tbl, dialect)}.{_quote_ident(col, dialect)} AS {d_name}"
                    )
                else:
                    selects.append(f"{_quote_ident(col, dialect)} AS {d_name}")
            else:
                # fallback：查 field_map 获取 table 限定符
                fld = field_map.get(d_name)
                if fld:
                    col = fld.get("column_name", d_name)
                    tbl = fld.get("table_name")
                    if tbl:
                        used_tables[tbl] = tbl
                        selects.append(
                            f"{_quote_ident(tbl, dialect)}.{_quote_ident(col, dialect)} AS {d_name}"
                        )
                    else:
                        selects.append(f"{_quote_ident(col, dialect)} AS {d_name}")
                else:
                    selects.append(d_name)

        # fields 列表（明细查询场景：不聚合，直接取原始列值）
        for f_name in _dsl_field_names:
            fld = field_map.get(f_name)
            if fld:
                col = fld.get("column_name", f_name)
                tbl = fld.get("table_name")
                if tbl:
                    used_tables[tbl] = tbl
                    selects.append(
                        f"{_quote_ident(tbl, dialect)}.{_quote_ident(col, dialect)} AS {f_name}"
                    )
                else:
                    selects.append(f"{_quote_ident(col, dialect)} AS {f_name}")
            else:
                selects.append(f_name)

        # ── 构建 FROM + JOIN ──
        tables_def = tables_json.get("tables", [])
        joins_def = tables_json.get("joins", [])

        # 确定主表（第一个指标的 table_name 或 tables_json 的第一个表）
        primary_table = None
        primary_alias = None
        if tables_def:
            primary_table = tables_def[0].get("name")
            # 注意：alias 可能是空字符串/None，统一回退到 primary_table
            primary_alias = tables_def[0].get("alias") or primary_table
        elif dsl.get("metrics"):
            first_metric_name = _dsl_item_names(dsl.get("metrics", []))[0]
            first_metric = metric_map.get(first_metric_name)
            if first_metric:
                primary_table = first_metric.get("table_name")
        if not primary_table and used_tables:
            primary_table = next(iter(used_tables.values()))
            primary_alias = primary_table
        if not primary_table:
            # 兜底：实在找不到就别用假名 "orders"，直接报错让上层重试
            logger.error("DSL编译: 无法确定主表（tables_json 为空且指标未指定 table_name）")
            error_text = "无法确定主表，请在数据集配置中维护 tables_json 或为指标指定 table_name"
            return _attach_sql_retry_failure(
                state,
                {"sql": None, "error": error_text},
                result="自动修复仍无法确定主表",
            )

        # 主表 FROM：仅在 alias 与表名不同（且有效）时输出 AS 子句
        if primary_alias and primary_alias != primary_table:
            from_parts = [
                f"{_quote_ident(primary_table, dialect)} AS {_quote_ident(primary_alias, dialect)}"
            ]
        else:
            from_parts = [_quote_ident(primary_table, dialect) or primary_table]

        # 构建 JOIN
        joined_tables = {primary_alias or primary_table}
        for j in joins_def:
            left = j.get("left_table")
            right = j.get("right_table")
            left_key = j.get("left_key")
            right_key = j.get("right_key")
            join_type = j.get("type", "LEFT JOIN")
            alias = j.get("alias") or right
            # 只有当右侧表被使用时才 JOIN
            if (
                right in used_tables
                or any(d.get("table_name") == right for d in dim_map.values())
                or any(f.get("table_name") == right for f in field_map.values())
            ):
                if alias not in joined_tables:
                    from_parts.append(
                        f"{join_type} {_quote_ident(right, dialect)} AS {_quote_ident(alias, dialect)} "
                        f"ON {_quote_ident(left, dialect)}.{_quote_ident(left_key, dialect)} = "
                        f"{_quote_ident(alias, dialect)}.{_quote_ident(right_key, dialect)}"
                    )
                    joined_tables.add(alias)

        # ── 构建 WHERE ──
        wheres = []

        # 指标内置过滤条件（先 sanitize，!= null → IS NOT NULL）
        for m_name in _dsl_item_names(dsl.get("metrics", [])):
            m = metric_map.get(m_name)
            if m and m.get("filter_sql"):
                wheres.append(f"({_sanitize_filter_sql(m['filter_sql'])})")

        # DSL 中的 filters
        for f in dsl.get("filters", []):
            field = _dsl_field_name(f["field"])
            op = f["op"]
            vals = f.get("values", [])
            dim = dim_map.get(field)
            if dim and dim.get("table_name"):
                field = f"{_quote_ident(dim['table_name'], dialect)}.{_quote_ident(dim['column_name'], dialect)}"
            else:
                fld = field_map.get(field)
                if fld and fld.get("table_name"):
                    field = f"{_quote_ident(fld['table_name'], dialect)}.{_quote_ident(fld['column_name'], dialect)}"
                else:
                    field = _quote_ident(field, dialect) or field
            if op == "in" and vals:
                in_list = ", ".join(["'" + str(v) + "'" for v in vals])
                wheres.append(f"{field} IN ({in_list})")
            elif op == "eq" and vals:
                wheres.append(f"{field} = '{vals[0]}'")
            elif op == "gt" and vals:
                wheres.append(f"{field} > '{vals[0]}'")
            elif op == "gte" and vals:
                wheres.append(f"{field} >= '{vals[0]}'")
            elif op == "lt" and vals:
                wheres.append(f"{field} < '{vals[0]}'")
            elif op == "lte" and vals:
                wheres.append(f"{field} <= '{vals[0]}'")
            elif op == "neq" and vals:
                wheres.append(f"{field} <> '{vals[0]}'")
            elif op == "between" and len(vals) >= 2:
                wheres.append(f"{field} BETWEEN '{vals[0]}' AND '{vals[1]}'")

        # 时间范围：优先使用第一个指标关联的 time_field
        tr = dsl.get("time_range")
        # 收集所有已知合法 time_field：避免 LLM 在 time_range.field 里瞎填 DDL 列名
        valid_time_fields = {
            m.get("time_field") for m in metric_map.values() if m.get("time_field")
        }
        tr_field = _dsl_field_name(tr.get("field")) if isinstance(tr, dict) else None
        # LLM 填了不合法的时间字段 → 强制回退到第一个 metric 的 time_field
        if tr_field and tr_field not in valid_time_fields and dsl.get("metrics"):
            first_metric_name = _dsl_item_names(dsl.get("metrics", []))[0]
            first_metric = metric_map.get(first_metric_name)
            if first_metric and first_metric.get("time_field"):
                logger.warning(
                    f"DSL time_range.field='{tr_field}' 不在已声明的 time_field {valid_time_fields} 中，"
                    f"强制覆盖为 '{first_metric['time_field']}'"
                )
                tr_field = first_metric["time_field"]

        if tr_field:
            time_field = _quote_ident(tr_field, dialect) or tr_field
            if tr.get("start"):
                wheres.append(f"{time_field} >= '{tr['start']}'")
            if tr.get("end"):
                wheres.append(f"{time_field} <= '{tr['end']}'")
        elif dsl.get("metrics") and query_constraints.get("enabled"):
            # 仅在 query_constraints 启用时才自动追加默认时间范围
            first_metric_name = _dsl_item_names(dsl.get("metrics", []))[0]
            first_metric = metric_map.get(first_metric_name)
            if first_metric and first_metric.get("time_field"):
                tf = _quote_ident(first_metric["time_field"], dialect) or first_metric["time_field"]
                import datetime

                days = query_constraints.get("default_time_range_days", 30)
                end = datetime.date.today().isoformat()
                start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
                wheres.append(f"{tf} >= '{start}'")
                wheres.append(f"{tf} <= '{end}'")

        # ── 组装 SQL ──
        sql_parts = [f"SELECT {', '.join(selects)}"]
        sql_parts.append(f"FROM {' '.join(from_parts)}")

        if wheres:
            sql_parts.append("WHERE " + " AND ".join(wheres))

        dims = _dsl_item_names(dsl.get("dimensions", []))
        if dims and not is_detail_query:
            group_cols = []
            for d_name in dims:
                d = dim_map.get(d_name)
                if d and d.get("table_name"):
                    group_cols.append(
                        f"{_quote_ident(d['table_name'], dialect)}.{_quote_ident(d['column_name'], dialect)}"
                    )
                else:
                    fld = field_map.get(d_name)
                    if fld and fld.get("table_name"):
                        group_cols.append(
                            f"{_quote_ident(fld['table_name'], dialect)}.{_quote_ident(fld['column_name'], dialect)}"
                        )
                    else:
                        group_cols.append(_quote_ident(d_name, dialect) or d_name)
            sql_parts.append(f"GROUP BY {', '.join(group_cols)}")

        ob = dsl.get("order_by", [])
        if ob:
            orders = [
                f"{_quote_ident(_dsl_field_name(o['field']), dialect) or _dsl_field_name(o['field'])} {o['direction']}"
                for o in ob
            ]
            sql_parts.append(f"ORDER BY {', '.join(orders)}")

        limit = dsl.get("limit")
        if limit in (None, "") and query_constraints["enabled"]:
            limit = query_constraints["default_limit"]
        if limit not in (None, ""):
            try:
                limit = min(int(limit), query_constraints["max_limit"])
            except (TypeError, ValueError):
                limit = query_constraints["default_limit"]
            if str(dialect).lower() == "oracle":
                sql_parts.append(f"FETCH FIRST {limit} ROWS ONLY")
            elif str(dialect).lower() in {"tsql", "sqlserver", "mssql"}:
                # SQL Server TOP 由 SQL Guard/SQLGlot 统一补齐，避免手写破坏 SELECT 列表。
                pass
            else:
                sql_parts.append(f"LIMIT {limit}")
        sql = "\n".join(sql_parts)

        guard_result = _guard_readonly_sql(
            sql,
            dialect=dialect,
            query_constraints=query_constraints,
            allowed_tables=allowed_tables,
        )
        if not guard_result.ok:
            logger.error("DSL编译: SQL Guard 拦截: %s", guard_result.error)
            return _attach_sql_retry_failure(
                state,
                {
                "sql": None,
                "error": guard_result.error,
                "sql_guard": guard_result.__dict__,
                "should_retry": False,
                },
                result="自动修复后的 SQL 未通过安全校验",
            )
        sql = guard_result.normalized_sql or sql

        logger.info(f"DSL编译成功 (dialect={dialect}): {sql}")
        return {
            "sql": sql,
            "sql_list": [sql],
            "error": None,
            "sql_guard": guard_result.__dict__,
        }

    return _node


# ── 节点 6: SQL 执行 ──────────────────────────────────


def sql_execute_node(db: Session):
    """执行 SQL 查询（只读），连接真实数据源返回结果集。"""

    def _node(state: AgentState) -> Dict[str, Any]:
        sql = state.get("sql")
        logger.info(f"SQL执行节点开始: sql={sql[:80]}..." if sql else "SQL执行节点开始: SQL为空")
        if not sql:
            upstream_error = state.get("error")
            if upstream_error:
                logger.warning("SQL为空，保留上游错误: %s", upstream_error)
                output = {
                    "sql_result": None,
                    "error": upstream_error,
                    "should_retry": bool(state.get("should_retry")),
                    "sql_guard": state.get("sql_guard"),
                }
                output["out_capsule"] = build_out_capsule(state, output)
                return output
            logger.warning("SQL为空，跳过执行")
            output = {"sql_result": None, "error": "SQL 为空", "should_retry": True}
            output["out_capsule"] = build_out_capsule(state, output)
            return output

        dataset_id = state.get("dataset_id")
        datasource_context = state.get("datasource_context") or {}
        datasource = None
        if dataset_id:
            dataset = db.get(SemanticDataset, dataset_id)
            if dataset:
                datasource = db.get(Datasource, dataset.datasource_id)

        if not datasource:
            logger.error("无可用数据源")
            output = {
                "sql_result": None,
                "error": "当前问数未绑定可执行数据集或数据源，请先选择数据集并测试连接",
                "should_retry": False,
            }
            output["out_capsule"] = build_out_capsule(state, output)
            return output

        dialect = datasource_context.get("dialect") or (getattr(datasource, "dialect", None) or getattr(datasource, "db_type", None) or "postgres").lower()
        guard_result = _guard_readonly_sql(
            sql,
            dialect=dialect,
            query_constraints=state.get("query_constraints"),
            allowed_tables=datasource_context.get("allowed_tables") or [],
        )
        if not guard_result.ok:
            logger.error("SQL执行: SQL Guard 拦截: %s", guard_result.error)
            output = {
                "sql_result": None,
                "error": guard_result.error,
                "sql_guard": guard_result.__dict__,
                "should_retry": False,
            }
            output["out_capsule"] = build_out_capsule(state, output)
            return output
        sql = guard_result.normalized_sql or sql

        engine = create_engine_for_datasource(datasource)
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                result_proxy = conn.execute(text(sql))
                columns = list(result_proxy.keys())
                rows = []
                for row in result_proxy:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if hasattr(val, "isoformat"):
                            row_dict[col] = val.isoformat()
                        elif isinstance(val, Decimal):
                            row_dict[col] = float(val)
                        else:
                            row_dict[col] = val
                    rows.append(row_dict)
                result = {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "column_labels": _build_column_labels(db, dataset_id),
                }
                logger.info(f"SQL执行成功: 返回 {len(rows)} 行")
                output = {
                    "sql_result": result,
                    "error": None,
                    "should_retry": False,
                    "datasource_dialect": dialect,
                }
                retry_trace = _finish_latest_sql_retry_trace(
                    state,
                    status="success",
                    result=f"自动修复后执行成功，返回 {len(rows)} 行",
                    repaired_sql=sql,
                    row_count=len(rows),
                )
                if retry_trace is not None:
                    output["sql_retry_trace"] = retry_trace
                output["out_capsule"] = build_out_capsule(state, output)
                return jsonable_encoder(output)
        except Exception as e:
            logger.error(f"SQL执行失败: {e}")
            error_text = f"SQL 执行失败: {str(e)}"
            output = {
                "sql_result": None,
                "error": error_text,
                "should_retry": True,
                "datasource_dialect": dialect,
            }
            retry_trace = _finish_latest_sql_retry_trace(
                state,
                status="failed",
                result="自动修复后执行仍失败",
                repaired_sql=sql,
                error=error_text,
            )
            if retry_trace is not None:
                output["sql_retry_trace"] = retry_trace
            output["out_capsule"] = build_out_capsule(state, output)
            return jsonable_encoder(output)
        finally:
            engine.dispose()

    return _node


# ── 节点 6.5: SQL 审计（Agent 校验）──────────────────────────
# SQL 执行失败后接管：调用 LLM 审计错误，输出结构化诊断 JSON
# - fixable: 改写 error 字段，走原重试链
# - architectural: 直接 END（建议用户修数据集，不再烧 token）

def _collect_audit_table_names(dsl: dict, structured: dict | None, sql: str | None) -> list[str]:
    """收集 SQL 审计需要的表名列表。

    优先级：
    1. dsl["metrics"] 在 schema_structured.metric_map 里的 table_name
    2. SQL 文本里 FROM 后的表名（直接 SQL 路径兜底）
    """
    names: list[str] = []
    seen: set[str] = set()

    if dsl and structured:
        metric_map = {m["name"]: m for m in structured.get("metrics", [])}
        for m_name in _dsl_item_names(dsl.get("metrics", [])):
            m = metric_map.get(m_name)
            if not m:
                continue
            tbl = m.get("table_name")
            if tbl and tbl not in seen:
                names.append(tbl)
                seen.add(tbl)

    if not names and sql:
        # 兜底：直接从 SQL 抓 FROM <table>
        m = re.search(
            r"\bFROM\s+[`\"\[]?(\w+)[`\"\]]?",
            sql,
            re.IGNORECASE,
        )
        if m and m.group(1) not in seen:
            names.append(m.group(1))

    return names


def _write_sql_diagnosis_log(db: Session, state: AgentState, diagnosis: dict[str, Any]) -> None:
    """best-effort 写入 SQL 诊断日志，失败不影响主问数流程。"""
    try:
        db.add(
            SQLDiagnosisLog(
                conversation_id=state.get("conversation_id"),
                dataset_id=state.get("dataset_id"),
                question=state.get("question"),
                sql=state.get("sql"),
                error=state.get("error"),
                diagnosis=diagnosis,
                retry_count=state.get("retry_count", 0),
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("SQL诊断日志写入失败，已忽略: %s", exc)


def _format_sql_diagnosis_error(diagnosis: dict[str, Any], original_error: str) -> str:
    """把结构化诊断转换成重试和最终回答可读的错误文本。"""
    title = diagnosis.get("title") or "SQL 执行失败"
    detail = diagnosis.get("detail") or diagnosis.get("root_cause") or original_error
    suggested = diagnosis.get("suggested_action") or diagnosis.get("suggested_fix")
    parts = [f"SQL 执行失败诊断：{title}。{detail}"]
    if suggested:
        parts.append(f"建议：{suggested}")
    if original_error:
        parts.append(f"原始错误：{original_error}")
    return "。".join(part.rstrip("。") for part in parts if part)


def sql_audit_node(db: Session):
    """SQL 审计 Agent 节点。SQL 执行失败时被路由到这里。
    调 LLM（temperature=0）输出结构化诊断 JSON，区分 fixable / architectural。

    Args:
        db: SQLAlchemy Session（用于查 datasource / sample data）
    """

    def _node(state: AgentState) -> Dict[str, Any]:
        logger.info("SQL审计节点开始")
        question = state.get("question", "")
        dsl = state.get("dsl") or {}
        sql = state.get("sql")
        original_error = state.get("error", "") or ""
        schema_context = state.get("schema_context", "") or ""
        ddl_context = state.get("ddl_context", "") or ""
        structured = state.get("schema_structured")
        metric_resolution = state.get("metric_resolution") or {}
        term_normalization = state.get("term_normalization") or {}
        semantic_asset_resolution = state.get("semantic_asset_resolution") or {}
        dataset_id = state.get("dataset_id")
        retry_count = state.get("retry_count", 0)
        max_retry = state.get("max_retry_count", _sql_max_retry_count())
        datasource_context = state.get("datasource_context") or {}
        datasource_dialect = state.get("datasource_dialect") or datasource_context.get("dialect")

        # 解析 datasource（sample data 查询需要）
        datasource = None
        if dataset_id:
            ds = db.get(SemanticDataset, dataset_id)
            if ds:
                datasource = db.get(Datasource, ds.datasource_id)
        if datasource_dialect is None and datasource is not None:
            datasource_dialect = (
                getattr(datasource, "dialect", None)
                or getattr(datasource, "db_type", None)
                or ""
            ).lower() or None

        # 收集审计相关的表名
        table_names = _collect_audit_table_names(dsl, structured, sql)

        # 拉样例数据（best-effort；失败不阻塞审计）
        sample_text = ""
        if table_names and datasource is not None:
            try:
                sample_text = _fetch_sample_rows(
                    db, table_names, per_table=2, datasource=datasource
                )
            except Exception as e:
                logger.warning(f"SQL审计: 样例数据查询失败: {e}")

        # DDL 上下文：ddl_context 优先，schema_context 兜底（直接 SQL 路径无 ddl_context）
        ddl_block = ddl_context if ddl_context else schema_context
        # 限制长度，避免 prompt 爆炸
        if len(ddl_block) > 6000:
            ddl_block = ddl_block[:6000] + "\n...（DDL 截断）"

        base_diagnosis = _classify_sql_execution_error(
            error=original_error,
            sql=sql,
            ddl_context=ddl_block,
            schema_structured=structured,
            datasource_dialect=datasource_dialect,
            retry_count=retry_count,
        )

        # 调 LLM（审计是确定性判断，temperature=0）
        llm = get_llm(temperature=0.0, role="sql_audit", db=db)
        sql_audit_prompt = get_prompt_manager().get_text_prompt(
            "sql_audit",
            fallback=SQL_AUDIT_SYSTEM,
        )
        system = SystemMessage(content=sql_audit_prompt.content)

        human_lines = [
            "【当前任务】",
            f"问题: {question}",
            f"DSL: {json.dumps(dsl, ensure_ascii=False) if dsl else '（无）'}",
            f"SQL: {sql or '（空）'}",
            f"错误: {original_error}",
            f"确定性诊断: {json.dumps(base_diagnosis, ensure_ascii=False)}",
        ]
        if schema_context:
            human_lines.append("")
            human_lines.append("【语义层 / Schema】")
            human_lines.append(schema_context[:4000])
        if ddl_block:
            human_lines.append("")
            human_lines.append("【所选表 DDL】")
            human_lines.append(ddl_block)
        if sample_text:
            human_lines.append("")
            human_lines.append(sample_text)
        if metric_resolution:
            human_lines.append("")
            human_lines.append("【指标解析】")
            human_lines.append(json.dumps(metric_resolution, ensure_ascii=False)[:1500])
        if term_normalization:
            human_lines.append("")
            human_lines.append("【业务术语归一化】")
            human_lines.append(json.dumps(term_normalization, ensure_ascii=False)[:1500])
        if semantic_asset_resolution:
            human_lines.append("")
            human_lines.append("【语义资产解析】")
            human_lines.append(json.dumps(semantic_asset_resolution, ensure_ascii=False)[:2000])

        human = HumanMessage(content="\n".join(human_lines))

        response = None
        result: dict[str, Any] = {}
        try:
            response, llm_err = _safe_llm_invoke(llm, [system, human], path="sql_audit")
            if llm_err:
                raise RuntimeError(llm_err)
            result = _safe_json_parse(str(response.content))
        except Exception as e:
            logger.error("SQL审计: LLM 调用失败，使用确定性诊断兜底: %s", e)
            result = {}

        diagnosis = _merge_llm_sql_diagnosis(base_diagnosis, result)
        retryable = bool(diagnosis.get("retryable"))
        will_retry = retryable and retry_count < max_retry
        diagnosis["retry_decision"] = {
            "will_retry": will_retry,
            "retry_count": retry_count,
            "max_retry_count": max_retry,
            "reason": (
                "诊断为可自动修复，进入下一轮 SQL 生成"
                if will_retry
                else (
                    "已达到自动修复重试上限"
                    if retryable
                    else "诊断为不可自动修复，终止重试"
                )
            ),
        }
        audit = dict(diagnosis)
        logger.info(
            "SQL审计完成: code=%s severity=%s retryable=%s root_cause=%r",
            diagnosis.get("code"),
            diagnosis.get("severity"),
            diagnosis.get("retryable"),
            diagnosis.get("root_cause"),
        )

        # token 计量
        merged = state.get("token_usage")
        if response is not None:
            usage = _extract_token_usage(response, [system, human])
            merged = _merge_token_usage(state.get("token_usage") or {}, usage)

        _write_sql_diagnosis_log(db, state, diagnosis)

        friendly_error = _format_sql_diagnosis_error(diagnosis, original_error)
        retry_trace = _sql_retry_trace(state)
        if will_retry:
            retry_trace = _start_sql_retry_trace(
                state,
                diagnosis,
                original_error=original_error,
            )
        elif retryable:
            friendly_error = (
                f"{friendly_error}。已达到自动修复重试上限（{max_retry} 次），"
                "无法继续安全重试。"
            )

        return {
            "sql_audit_result": audit,
            "sql_diagnosis": diagnosis,
            "should_retry": will_retry,
            "error": friendly_error,
            "sql_retry_trace": retry_trace,
            "token_usage": merged,
        }

    return _node


# ── 节点 7: 报告生成 ──────────────────────────────────


async def report_generator_node(
    state: AgentState,
    db: Session | None = None,
) -> Dict[str, Any]:
    """根据 SQL 结果生成自然语言回答和图表推荐。
    使用 astream() 实现真正的 token 级流式，供 astream_events 捕获。"""
    logger.info("报告生成节点开始")
    result = await generate_sql_result_report(
        state,
        db=db,
        observation_name="llm.report_generator",
        report_owner="subagent",
    )
    result["out_capsule"] = build_out_capsule(state, result)
    logger.info("报告生成完成")
    return result
