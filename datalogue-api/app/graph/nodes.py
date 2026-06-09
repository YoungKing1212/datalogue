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

import json
import re
from decimal import Decimal
from typing import Dict, Any

import logging
from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage

from app.graph.llm import get_llm
from app.graph.state import AgentState
from app.schemas.dsl import get_dsl_item_name, normalize_dsl
from app.prompts.intent_router import INTENT_RECOGNITION_SYSTEM
from app.prompts.dsl_generate import (
    build_real_schema_system,
    build_inferred_system,
    build_semantic_system,
    build_no_schema_system,
)
from app.prompts.sql_audit import SQL_AUDIT_SYSTEM
from app.prompts.report_generate import build_report_system
from app.models.dataset import (
    AnalysisBlueprint,
    BusinessTerm,
    SemanticDataset,
)
from app.models.conversation import SQLDiagnosisLog
from app.models.datasource import Datasource
from app.services.analysis_blueprint import execute_analysis_blueprint
from app.services.dataset_context import build_dataset_query_context
from app.services.datasource import create_engine_for_datasource
from app.utils.query_constraints import (
    normalize_query_constraints,
    render_query_constraints_instruction,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_SQL_RETRY_COUNT = 3

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
    try:
        return llm.invoke(messages), None
    except Exception as e:
        err_str = str(e)
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
    max_retry = state.get("max_retry_count", DEFAULT_MAX_SQL_RETRY_COUNT)
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
    if bp.trigger_keywords:
        lines.append(f"触发词: {'、'.join(str(t) for t in bp.trigger_keywords if t)}")
    if bp.trigger_examples:
        lines.append("用户可能问法:")
        lines.extend(_format_blueprint_list(bp.trigger_examples))
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
    if bp.attribution_hints:
        lines.append(f"归因和解释提示: {bp.attribution_hints}")
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


def _format_dsl_asset_catalog(structured: dict | None) -> str:
    """把结构化语义层资产整理成 NL2DSL v2 可引用目录。"""
    if not structured:
        return ""
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
        lines.append(f"{title}:")
        for item in items:
            aliases = item.get("synonyms") or item.get("aliases") or []
            if asset_type == "field":
                aliases = _field_aliases(item)
            alias_text = f"，同义词={aliases}" if aliases else ""
            lines.append(
                "- "
                f"asset_type={asset_type}, asset_id={item.get('id')}, "
                f"name={item.get('name')}, display_name={item.get('display_name') or item.get('name')}"
                f"{alias_text}"
            )
    return "\n".join(lines) if len(lines) > 1 else ""


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


def intent_recognition_node(state: AgentState) -> Dict[str, Any]:
    """识别用户意图，判断是数据查询、闲聊还是功能操作。"""
    question = state["question"]
    logger.info(f"意图识别节点开始: question={question[:50]}...")
    history = state.get("history", [])
    llm = get_llm(temperature=0.0)

    system = SystemMessage(content=INTENT_RECOGNITION_SYSTEM)

    human_text = question
    if history and len(history) > 1:
        recent = history[-6:-1] if len(history) > 6 else history[:-1]
        ctx = "\n".join(
            [f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:100]}" for m in recent]
        )
        human_text = f"【历史上下文】\n{ctx}\n\n【当前问题】\n{question}"

    human = HumanMessage(content=human_text)
    response = llm.invoke([system, human])
    result = _safe_json_parse(str(response.content))

    intent = result.get("intent", "query")
    entities = result.get("entities", {})
    direct_answer = result.get("direct_answer")

    answer = direct_answer if intent == "chitchat" else None
    logger.info(f"意图识别结果: intent={intent}")
    usage = _extract_token_usage(response)
    current_usage = state.get("token_usage") or {}
    merged = _merge_token_usage(current_usage, usage)

    return {
        "intent": intent,
        "entities": entities,
        "answer": answer,
        "token_usage": merged,
    }


def entry_intent_classification_node(db: Session):
    """构建 QueryGraph 前置入口分类节点。

    该节点只负责路由决策，不执行蓝图或知识库查询；非普通问数场景会写入
    `answer` 和 `route_payload`，由工作流直接结束并交给 API 层透出。
    """

    def _node(state: AgentState) -> Dict[str, Any]:
        question = state.get("question") or ""
        q_norm = _normalized_text(question)
        intent = state.get("intent") or "query"
        entities = state.get("entities") or {}
        dataset_id = state.get("dataset_id")
        logger.info("入口意图分类开始: intent=%s, dataset_id=%s", intent, dataset_id)

        if intent == "chitchat":
            return {
                "entry_intent": "chitchat",
                "entry_route": "direct_answer",
                "entry_reason": "粗粒度意图识别为闲聊，直接返回回答。",
                "route_payload": {"kind": "direct_answer"},
            }

        if intent == "function":
            answer = (
                "当前问数入口只处理数据查询、分析蓝图和知识解释，"
                "暂不直接执行保存、发布或导出类操作。"
            )
            return {
                "entry_intent": "rejection",
                "entry_route": "reject",
                "entry_reason": "功能操作不应进入 QueryGraph。",
                "answer": answer,
                "route_payload": {"kind": "unsupported_function"},
            }

        if _contains_any(q_norm, _PERMISSION_PATTERNS):
            answer = (
                "这个问题涉及权限不足或未授权资源，我不能绕过权限继续查询。"
                "请先确认数据集、数据源或知识库授权后再重试。"
            )
            return {
                "entry_intent": "rejection",
                "entry_route": "reject",
                "entry_reason": "用户输入命中权限不足/未授权语义。",
                "answer": answer,
                "route_payload": {"kind": "permission_denied"},
            }

        blueprint_match = _match_analysis_blueprint(db, dataset_id, question)
        if blueprint_match:
            answer = (
                f"已命中分析蓝图「{blueprint_match['name']}」，"
                "将按固定分析逻辑处理。"
            )
            return {
                "entry_intent": "analysis_blueprint",
                "entry_route": "analysis_blueprint",
                "entry_reason": (
                    "问题命中已发布分析蓝图的关键词、示例或使用说明。"
                ),
                "blueprint_id": blueprint_match["blueprint_id"],
                "blueprint_match": blueprint_match,
                "answer": answer,
                "route_payload": {"kind": "analysis_blueprint", **blueprint_match},
            }

        is_knowledge_question = _contains_any(q_norm, _KNOWLEDGE_PATTERNS)
        if is_knowledge_question:
            term_match = _match_business_term(db, dataset_id, question)
            answer = (
                "我识别到这是知识解释类问题，"
                "但还需要更具体的业务术语或可用知识库内容才能回答。"
            )
            payload: dict[str, Any] = {"kind": "knowledge_qa"}
            term_id = None
            if term_match:
                term_id = term_match["term_id"]
                payload.update(term_match)
                if term_match.get("definition"):
                    answer = f"{term_match['name']}：{term_match['definition']}"
                else:
                    answer = (
                        f"已识别业务术语「{term_match['name']}」，"
                        "但知识库中还没有维护定义。"
                    )
            return {
                "entry_intent": "knowledge_qa",
                "entry_route": "knowledge_qa",
                "entry_reason": "问题命中定义、口径、解释等知识库问答语义。",
                "knowledge_term_id": term_id,
                "answer": answer,
                "route_payload": payload,
            }

        has_metric_entity = bool(entities.get("metrics"))
        has_dimension_entity = bool(entities.get("dimensions"))
        is_detail_query = _contains_any(q_norm, _DETAIL_PATTERNS)
        is_metric_query = has_metric_entity or _contains_any(q_norm, _METRIC_PATTERNS)
        is_blueprint_like = _contains_any(q_norm, _BLUEPRINT_PATTERNS)
        is_short_ambiguous = len(q_norm) <= 4 and _contains_any(q_norm, _AMBIGUOUS_PATTERNS)

        if is_blueprint_like and not is_metric_query and not is_detail_query:
            answer = (
                "这个问题更像固定分析诉求，但当前没有命中可用分析蓝图。"
                "请补充要分析的主题、指标或选择具体蓝图。"
            )
            return {
                "entry_intent": "clarification",
                "entry_route": "clarify",
                "entry_reason": "复杂固定分析语义未命中已发布蓝图，进入澄清。",
                "answer": answer,
                "route_payload": {"kind": "clarification", "missing": ["blueprint_or_metrics"]},
            }

        if is_short_ambiguous:
            answer = (
                "这个问题缺少明确对象。"
                "请补充要查询的指标、维度、时间范围或业务术语。"
            )
            return {
                "entry_intent": "clarification",
                "entry_route": "clarify",
                "entry_reason": "短句或指代不清，无法可靠判断查询目标。",
                "answer": answer,
                "route_payload": {"kind": "clarification", "missing": ["query_target"]},
            }

        if is_detail_query:
            return {
                "entry_intent": "detail_query",
                "entry_route": "query_graph",
                "entry_reason": "问题命中明细/列表类查询语义，继续 NL2SQL。",
                "route_payload": {"kind": "detail_query"},
            }

        if is_metric_query or has_dimension_entity:
            return {
                "entry_intent": "metric_query",
                "entry_route": "query_graph",
                "entry_reason": "问题命中指标/统计类查询语义，继续 NL2SQL。",
                "route_payload": {"kind": "metric_query"},
            }

        answer = (
            "我还无法确定你想查询数据、运行分析蓝图，还是询问业务知识。"
            "请补充查询对象或说明要分析的问题。"
        )
        return {
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "未命中普通问数、蓝图、知识库或拒答规则。",
            "answer": answer,
            "route_payload": {"kind": "clarification", "missing": ["intent"]},
        }

    return _node


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
            return {
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
            }

        result = execute_analysis_blueprint(
            db,
            bp,
            question=question,
            require_active=True,
            count_usage=True,
        )
        if not result.get("ok"):
            missing = result.get("missing") or []
            answer = result.get("error") or "分析蓝图执行失败"
            route_payload = {
                "kind": "clarification" if missing else "analysis_blueprint_error",
                "blueprint_id": bp.id,
                "params": result.get("params") or {},
            }
            if missing:
                route_payload["missing"] = missing
            return {
                "sql_result": None,
                "sql": result.get("sql"),
                "sql_list": [result["sql"]] if result.get("sql") else [],
                "error": answer,
                "answer": answer,
                "route_payload": {
                    **route_payload,
                },
                "should_retry": False,
            }

        return {
            "sql": result["sql"],
            "sql_list": [result["sql"]],
            "sql_result": result["sql_result"],
            "generation_mode": "analysis_blueprint",
            "error": None,
            "should_retry": False,
            "route_payload": {
                "kind": "analysis_blueprint",
                "blueprint_id": bp.id,
                "name": bp.name,
                "params": result["params"],
                "execution_time_ms": result["execution_time_ms"],
            },
        }

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


# ── 节点 2.5: 业务术语归一化（Term Normalize）────────────────


def _term_match_candidates(term: dict) -> list[tuple[str, str]]:
    """返回业务术语可匹配词，包含标准名、展示名和同义词。"""
    candidates: list[tuple[str, str]] = []
    if term.get("name"):
        candidates.append((str(term["name"]), "exact"))
    if term.get("display_name") and term.get("display_name") != term.get("name"):
        candidates.append((str(term["display_name"]), "display_name"))
    for alias in _coerce_text_list(term.get("aliases")):
        candidates.append((alias, "synonym"))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token, match_type in candidates:
        norm = _semantic_match_text(token)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append((token, match_type))
    return deduped


def _match_term_in_question(term: dict, question: str) -> dict | None:
    """在用户问题中匹配一个业务术语。"""
    q_norm = _semantic_match_text(question)
    if not q_norm:
        return None

    best: dict | None = None
    for token, match_type in _term_match_candidates(term):
        token_norm = _semantic_match_text(token)
        if not token_norm:
            continue
        confidence = 0.0
        if token_norm == q_norm:
            confidence = {"exact": 0.97, "display_name": 0.95, "synonym": 0.9}.get(
                match_type, 0.88
            )
        elif len(token_norm) >= 2 and token_norm in q_norm:
            confidence = {"exact": 0.9, "display_name": 0.88, "synonym": 0.84}.get(
                match_type, 0.8
            )
        if confidence <= 0:
            continue
        candidate = {
            "term_id": term.get("id"),
            "name": term.get("name"),
            "display_name": term.get("display_name") or term.get("name"),
            "term_type": term.get("term_type"),
            "definition": term.get("definition"),
            "matched_text": token,
            "match_type": match_type,
            "confidence": round(confidence, 2),
            "aliases": term.get("aliases") or [],
            "asset_links": term.get("asset_links") or [],
        }
        if best is None or candidate["confidence"] > best["confidence"]:
            best = candidate
    return best


def _build_term_conflicts(matches: list[dict]) -> list[dict]:
    """识别本次问题命中的术语冲突。"""
    by_token: dict[str, list[dict]] = {}
    for match in matches:
        token = _semantic_match_text(match.get("matched_text"))
        if not token:
            continue
        by_token.setdefault(token, []).append(match)

    conflicts: list[dict] = []
    for token, owners in by_token.items():
        unique_ids = {m.get("term_id") for m in owners}
        if len(unique_ids) <= 1:
            continue
        conflicts.append(
            {
                "type": "alias_collision",
                "token": owners[0].get("matched_text") or token,
                "term_ids": sorted(i for i in unique_ids if i is not None),
                "terms": [
                    {
                        "id": m.get("term_id"),
                        "name": m.get("name"),
                        "display_name": m.get("display_name"),
                        "definition": m.get("definition"),
                    }
                    for m in owners
                ],
                "severity": "warning",
                "message": "同一个名称或同义词命中了多个业务术语",
            }
        )
    return conflicts


def term_normalize_node(state: AgentState) -> Dict[str, Any]:
    """将业务术语、同义词和冲突信息注入 QueryGraph。

    节点只做确定性归一化，不额外调用 LLM；冲突术语直接转澄清，避免下游
    DSL/SQL 在错误口径上继续生成。
    """
    question = state.get("question") or ""
    structured = state.get("schema_structured") or {}
    terms = structured.get("terms") or []
    entities = dict(state.get("entities") or {})
    logger.info("term_normalize 开始: terms=%s", len(terms))

    matches = [
        match for term in terms if (match := _match_term_in_question(term, question))
    ]
    matches.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    conflicts = _build_term_conflicts(matches)
    term_normalization = {
        "matched_terms": matches,
        "conflicts": conflicts,
        "has_conflict": bool(conflicts),
    }

    if conflicts:
        names = "、".join(
            sorted(
                {
                    term.get("display_name") or term.get("name") or str(term.get("id"))
                    for conflict in conflicts
                    for term in conflict.get("terms", [])
                }
            )
        )
        answer = f"“{conflicts[0]['token']}”可能对应多个业务术语：{names}。请先确认你要使用哪个口径。"
        logger.info("term_normalize 发现冲突: %s", conflicts)
        return {
            "term_normalization": term_normalization,
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "业务术语同义词命中多个定义，需要用户澄清。",
            "answer": answer,
            "route_payload": {
                "kind": "term_conflict_clarification",
                "conflicts": conflicts,
            },
            "should_retry": False,
        }

    if matches:
        existing_terms = _coerce_text_list(entities.get("terms"))
        normalized_terms = _dedupe_texts([*existing_terms, *[m["matched_text"] for m in matches]])
        entities["terms"] = normalized_terms

    logger.info(
        "term_normalize 完成: matched=%s, conflicts=%s",
        len(matches),
        len(conflicts),
    )
    return {
        "entities": entities,
        "term_normalization": term_normalization,
    }


# ── 节点 2.5: 语义资产解析（Semantic Asset Resolution）────────────

_SEMANTIC_ASSET_BUCKETS = {
    "term": "terms",
    "metric": "metrics",
    "dimension": "dimensions",
    "field": "fields",
    "blueprint": "blueprints",
}


def _asset_identity(asset: dict) -> str:
    """生成资产去重键；字段可能没有跨环境稳定 ID，退回 name。"""
    return f"{asset.get('asset_type')}:{asset.get('asset_id') or asset.get('name')}"


def _context_bias(question: str, asset_type: str) -> float:
    """根据问题语气给资产类型加轻量偏置，避免同名资产时选错大类。"""
    q_norm = _normalized_text(question)
    if asset_type == "metric" and any(p in q_norm for p in _METRIC_PATTERNS):
        return 0.06
    if asset_type in ("dimension", "field") and any(p in q_norm for p in _DETAIL_PATTERNS):
        return 0.05
    if asset_type == "term" and any(p in q_norm for p in _KNOWLEDGE_PATTERNS):
        return 0.08
    if asset_type == "blueprint" and any(p in q_norm for p in _BLUEPRINT_PATTERNS):
        return 0.08
    return 0.0


def _asset_aliases(asset_type: str, item: dict) -> list[tuple[str, str]]:
    """返回 (alias, match_type) 列表，match_type 供前端和审计解释来源。"""
    aliases: list[tuple[str, str]] = []
    if item.get("name"):
        aliases.append((str(item["name"]), "exact"))
    if item.get("display_name") and item.get("display_name") != item.get("name"):
        aliases.append((str(item["display_name"]), "display_name"))

    if asset_type == "field":
        for alias in _field_aliases(item):
            match_type = "column_label" if alias != item.get("column_name") else "exact"
            aliases.append((alias, match_type))
    elif asset_type == "blueprint":
        for keyword in _coerce_text_list(item.get("trigger_keywords")):
            aliases.append((keyword, "trigger_keyword"))
        for example in _coerce_text_list(item.get("trigger_examples")):
            aliases.append((example, "trigger_example"))
    else:
        for synonym in _coerce_text_list(item.get("synonyms")):
            aliases.append((synonym, "synonym"))
        for alias in _coerce_text_list(item.get("aliases")):
            aliases.append((alias, "synonym"))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alias, match_type in aliases:
        norm = _semantic_match_text(alias)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append((alias, match_type))
    return deduped


def _build_semantic_asset_catalog(structured: dict | None) -> list[dict]:
    """从 schema_structured 构建统一资产列表。"""
    if not structured:
        return []
    catalog: list[dict] = []
    for asset_type, bucket in _SEMANTIC_ASSET_BUCKETS.items():
        for item in structured.get(bucket) or []:
            name = item.get("name") or item.get("column_name")
            if not name:
                continue
            display_name = item.get("display_name") or name
            catalog.append(
                {
                    "asset_type": asset_type,
                    "asset_id": item.get("id"),
                    "name": name,
                    "display_name": display_name,
                    "table_name": item.get("table_name"),
                    "column_name": item.get("column_name"),
                    "term_type": item.get("term_type"),
                    "implementation_type": item.get("implementation_type"),
                    "asset_links": item.get("asset_links") or [],
                    "_item": item,
                    "_aliases": _asset_aliases(asset_type, item),
                }
            )
    return catalog


def _candidate_from_match(
    asset: dict,
    *,
    query_text: str,
    matched_text: str,
    match_type: str,
    confidence: float,
) -> dict:
    """把一次命中转成可序列化候选，去掉内部字段。"""
    return {
        "asset_type": asset["asset_type"],
        "asset_id": asset.get("asset_id"),
        "name": asset.get("name"),
        "display_name": asset.get("display_name"),
        "table_name": asset.get("table_name"),
        "column_name": asset.get("column_name"),
        "term_type": asset.get("term_type"),
        "implementation_type": asset.get("implementation_type"),
        "matched_text": matched_text,
        "query_text": query_text,
        "match_type": match_type,
        "confidence": round(min(confidence, 0.99), 2),
    }


def _match_semantic_asset(
    asset: dict, query_text: str, question: str, preferred_type: str | None = None
) -> dict | None:
    """计算单个查询词与资产的最佳命中。"""
    query_norm = _semantic_match_text(query_text)
    question_norm = _semantic_match_text(question)
    if not query_norm:
        return None

    best: dict | None = None
    for alias, match_type in asset.get("_aliases") or []:
        alias_norm = _semantic_match_text(alias)
        if not alias_norm:
            continue

        confidence = 0.0
        if query_norm == alias_norm:
            confidence = {
                "exact": 0.96,
                "display_name": 0.94,
                "synonym": 0.88,
                "column_label": 0.86,
                "trigger_keyword": 0.86,
                "trigger_example": 0.78,
            }.get(match_type, 0.82)
        elif len(alias_norm) >= 2 and alias_norm in query_norm:
            confidence = 0.78
        elif len(query_norm) >= 2 and query_norm in alias_norm:
            confidence = 0.72
        elif query_text == question and len(alias_norm) >= 2 and alias_norm in question_norm:
            confidence = 0.74

        if confidence <= 0:
            continue
        confidence += _context_bias(question, asset["asset_type"])
        if preferred_type == asset["asset_type"]:
            confidence += 0.04
        candidate = _candidate_from_match(
            asset,
            query_text=query_text,
            matched_text=alias,
            match_type=match_type,
            confidence=confidence,
        )
        if best is None or candidate["confidence"] > best["confidence"]:
            best = candidate
    return best


def _linked_asset_candidates(term_candidate: dict, catalog: list[dict]) -> list[dict]:
    """术语命中后，把术语显式关联的语义资产也加入候选。"""
    term_asset = next(
        (
            asset
            for asset in catalog
            if asset["asset_type"] == "term" and asset.get("asset_id") == term_candidate.get("asset_id")
        ),
        None,
    )
    if not term_asset:
        return []

    by_identity = {_asset_identity(asset): asset for asset in catalog}
    out: list[dict] = []
    for link in term_asset.get("asset_links") or []:
        key = f"{link.get('asset_type')}:{link.get('asset_id')}"
        asset = by_identity.get(key)
        if not asset:
            continue
        out.append(
            _candidate_from_match(
                asset,
                query_text=term_candidate["query_text"],
                matched_text=term_candidate["matched_text"],
                match_type="linked_term",
                confidence=max(term_candidate["confidence"] - 0.08, 0.5),
            )
        )
    return out


def _entity_query_terms(entities: dict, question: str) -> list[dict]:
    """把上游实体和原问题整理成待解析词。"""
    terms: list[dict] = []
    for entity in entities.get("terms") or []:
        if entity:
            terms.append({"text": str(entity), "preferred_type": "term"})
    for entity in entities.get("metrics") or []:
        if entity:
            terms.append({"text": str(entity), "preferred_type": "metric"})
    for entity in entities.get("dimensions") or []:
        if entity:
            terms.append({"text": str(entity), "preferred_type": "dimension"})

    filters = entities.get("filters")
    if isinstance(filters, list):
        for item in filters:
            if isinstance(item, dict) and item.get("field"):
                terms.append({"text": str(item["field"]), "preferred_type": "field"})

    if question:
        terms.append({"text": question, "preferred_type": None})

    deduped: list[dict] = []
    seen: set[tuple[str, str | None]] = set()
    for term in terms:
        norm = _semantic_match_text(term["text"])
        key = (norm, term.get("preferred_type"))
        if not norm or key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def _to_compat_metric_resolution(
    semantic_resolution: dict, entities: dict, structured: dict | None
) -> dict:
    """把统一资产解析降级成旧 metric_resolution 输出，供旧节点和前端兼容。"""
    by_type = {
        bucket: {str(item.get("name")): item for item in (structured or {}).get(bucket) or []}
        for bucket in ("metrics", "dimensions")
    }

    def _resolve_entity(entity: str, asset_type: str) -> dict:
        bucket = "metrics" if asset_type == "metric" else "dimensions"
        candidates = [
            c
            for c in semantic_resolution.get(bucket, [])
            if c.get("query_text") == entity or c.get("matched_text") == entity
        ]
        if not candidates:
            # 原问题全文命中的候选也可作为兼容解析结果。
            candidates = semantic_resolution.get(bucket, [])
        if not candidates:
            return {
                "entity": entity,
                "resolved": None,
                "status": "unresolved",
                "match_type": None,
                "asset_type": asset_type,
                "asset_id": None,
                "confidence": 0.0,
            }
        best = max(candidates, key=lambda c: c.get("confidence", 0))
        resolved = best.get("name")
        known = by_type.get(bucket, {}).get(str(resolved))
        return {
            "entity": entity,
            "resolved": resolved,
            "status": "matched" if known or resolved else "unresolved",
            "match_type": best.get("match_type"),
            "asset_type": asset_type,
            "asset_id": best.get("asset_id"),
            "confidence": best.get("confidence"),
        }

    resolved_metrics = [
        _resolve_entity(str(entity), "metric") for entity in (entities.get("metrics") or []) if entity
    ]
    resolved_dimensions = [
        _resolve_entity(str(entity), "dimension")
        for entity in (entities.get("dimensions") or [])
        if entity
    ]

    all_matched = all(r["status"] == "matched" for r in resolved_metrics)
    unresolved = [r["entity"] for r in resolved_metrics if r["status"] == "unresolved"]
    return {
        "metrics": resolved_metrics,
        "dimensions": resolved_dimensions,
        "all_matched": all_matched,
        "unresolved": unresolved,
    }


def semantic_asset_resolution_node(state: AgentState) -> Dict[str, Any]:
    """统一解析术语、指标、维度、字段和分析蓝图资产。

    该节点替代旧 metric_resolution_node，但会继续输出 metric_resolution，
    让 DSL 生成、SQL 审计和历史前端展示不用一次性迁移。
    """
    question = state.get("question", "") or ""
    entities = state.get("entities") or {}
    structured = state.get("schema_structured")
    logger.info("semantic_asset_resolution 开始解析资产")

    catalog = _build_semantic_asset_catalog(structured)
    best_by_asset: dict[str, dict] = {}
    candidates_by_query: dict[str, list[dict]] = {}

    for query_term in _entity_query_terms(entities, question):
        text = query_term["text"]
        preferred_type = query_term.get("preferred_type")
        matched_for_query: list[dict] = []
        for asset in catalog:
            candidate = _match_semantic_asset(asset, text, question, preferred_type)
            if not candidate:
                continue
            key = _asset_identity(candidate)
            if key not in best_by_asset or candidate["confidence"] > best_by_asset[key]["confidence"]:
                best_by_asset[key] = candidate
            matched_for_query.append(candidate)

        if matched_for_query:
            matched_for_query.sort(key=lambda c: c["confidence"], reverse=True)
            candidates_by_query[text] = matched_for_query

    # 术语关联扩展：命中业务术语时，把显式绑定资产加入解析结果。
    for candidate in list(best_by_asset.values()):
        if candidate.get("asset_type") != "term":
            continue
        for linked in _linked_asset_candidates(candidate, catalog):
            key = _asset_identity(linked)
            if key not in best_by_asset or linked["confidence"] > best_by_asset[key]["confidence"]:
                best_by_asset[key] = linked

    sorted_assets = sorted(
        best_by_asset.values(),
        key=lambda c: (c.get("confidence", 0), c.get("asset_type") == "metric"),
        reverse=True,
    )
    semantic_resolution: dict[str, Any] = {
        "assets": sorted_assets,
        "terms": [],
        "metrics": [],
        "dimensions": [],
        "fields": [],
        "blueprints": [],
        "ambiguities": [],
        "unresolved": [],
    }
    for candidate in sorted_assets:
        bucket = _SEMANTIC_ASSET_BUCKETS.get(candidate["asset_type"])
        if bucket:
            semantic_resolution[bucket].append(candidate)

    for text, candidates in candidates_by_query.items():
        if len(candidates) < 2:
            continue
        top = candidates[0]
        close_candidates = [
            c for c in candidates[:5] if top["confidence"] - c["confidence"] <= 0.08
        ]
        if len(close_candidates) >= 2:
            semantic_resolution["ambiguities"].append(
                {
                    "text": text,
                    "reason": "多个语义资产置信度接近",
                    "candidates": close_candidates,
                    "resolution_hint": f"请确认“{text}”具体指哪个业务资产",
                }
            )

    explicit_terms = [t for t in _entity_query_terms(entities, question) if t.get("preferred_type")]
    for term in explicit_terms:
        text = term["text"]
        if text not in candidates_by_query:
            semantic_resolution["unresolved"].append(
                {"text": text, "preferred_type": term.get("preferred_type")}
            )

    metric_resolution = _to_compat_metric_resolution(semantic_resolution, entities, structured)
    logger.info(
        "semantic_asset_resolution 完成: assets=%s, terms=%s, metrics=%s, dimensions=%s, fields=%s, "
        "blueprints=%s, ambiguities=%s, unresolved=%s",
        len(semantic_resolution["assets"]),
        len(semantic_resolution["terms"]),
        len(semantic_resolution["metrics"]),
        len(semantic_resolution["dimensions"]),
        len(semantic_resolution["fields"]),
        len(semantic_resolution["blueprints"]),
        len(semantic_resolution["ambiguities"]),
        len(semantic_resolution["unresolved"]),
    )
    return {
        "semantic_asset_resolution": semantic_resolution,
        "metric_resolution": metric_resolution,
    }


def metric_resolution_node(state: AgentState) -> Dict[str, Any]:
    """兼容旧调用：实际执行统一语义资产解析。"""
    return semantic_asset_resolution_node(state)


# ── 节点 3: DSL / SQL 生成 ──────────────────────────────────


def dsl_generate_node(state: AgentState) -> Dict[str, Any]:
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

    llm = get_llm(temperature=0.1)

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
        if error:
            human_text += f"\n\n上一轮错误: {error}"
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
        usage = _extract_token_usage(response)
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
        asset_catalog = _format_dsl_asset_catalog(structured)
        all_matched = metric_resolution.get("all_matched", True)
        unresolved = metric_resolution.get("unresolved", [])

        # 推断路径：指标未在语义层中定义，基于表结构让 LLM 直接生成 SQL
        if not all_matched and ddl_context:
            logger.info(f"走推断路径: 未解析指标={unresolved}")
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
            usage = _extract_token_usage(response)
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
        human_text = f"用户问题: {question}\n\n语义层信息:\n{schema}"
        if asset_catalog:
            human_text += f"\n\n{asset_catalog}"
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
        usage = _extract_token_usage(response)
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
    if error:
        human_text += f"\n\n上一轮错误: {error}"
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
    usage = _extract_token_usage(response)
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
    else:
        # fallback: 从文本中提取
        valid_names = set()
        for line in schema.split("\n"):
            m = re.match(r"-\s+(\w+)\s+\([^)]+\):", line)
            if m:
                valid_names.add(m.group(1))

    errors = []
    metrics = _dsl_item_names(dsl.get("metrics", []))
    dsl_fields_names = _dsl_item_names(dsl.get("fields", []))
    dsl_dim_names = _dsl_item_names(dsl.get("dimensions", []))
    if not metrics and not dsl_fields_names and not dsl_dim_names:
        errors.append("查询条件不足：metrics/dimensions/fields 至少需要一项")
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

        # 推断方言（从 dataset_id 查 Datasource.db_type）
        dataset_id = state.get("dataset_id")
        dialect = _resolve_dialect(db, dataset_id)
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
            sql_parts.append(f"LIMIT {limit}")
        sql = "\n".join(sql_parts)

        guard_result = _guard_readonly_sql(
            sql,
            dialect=dialect,
            query_constraints=query_constraints,
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
            logger.warning("SQL为空，跳过执行")
            return {"sql_result": None, "error": "SQL 为空", "should_retry": True}

        dataset_id = state.get("dataset_id")
        datasource = None
        if dataset_id:
            dataset = db.get(SemanticDataset, dataset_id)
            if dataset:
                datasource = db.get(Datasource, dataset.datasource_id)

        if not datasource:
            datasource = db.query(Datasource).filter(Datasource.status == "connected").first()

        if not datasource:
            logger.error("无可用数据源")
            return {
                "sql_result": None,
                "error": "无可用数据源，请先在数据源管理中测试连接",
                "should_retry": False,
            }

        dialect = (getattr(datasource, "db_type", None) or "postgres").lower()
        guard_result = _guard_readonly_sql(
            sql,
            dialect=dialect,
            query_constraints=state.get("query_constraints"),
        )
        if not guard_result.ok:
            logger.error("SQL执行: SQL Guard 拦截: %s", guard_result.error)
            return {
                "sql_result": None,
                "error": guard_result.error,
                "sql_guard": guard_result.__dict__,
                "should_retry": False,
            }
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
                output = {"sql_result": result, "error": None, "should_retry": False}
                retry_trace = _finish_latest_sql_retry_trace(
                    state,
                    status="success",
                    result=f"自动修复后执行成功，返回 {len(rows)} 行",
                    repaired_sql=sql,
                    row_count=len(rows),
                )
                if retry_trace is not None:
                    output["sql_retry_trace"] = retry_trace
                return output
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
            return output
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
        for m_name in dsl.get("metrics", []) or []:
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
        max_retry = state.get("max_retry_count", DEFAULT_MAX_SQL_RETRY_COUNT)
        datasource_dialect = state.get("datasource_dialect")

        # 解析 datasource（sample data 查询需要）
        datasource = None
        if dataset_id:
            ds = db.get(SemanticDataset, dataset_id)
            if ds:
                datasource = db.get(Datasource, ds.datasource_id)
        if datasource is None:
            datasource = db.query(Datasource).filter(Datasource.status == "connected").first()
        if datasource_dialect is None and datasource is not None:
            datasource_dialect = (getattr(datasource, "db_type", None) or "").lower() or None

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
        llm = get_llm(temperature=0.0)
        system = SystemMessage(content=SQL_AUDIT_SYSTEM)

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
            response = llm.invoke([system, human])
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
            usage = _extract_token_usage(response)
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


async def report_generator_node(state: AgentState) -> Dict[str, Any]:
    """根据 SQL 结果生成自然语言回答和图表推荐。
    使用 astream() 实现真正的 token 级流式，供 astream_events 捕获。"""
    logger.info("报告生成节点开始")
    question = state["question"]
    sql_result = state.get("sql_result")

    if not sql_result:
        logger.warning("无SQL结果，返回默认提示")
        return {"answer": "查询未返回结果，请检查语义层配置。"}

    rows = sql_result.get("rows", [])

    summary_lines = [f"查询结果共 {len(rows)} 行："]
    for row in rows:
        parts = [f"{k}={v}" for k, v in row.items()]
        summary_lines.append("  " + ", ".join(parts))

    result_text = "\n".join(summary_lines)

    llm = get_llm(temperature=0.3)
    dataset_prompt = state.get("dataset_prompt_instructions") or ""
    system = SystemMessage(content=build_report_system(dataset_prompt))
    human = HumanMessage(content=f"用户问题: {question}\n\n查询结果:\n{result_text}")

    full_content = ""
    usage = None
    async for chunk in llm.astream([system, human]):
        full_content += chunk.content
        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
            usage = chunk.usage_metadata

    answer = full_content.strip()

    # 尝试从最后一个 chunk 的 usage_metadata 提取 token 用量
    if usage:
        prompt = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
        completion = usage.get("output_tokens") or usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", prompt + completion)
        token_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
    else:
        token_usage = None

    current_usage = state.get("token_usage") or {}
    merged = _merge_token_usage(current_usage, token_usage or {})

    logger.info("报告生成完成")
    return {"answer": answer, "token_usage": merged}
