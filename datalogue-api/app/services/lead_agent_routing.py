# ============================================================
# File Name   : lead_agent_routing.py
# Description:
#   LeadAgent 入口路由模块：把原 LangGraph `intent_recognition_node` + `entry_intent_classification_node`
#   合并为单一公开函数 `route_query_intent`，供 chat.py 在驱动 LangGraph 之前调一次，
#   产出全部入口路由决策（intent / entities / entry_intent / entry_route / blueprint_id / ...）。
#
#   Phase 3 改造：
#   - 5 条 PATTERN 常量 + 2 个 match helper + 1 个 _collect_blueprint_terms 从 nodes.py 迁出
#   - 不依赖 app.graph.nodes（保持 services→graph 单向边界）
#
# Author      : yangkai
# Created On  : 2026-06-14
# ============================================================

from __future__ import annotations

import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app import models
from app.graph.llm import get_llm
from app.models import AnalysisBlueprint, BusinessTerm
from app.prompts.intent_router import INTENT_RECOGNITION_SYSTEM
from app.services.observability.tracer import get_observability_tracer
from app.utils.token import extract_token_usage

logger = logging.getLogger(__name__)

# ============================================================
# 入口路由 PATTERN 常量（从 nodes.py 迁出）
# ============================================================


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


# ============================================================
# 辅助函数
# ============================================================


def _normalized_text(text: str) -> str:
    """归一化问题文本，便于做确定性入口路由匹配。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    """text 是否包含任一 pattern（已用于 Phase 1/2 builder）。"""
    return any(pattern in text for pattern in patterns)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _match_analysis_blueprint(
    db: Session, dataset_id: int | None, question: str
) -> dict | None:
    """在当前数据集的已发布分析蓝图中查找最匹配的路由目标。"""
    if not dataset_id or db is None:
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


def _match_business_term(
    db: Session, dataset_id: int | None, question: str
) -> dict | None:
    """按业务术语名称和别名匹配知识库问答目标。"""
    if not dataset_id or db is None:
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


def _safe_json_parse(content: str) -> dict:
    """简单 JSON 解析（与 nodes._safe_json_parse 同语义）。"""
    import json as _json

    try:
        parsed = _json.loads(content)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ============================================================
# 入口路由主函数
# ============================================================


def route_query_intent(
    db: Session,
    *,
    question: str,
    dataset_id: int | None,
    lead_agent_context: dict | None,
    history: list | None,
    multiturn_context: dict | None,
    clarification_response: dict | None,
    tracer: Any | None = None,
    trace_context: Any | None = None,
) -> dict[str, Any]:
    """LeadAgent 入口路由：一次性产出全部入口决策（替代 intent + entry 两个图节点）。

    返回 dict 含 11 个字段：
    - intent: "query" | "chitchat" | "function"
    - entities: {metrics, dimensions, time_range, ...}
    - entry_intent: "chitchat" | "rejection" | "analysis_blueprint" | "knowledge_qa" | "detail_query" | "metric_query" | "clarification"
    - entry_route: "direct_answer" | "reject" | "analysis_blueprint" | "knowledge_qa" | "query_graph" | "clarify"
    - entry_reason: 路由理由文本
    - route_payload: 路由载荷（蓝图匹配/澄清/拒答）
    - blueprint_id: 命中蓝图 ID
    - blueprint_match: 蓝图匹配详情
    - knowledge_term_id: 命中业务术语 ID
    - answer: chitchat/reject/clarification 时填的自然语言回答
    - token_usage: 累积 Token 用量
    """
    lead_agent_context = _as_dict(lead_agent_context)
    multiturn_context = _as_dict(multiturn_context)
    history = history or []

    # tracer span
    if tracer is not None and trace_context is not None and hasattr(tracer, "start_span"):
        tracer.start_span(
            trace_context,
            node="lead_agent_routing",
            display_name="LeadAgent · 入口路由",
            input_payload={
                "question": question,
                "dataset_id": dataset_id,
                "history_len": len(history),
                "has_multiturn_context": bool(multiturn_context),
                "has_clarification_response": bool(clarification_response),
            },
        )

    # 1) LLM 提取 intent + entities
    intent, entities, llm_answer, usage = _invoke_intent_llm(
        question=question,
        history=history,
        multiturn_context=multiturn_context,
        clarification_response=clarification_response,
        db=db,
        tracer=tracer,
        trace_context=trace_context,
    )

    # 2) 规则路由
    result = _classify_entry_intent(
        db=db,
        question=question,
        intent=intent,
        entities=entities,
        dataset_id=dataset_id,
        history=history,
        multiturn_context=multiturn_context,
        clarification_response=clarification_response,
        lead_agent_context=lead_agent_context,
    )

    # 3) 合并 LLM 答案（chitchat 早退时优先用 LLM answer）
    if intent == "chitchat" and llm_answer and not result.get("answer"):
        result["answer"] = llm_answer

    # 4) token_usage 合并
    if usage:
        result["token_usage"] = usage

    if tracer is not None and trace_context is not None and hasattr(tracer, "end_span"):
        tracer.end_span(
            trace_context,
            node="lead_agent_routing",
            output_payload={
                "intent": intent,
                "entry_intent": result.get("entry_intent"),
                "entry_route": result.get("entry_route"),
                "blueprint_id": result.get("blueprint_id"),
                "knowledge_term_id": result.get("knowledge_term_id"),
            },
        )
    return result


def _invoke_intent_llm(
    *,
    question: str,
    history: list,
    multiturn_context: dict,
    clarification_response: dict | None,
    db: Session | None,
    tracer: Any | None,
    trace_context: Any | None,
) -> tuple[str, dict, str | None, dict]:
    """封装 LLM 提取 intent + entities 的调用。失败时降级为 ("query", {}, None, {})。"""
    try:
        llm = get_llm(temperature=0.0, role="intent", db=db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[route_query_intent] LLM 不可用，降级到规则路由: %s", exc)
        return "query", {}, None, {}

    system = SystemMessage(content=INTENT_RECOGNITION_SYSTEM)
    human_text = _build_human_text(
        question=question,
        history=history,
        multiturn_context=multiturn_context,
        clarification_response=clarification_response,
    )
    human = HumanMessage(content=human_text)

    generation = None
    if tracer is not None and hasattr(tracer, "start_generation"):
        generation = tracer.start_generation(
            name="llm.intent_recognition",
            model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
            messages=[system, human],
            metadata={
                "path": "route_query_intent",
                "phase": "lead_agent",
            },
        )

    started_at = time.perf_counter()
    try:
        response = llm.invoke([system, human])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[route_query_intent] LLM 调用失败，降级: %s", exc)
        if generation is not None and tracer is not None and hasattr(tracer, "end_generation"):
            tracer.end_generation(
                generation, output=str(exc), usage={}, error=str(exc)
            )
        return "query", {}, None, {}
    ended_at = time.perf_counter()

    content = getattr(response, "content", "") or ""
    parsed = _safe_json_parse(str(content))
    intent = str(parsed.get("intent") or "query").strip().lower()
    if intent not in {"query", "chitchat", "function"}:
        intent = "query"
    entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
    direct_answer = parsed.get("direct_answer")
    answer = str(direct_answer) if intent == "chitchat" and direct_answer else None

    usage = extract_token_usage(response, [system, human])
    perf_metadata = {
        "path": "route_query_intent",
        "elapsed_ms": int((ended_at - started_at) * 1000),
    }
    if generation is not None and tracer is not None and hasattr(tracer, "end_generation"):
        tracer.end_generation(
            generation,
            output=content,
            usage=usage,
            metadata=perf_metadata,
        )
    return intent, entities, answer, usage


def _build_human_text(
    *,
    question: str,
    history: list,
    multiturn_context: dict,
    clarification_response: dict | None,
) -> str:
    """构造 LLM 的人类 prompt，复用 nodes.py intent_recognition_node 的多轮上下文拼接逻辑。"""
    clarification_hints: list[str] = []
    pending_clarification = multiturn_context.get("pending_clarification")
    if isinstance(pending_clarification, dict) and pending_clarification.get("kind"):
        clarification_hints.append(
            f"上一轮为澄清态 kind={pending_clarification.get('kind')}"
        )
    if clarification_response:
        clarification_hints.append("本轮含 clarification_response")

    if history and len(history) > 1:
        recent = history[-6:-1] if len(history) > 6 else history[:-1]
        ctx = "\n".join(
            [
                f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:100]}"
                for m in recent
            ]
        )
        hint_block = ""
        if clarification_hints:
            hint_block = "\n".join(f"- {h}" for h in clarification_hints) + "\n"
        return (
            f"【历史上下文】\n{ctx}\n"
            f"【多轮提示】\n{hint_block}"
            f"【当前问题】\n{question}"
        )
    if clarification_hints:
        return (
            f"【多轮提示】\n"
            + "\n".join(f"- {h}" for h in clarification_hints)
            + f"\n【当前问题】\n{question}"
        )
    return question


def _extract_token_usage(response: Any, messages: list) -> dict:
    """DEPRECATED: 改用 app.utils.token.extract_token_usage（兼容 input_tokens/output_tokens）。"""
    return extract_token_usage(response, messages)


# ============================================================
# 规则路由（从 nodes.entry_intent_classification_node 迁出）
# ============================================================


def _classify_entry_intent(
    *,
    db: Session,
    question: str,
    intent: str,
    entities: dict,
    dataset_id: int | None,
    history: list,
    multiturn_context: dict,
    clarification_response: dict | None,
    lead_agent_context: dict,
) -> dict[str, Any]:
    """rule-based 入口路由：产出 entry_intent / entry_route / entry_reason / route_payload 等。

    与 nodes.entry_intent_classification_node 行为等价，但不依赖 LangGraph 节点上下文。
    """
    q_norm = _normalized_text(question or "")
    has_metric_entity = bool(entities.get("metrics"))
    has_dimension_entity = bool(entities.get("dimensions"))

    # 1) chitchat 短路
    if intent == "chitchat":
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "chitchat",
            "entry_route": "direct_answer",
            "entry_reason": "粗粒度意图识别为闲聊，直接返回回答。",
            "route_payload": {"kind": "direct_answer"},
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
            "answer": None,
        }

    # 2) function 拒答（但 pending 澄清态时降级为 query）
    if intent == "function":
        pending_clarification = multiturn_context.get("pending_clarification")
        has_pending = (
            dataset_id is not None
            and isinstance(pending_clarification, dict)
            and bool(pending_clarification.get("kind"))
        )
        if has_pending:
            logger.info(
                "[route_query_intent] 跳过 function 拒答：dataset_id=%s 锁定且存在 pending_clarification=%s",
                dataset_id,
                pending_clarification.get("kind"),
            )
            intent = "query"
        else:
            return {
                "intent": intent,
                "entities": entities,
                "entry_intent": "rejection",
                "entry_route": "reject",
                "entry_reason": "功能操作不应进入 QueryGraph。",
                "answer": (
                    "当前问数入口只处理数据查询、分析蓝图和知识解释，"
                    "暂不直接执行保存、发布或导出类操作。"
                ),
                "route_payload": {"kind": "unsupported_function"},
                "blueprint_id": None,
                "blueprint_match": None,
                "knowledge_term_id": None,
            }

    # 3) permission 拒答
    if _contains_any(q_norm, _PERMISSION_PATTERNS):
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "rejection",
            "entry_route": "reject",
            "entry_reason": "用户输入命中权限不足/未授权语义。",
            "answer": (
                "这个问题涉及权限不足或未授权资源，我不能绕过权限继续查询。"
                "请先确认数据集、数据源或知识库授权后再重试。"
            ),
            "route_payload": {"kind": "permission_denied"},
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
        }

    # 4) 蓝图匹配
    blueprint_match = _match_analysis_blueprint(db, dataset_id, question)
    if blueprint_match:
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "analysis_blueprint",
            "entry_route": "analysis_blueprint",
            "entry_reason": "问题命中已发布分析蓝图的关键词、示例或使用说明。",
            "blueprint_id": blueprint_match["blueprint_id"],
            "blueprint_match": blueprint_match,
            "answer": (
                f"已命中分析蓝图「{blueprint_match['name']}」，"
                "将按固定分析逻辑处理。"
            ),
            "route_payload": {"kind": "analysis_blueprint", **blueprint_match},
        }

    # 5) 知识库问答
    is_knowledge_question = _contains_any(q_norm, _KNOWLEDGE_PATTERNS)
    if is_knowledge_question:
        term_match = _match_business_term(db, dataset_id, question)
        payload: dict[str, Any] = {"kind": "knowledge_qa"}
        term_id = None
        answer = (
            "我识别到这是知识解释类问题，"
            "但还需要更具体的业务术语或可用知识库内容才能回答。"
        )
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
            "intent": intent,
            "entities": entities,
            "entry_intent": "knowledge_qa",
            "entry_route": "knowledge_qa",
            "entry_reason": "问题命中定义、口径、解释等知识库问答语义。",
            "knowledge_term_id": term_id,
            "answer": answer,
            "route_payload": payload,
        }

    # 6) 模糊澄清
    is_blueprint_like = _contains_any(q_norm, _BLUEPRINT_PATTERNS)
    is_metric_query = has_metric_entity or _contains_any(q_norm, _METRIC_PATTERNS)
    is_detail_query = _contains_any(q_norm, _DETAIL_PATTERNS)
    is_short_ambiguous = len(q_norm) <= 4 and _contains_any(q_norm, _AMBIGUOUS_PATTERNS)

    if is_blueprint_like and not is_metric_query and not is_detail_query:
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "复杂固定分析语义未命中已发布蓝图，进入澄清。",
            "answer": (
                "这个问题更像固定分析诉求，但当前没有命中可用分析蓝图。"
                "请补充要分析的主题、指标或选择具体蓝图。"
            ),
            "route_payload": {
                "kind": "clarification",
                "missing": ["blueprint_or_metrics"],
            },
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
        }

    if is_short_ambiguous:
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "短句或指代不清，无法可靠判断查询目标。",
            "answer": (
                "这个问题缺少明确对象。"
                "请补充要查询的指标、维度、时间范围或业务术语。"
            ),
            "route_payload": {"kind": "clarification", "missing": ["query_target"]},
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
        }

    # 7) detail / metric 主链
    if is_detail_query:
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "detail_query",
            "entry_route": "query_graph",
            "entry_reason": "问题命中明细/列表类查询语义，继续 NL2SQL。",
            "route_payload": {"kind": "detail_query"},
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
            "answer": None,
        }

    if is_metric_query or has_dimension_entity:
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "metric_query",
            "entry_route": "query_graph",
            "entry_reason": "问题命中指标/统计类查询语义，继续 NL2SQL。",
            "route_payload": {"kind": "metric_query"},
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
            "answer": None,
        }

    # 8) 默认：澄清
    return {
        "intent": intent,
        "entities": entities,
        "entry_intent": "clarification",
        "entry_route": "clarify",
        "entry_reason": "未命中普通问数、蓝图、知识库或拒答规则。",
        "answer": (
            "我还无法确定你想查询数据、运行分析蓝图，还是询问业务知识。"
            "请补充查询对象或说明要分析的问题。"
        ),
        "route_payload": {"kind": "clarification", "missing": ["intent"]},
        "blueprint_id": None,
        "blueprint_match": None,
        "knowledge_term_id": None,
    }
