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
#   Phase 4 改造：
#   - 新增 `resolve_term_clarification`：把原 LangGraph `clarification_resolution_node`
#     上提至 chat 层，chat.py 在 `route_query_intent` 之后调一次；missing/expired/unresolved
#     走 `_early_route_return` 早退，resolved 注入 selected_term_id + resolved_question
#   - 迁出 6 个澄清解析辅助函数（parse_clarification_response / term_resolve_clarification_candidate
#     / term_latest_pending_clarification / term_format_clarification_answer / term_response_selected_index
#     / term_candidate_matches_text）
#   - LangGraph 节点数 13 → 12
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
    "日志",
    "工作日志",
    "工作日报",
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
_FILTER_REFINEMENT_FIELDS = ("姓名", "名字", "账号", "账户", "工号", "部门", "项目", "状态")
_FILTER_REFINEMENT_OPERATORS = ("为", "是", "=", "等于", "叫")


# ============================================================
# 辅助函数
# ============================================================


def _normalized_text(text: str) -> str:
    """归一化问题文本，便于做确定性入口路由匹配。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    """text 是否包含任一 pattern（已用于 Phase 1/2 builder）。"""
    return any(pattern in text for pattern in patterns)


def _has_multiturn_query_context(
    *,
    dataset_id: int | None,
    multiturn_context: dict,
    lead_agent_context: dict,
) -> bool:
    """判断本轮是否有可承接的上一轮查询上下文。"""
    if dataset_id is None:
        return False

    contexts = [multiturn_context, lead_agent_context.get("thread_context")]
    for context in contexts:
        if not isinstance(context, dict):
            continue
        raw = context.get("raw") if isinstance(context.get("raw"), dict) else {}
        last_success_task = context.get("last_success_task") or raw.get("last_success_task")
        if isinstance(last_success_task, dict) and last_success_task.get("query_type"):
            return True
        classification = context.get("multiturn_classification") or raw.get(
            "multiturn_classification"
        )
        if isinstance(classification, dict) and classification.get("intent") == "continue":
            return True
    return False


def _looks_like_filter_refinement(question: str) -> bool:
    """识别“姓名为XX”这类承接上一轮结果的字段过滤短追问。"""
    q_norm = _normalized_text(question)
    if not q_norm:
        return False
    for field in _FILTER_REFINEMENT_FIELDS:
        if field not in q_norm:
            continue
        field_index = q_norm.find(field)
        suffix = q_norm[field_index + len(field) :]
        for operator in _FILTER_REFINEMENT_OPERATORS:
            if suffix.startswith(operator):
                return bool(suffix[len(operator) :])
    return False


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _lead_multiturn_refinement(lead_agent_context: dict) -> dict[str, Any]:
    """读取 LeadAgent 输出的抽象追问槽位。"""

    refinement = lead_agent_context.get("multiturn_refinement")
    return refinement if isinstance(refinement, dict) else {}


def _refinement_can_continue(refinement: dict[str, Any]) -> bool:
    """判断抽象槽位是否足以承接上一轮查询。"""

    if refinement.get("intent") != "continue":
        return False
    if refinement.get("requires_clarification"):
        return False
    try:
        confidence = float(refinement.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.5:
        return False
    slots = refinement.get("slots")
    return isinstance(slots, dict) and any(value not in (None, "", [], {}) for value in slots.values())


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
            display_name="lead_agent_routing",
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
                generation,
                output=str(exc),
                usage={},
                metadata={"status": "fallback", "error": str(exc)[:1000]},
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

    # 4) LeadAgent LLM 多轮追问理解：优先承接上一轮成功查询，避免被蓝图/关键词规则抢路由。
    refinement = _lead_multiturn_refinement(lead_agent_context)
    if refinement.get("requires_clarification"):
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "LeadAgent 已识别为多轮追问，但仍需要补充约束。",
            "answer": refinement.get("clarification_question")
            or "这个追问还缺少可承接的过滤条件，请补充要筛选的对象、时间或状态。",
            "route_payload": {
                "kind": "clarification",
                "source": "llm_multiturn_refinement",
                "multiturn_refinement": refinement,
            },
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
        }
    if _refinement_can_continue(refinement):
        if _has_multiturn_query_context(
            dataset_id=dataset_id,
            multiturn_context=multiturn_context,
            lead_agent_context=lead_agent_context,
        ):
            return {
                "intent": intent,
                "entities": entities,
                "entry_intent": "detail_query",
                "entry_route": "query_graph",
                "entry_reason": "LeadAgent 已产出多轮追问抽象槽位，继承上一轮查询上下文继续 NL2SQL。",
                "route_payload": {
                    "kind": "detail_query",
                    "source": "llm_multiturn_refinement",
                    "multiturn_refinement": refinement,
                },
                "blueprint_id": None,
                "blueprint_match": None,
                "knowledge_term_id": None,
                "answer": None,
            }
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "LeadAgent 识别为追问，但没有可承接的上一轮成功查询。",
            "answer": "没有可承接的上一轮查询结果，请先发起一次明确的数据查询。",
            "route_payload": {
                "kind": "clarification",
                "source": "llm_multiturn_refinement",
                "missing": ["last_success_task"],
                "multiturn_refinement": refinement,
            },
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
        }

    # 5) 蓝图匹配
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

    # 6) 知识库问答
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

    # 7) 模糊澄清
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

    # 8) detail / metric 主链
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

    if _has_multiturn_query_context(
        dataset_id=dataset_id,
        multiturn_context=multiturn_context,
        lead_agent_context=lead_agent_context,
    ) and _looks_like_filter_refinement(question):
        return {
            "intent": intent,
            "entities": entities,
            "entry_intent": "detail_query",
            "entry_route": "query_graph",
            "entry_reason": "已继承上一轮查询上下文，本轮命中字段过滤追问，继续 NL2SQL。",
            "route_payload": {
                "kind": "detail_query",
                "source": "multiturn_filter_refinement",
            },
            "blueprint_id": None,
            "blueprint_match": None,
            "knowledge_term_id": None,
            "answer": None,
        }

    # 9) 默认：澄清
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


# ============================================================
# Phase 4：术语澄清解析（chat 层接管 LangGraph `clarification_resolution_node`）
# ============================================================
#
# 行为契约 1:1 等价于 `app/graph.nodes.clarification_resolution_node`：
#   5 状态机：none / missing / expired / unresolved / resolved
# 辅助函数（_parse_clarification_response / _resolve_clarification_candidate /
# _latest_pending_clarification / _response_selected_index / _candidate_matches_text /
# _format_term_clarification_answer / _ORDINAL_WORDS）从 graph/nodes.py 迁出。
# 复用 _normalized_text / _coerce_text_list / _semantic_match_text 三个本地副本，
# 避免 services→graph 反向依赖。
# ============================================================

import re  # noqa: F401  # 保持与文件其他部分 import 风格一致
from datetime import datetime

from app.models.conversation import PendingClarification

_TERM_PENDING_NODE_NAME = "term_clarification_resolution"
_TERM_PENDING_DISPLAY_NAME = "术语澄清解析"

_ORDINAL_WORDS = {
    "一": 1,
    "第一个": 1,
    "第一": 1,
    "1": 1,
    "二": 2,
    "第二个": 2,
    "第二": 2,
    "2": 2,
    "三": 3,
    "第三个": 3,
    "第三": 3,
    "3": 3,
    "四": 4,
    "第四个": 4,
    "第四": 4,
    "4": 4,
    "五": 5,
    "第五个": 5,
    "第五": 5,
    "5": 5,
}


def _term_normalized_text(text: str) -> str:
    """归一化文本（空白 + 小写），用于序号匹配。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _term_coerce_text_list(value: Any) -> list[str]:
    """把 JSON / 字符串 / 列表里的别名清洗成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        raw_items = list(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                raw_items = json.loads(stripped)
                if not isinstance(raw_items, list):
                    raw_items = [stripped]
            except (ValueError, TypeError):
                raw_items = [item.strip() for item in stripped.split(",") if item.strip()]
        else:
            raw_items = [item.strip() for item in stripped.split(",") if item.strip()]
    else:
        raw_items = [str(value)]
    out: list[str] = []
    for item in raw_items:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _term_semantic_match_text(text: Any) -> str:
    """忽略大小写、空白、下划线、引用符后的纯语义匹配文本。"""
    if text is None:
        return ""
    return re.sub(r"[\s_`'\".]+", "", str(text).strip().lower())


def parse_clarification_response(payload: Any) -> dict[str, Any]:
    """兼容 Pydantic 对象和普通 dict，提取澄清回复。"""
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if v is not None}
    return {}


def term_response_selected_index(text: str) -> int | None:
    """从『第一个/1/选 2』等回复中提取候选序号。"""
    normalized = _term_normalized_text(text)
    if not normalized:
        return None
    for word, value in _ORDINAL_WORDS.items():
        if _term_normalized_text(word) == normalized or _term_normalized_text(word) in normalized:
            return value
    match = re.search(r"(?:选择|选|第)?\s*(\d+)", text or "")
    return int(match.group(1)) if match else None


def term_candidate_matches_text(candidate: dict, text: str) -> bool:
    """判断自然语言回复是否指向某个候选术语。"""
    text_norm = _term_semantic_match_text(text)
    if not text_norm:
        return False
    aliases = [
        candidate.get("display_name"),
        candidate.get("name"),
        *_term_coerce_text_list(candidate.get("aliases")),
    ]
    for alias in aliases:
        alias_norm = _term_semantic_match_text(alias)
        if alias_norm and (alias_norm == text_norm or alias_norm in text_norm):
            return True
    return False


def term_resolve_clarification_candidate(
    candidates: list[dict],
    response: dict[str, Any],
    text: str,
) -> dict | None:
    """从结构化回复或自然语言中解析候选项。"""
    selected_term_id = response.get("selected_term_id")
    if selected_term_id is not None:
        for candidate in candidates:
            if int(candidate.get("term_id")) == int(selected_term_id):
                return candidate

    selected_index = response.get("selected_index")
    if selected_index is None:
        selected_index = term_response_selected_index(response.get("selected_text") or text)
    if selected_index is not None:
        for candidate in candidates:
            if int(candidate.get("index") or 0) == int(selected_index):
                return candidate

    selected_text = response.get("selected_text") or text
    for candidate in candidates:
        if term_candidate_matches_text(candidate, selected_text):
            return candidate
    return None


def term_latest_pending_clarification(
    db: Session,
    conversation_id: int | None,
    dataset_id: int | None,
    response: dict[str, Any],
) -> PendingClarification | None:
    """查找当前会话最近一个待处理术语澄清。"""
    if not conversation_id:
        return None
    query = db.query(PendingClarification).filter(
        PendingClarification.conversation_id == conversation_id,
        PendingClarification.clarification_type == "term_conflict",
        PendingClarification.status == "pending",
    )
    if dataset_id is not None:
        query = query.filter(
            (PendingClarification.dataset_id == dataset_id)
            | (PendingClarification.dataset_id.is_(None))
        )
    clarification_id = response.get("clarification_id")
    if clarification_id is not None:
        query = query.filter(PendingClarification.id == int(clarification_id))
    return query.order_by(PendingClarification.created_at.desc()).first()


def term_format_clarification_answer(candidates: list[dict], prefix: str) -> str:
    """生成术语澄清提示文案。"""
    parts = []
    for candidate in candidates:
        label = candidate.get("display_name") or candidate.get("name") or candidate.get("term_id")
        definition = candidate.get("definition")
        parts.append(
            f"{candidate.get('index')}. {label}" + (f"（{definition}）" if definition else "")
        )
    return f"{prefix}请回复序号或术语名称：{'；'.join(parts)}"


def _emit_term_span(tracer, trace_context, span_input: dict, span_output: dict) -> None:
    """emit term 澄清解析的 tracer span（缺失 tracer / 出错时降级跳过）。"""
    if tracer is None or not hasattr(tracer, "start_span"):
        return
    try:
        tracer.start_span(
            trace_context,
            node=_TERM_PENDING_NODE_NAME,
            display_name=_TERM_PENDING_DISPLAY_NAME,
            input_payload=span_input,
        )
        if hasattr(tracer, "end_span"):
            tracer.end_span(
                trace_context,
                node=_TERM_PENDING_NODE_NAME,
                output_payload=span_output,
            )
    except Exception:  # noqa: BLE001
        logger.warning("术语澄清 span emit 失败", exc_info=True)


def resolve_term_clarification(
    db: Session,
    *,
    question: str,
    conversation_id: int | None,
    dataset_id: int | None,
    clarification_response: Any,
    tracer: Any | None = None,
    trace_context: Any | None = None,
) -> dict[str, Any]:
    """Phase 4: chat 层 term 澄清解析（替代 LangGraph clarification_resolution_node）。

    5 状态机（与原节点行为 1:1 等价）：
    - none       : 无挂起且无回复 → 透明通过
    - missing    : 有回复但找不到挂起 → 拒答
    - expired    : 挂起已过期 → 拒答（lazy mark expired + commit）
    - unresolved : 候选未匹配 → 重新提示
    - resolved   : 命中候选 → 注入 selected_term_id + resolved_question
    """
    response = parse_clarification_response(clarification_response)
    pending = term_latest_pending_clarification(db, conversation_id, dataset_id, response)
    has_response = bool(response) or bool(pending)

    span_input = {
        "question": question,
        "conversation_id": conversation_id,
        "dataset_id": dataset_id,
        "has_response": has_response,
    }

    if not pending:
        if response:
            result = {
                "status": "missing",
                "selected_term_id": None,
                "resolved_question": None,
                "answer": "没有找到待处理的术语澄清，请重新提出完整问题。",
                "entry_intent": "clarification",
                "entry_route": "clarify",
                "entry_reason": "没有找到待处理的术语澄清态。",
                "route_payload": {"kind": "term_conflict_missing"},
                "clarification_resolution_result": {"status": "missing"},
            }
        else:
            result = {
                "status": "none",
                "selected_term_id": None,
                "resolved_question": None,
                "answer": None,
                "entry_intent": None,
                "entry_route": None,
                "entry_reason": None,
                "route_payload": {},
                "clarification_resolution_result": {"status": "none"},
            }
        _emit_term_span(tracer, trace_context, span_input, {
            "status": result["status"],
            "route_payload": result["route_payload"],
        })
        return result

    now = datetime.utcnow()
    if pending.expires_at and pending.expires_at <= now:
        pending.status = "expired"
        db.commit()
        result = {
            "status": "expired",
            "selected_term_id": None,
            "resolved_question": None,
            "answer": "术语澄清已过期，请重新提出完整问题。",
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "术语澄清态已过期。",
            "route_payload": {
                "kind": "term_conflict_expired",
                "clarification_id": pending.id,
            },
            "clarification_resolution_result": {
                "status": "expired",
                "clarification_id": pending.id,
            },
        }
        _emit_term_span(tracer, trace_context, span_input, {
            "status": result["status"],
            "route_payload": result["route_payload"],
        })
        return result

    candidates = pending.candidates or []
    selected = term_resolve_clarification_candidate(candidates, response, question)
    if not selected:
        answer = term_format_clarification_answer(
            candidates, "我还不能确认你要使用哪个术语口径。",
        )
        result = {
            "status": "unresolved",
            "selected_term_id": None,
            "resolved_question": None,
            "answer": answer,
            "entry_intent": "clarification",
            "entry_route": "clarify",
            "entry_reason": "用户澄清回复未能匹配候选术语。",
            "route_payload": {
                "kind": "term_conflict_clarification",
                "clarification_id": pending.id,
                "candidates": candidates,
                "expires_at": pending.expires_at.isoformat() if pending.expires_at else None,
            },
            "clarification_resolution_result": {
                "status": "unresolved",
                "clarification_id": pending.id,
            },
        }
        _emit_term_span(tracer, trace_context, span_input, {
            "status": result["status"],
            "route_payload": result["route_payload"],
        })
        return result

    selected_payload = {
        "term_id": selected.get("term_id"),
        "index": selected.get("index"),
        "name": selected.get("name"),
        "display_name": selected.get("display_name"),
        "source": "structured" if response else "natural_language",
        "response_text": response.get("selected_text") or question,
    }
    pending.status = "resolved"
    pending.resolved_at = now
    pending.selected_payload = selected_payload
    db.commit()
    logger.info(
        "术语澄清解析成功: clarification_id=%s, term_id=%s",
        pending.id,
        selected_payload["term_id"],
    )
    result = {
        "status": "resolved",
        "selected_term_id": int(selected["term_id"]),
        "resolved_question": pending.original_question,
        "answer": None,
        "entry_intent": None,
        "entry_route": None,
        "entry_reason": None,
        "route_payload": {
            "kind": "term_conflict_resolved",
            "clarification_id": pending.id,
            "selected_term_id": int(selected["term_id"]),
            "selected_term": selected_payload,
        },
        "clarification_resolution_result": {
            "status": "resolved",
            "clarification_id": pending.id,
            "selected_term": selected_payload,
        },
    }
    _emit_term_span(tracer, trace_context, span_input, {
        "status": result["status"],
        "route_payload": result["route_payload"],
        "selected_term_id": result["selected_term_id"],
    })
    return result
