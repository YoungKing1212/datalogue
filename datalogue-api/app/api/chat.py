# ============================================================
# File Name   : chat.py
# Description:
#   聊天问数 API 端点。
#
# Responsibilities:
#   - 流式输出 NL2SQL 工作流事件和最终回答。
#   - 持久化聊天消息、SQL 和执行轨迹元数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 问数对话路由 — SSE 流式输出 + LangGraph Agent 工作流

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app import schemas, models
from app.graph.workflow import build_workflow

router = APIRouter()
logger = logging.getLogger(__name__)


# 节点名称到前端展示名的映射
_NODE_DISPLAY_NAMES = {
    "intent_recognition": "意图识别",
    "entry_intent_classification": "入口分类",
    "analysis_blueprint_execute": "蓝图执行",
    "schema_recall": "Schema 召回",
    "term_normalize_node": "术语归一化",
    "semantic_asset_resolution_node": "语义资产解析",
    "metric_resolution_node": "指标解析",
    "dsl_generate": "DSL 生成",
    "dsl_validate": "DSL 校验",
    "dsl_compiler": "SQL 编译",
    "sql_execute": "SQL 执行",
    "sql_audit": "SQL 诊断",
    "report_generator": "报告生成",
}

_STATE_OUTPUT_KEYS = {
    "conversation_id",
    "intent",
    "entities",
    "entry_intent",
    "entry_route",
    "entry_reason",
    "blueprint_id",
    "blueprint_match",
    "blueprint_context",
    "knowledge_term_id",
    "route_payload",
    "schema_context",
    "query_constraints",
    "dataset_context_debug",
    "term_normalization",
    "semantic_asset_resolution",
    "metric_resolution",
    "dsl",
    "dsl_valid",
    "sql",
    "sql_result",
    "datasource_dialect",
    "sql_audit_result",
    "sql_diagnosis",
    "answer",
    "sql_list",
    "error",
    "generation_mode",
    "should_retry",
    "token_usage",
}


def _sse_data(payload: dict) -> dict:
    """将 SSE payload 转成 JSON 字符串，兼容 datetime/date/Decimal 等对象。"""
    return {"data": json.dumps(jsonable_encoder(payload), ensure_ascii=False)}


def _is_state_output(value: dict) -> bool:
    """判断字典是否像 AgentState 节点输出。"""
    return bool(_STATE_OUTPUT_KEYS.intersection(value.keys()))


def _find_state_output(value: object, lg_node: str = "", depth: int = 0) -> dict:
    """递归查找 LangGraph/LCEL 事件中的 AgentState 输出片段。"""
    if depth > 5 or not isinstance(value, dict):
        return {}

    if lg_node and isinstance(value.get(lg_node), dict):
        nested = _find_state_output(value[lg_node], lg_node, depth + 1)
        return nested or value[lg_node]

    if _is_state_output(value):
        return value

    for key in ("output", "__end__", "state", "result"):
        nested = _find_state_output(value.get(key), lg_node, depth + 1)
        if nested:
            return nested

    if len(value) == 1:
        nested = _find_state_output(next(iter(value.values())), lg_node, depth + 1)
        if nested:
            return nested

    return {}


def _extract_node_output(event: dict, lg_node: str) -> dict:
    """从 LangGraph 事件中提取当前节点的真实输出。

    astream_events(version="v2") 在不同 LangGraph 版本/事件层级下可能返回两类结构：
    1. {"output": {"entry_intent": "..."}}
    2. {"output": {"entry_intent_classification": {"entry_intent": "..."}}}
    前端 step 事件需要的是节点真实输出，而不是外层节点名包装。
    """
    return _find_state_output(event.get("data", {}).get("output", {}) or {}, lg_node)


async def _stream_chat(payload: schemas.ChatRequest, db: Session):
    """SSE 流式问数：驱动 LangGraph 工作流，逐步发送节点进度事件。"""
    logger.info(f"[_stream_chat] 开始处理问题: {payload.question[:50]}")
    conv_id: int | None = payload.conversation_id

    # 查找或创建对话
    if conv_id:
        conv = db.get(models.Conversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        # 已存在对话的首条消息：自动用首句作为标题（避免「新对话」/空标题占位）
        existing_msg_count = (
            db.query(models.Message).filter(models.Message.conversation_id == conv_id).count()
        )
        if existing_msg_count == 0 and (not conv.title or conv.title in ("新对话", "")):
            conv.title = payload.question[:40]
            if not conv.thread_id:
                conv.thread_id = f"thread-{payload.question[:20]}"
            db.commit()
            db.refresh(conv)
    else:
        conv = models.Conversation(
            title=payload.question[:40],
            thread_id=f"thread-{payload.question[:20]}",
            user_id=1,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conv_id = int(conv.id)

    # 保存用户消息
    db.add(
        models.Message(
            conversation_id=conv_id,
            role="user",
            content=payload.question,
        )
    )
    db.commit()

    # 查询历史消息（最近 6 轮，用于多轮对话上下文）
    history_msgs = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv_id)
        .order_by(models.Message.created_at.desc())
        .limit(12)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_msgs)]

    # 构建初始状态
    initial_state = {
        "question": payload.question,
        "dataset_id": payload.dataset_id,
        "conversation_id": conv_id,
        "history": history,
        "intent": None,
        "entities": None,
        "entry_intent": None,
        "entry_route": None,
        "entry_reason": None,
        "blueprint_id": None,
        "blueprint_match": None,
        "blueprint_context": None,
        "knowledge_term_id": None,
        "route_payload": None,
        "schema_context": None,
        "schema_structured": None,
        "ddl_context": None,
        "query_constraints": None,
        "dataset_context_debug": None,
        "term_normalization": None,
        "semantic_asset_resolution": None,
        "metric_resolution": None,
        "dsl": None,
        "dsl_valid": False,
        "sql": None,
        "sql_result": None,
        "datasource_dialect": None,
        "sql_audit_result": None,
        "sql_diagnosis": None,
        "answer": None,
        "sql_list": [],
        "error": None,
        "retry_count": 0,
        "should_retry": False,
        "token_usage": None,
    }

    # 构建并运行工作流
    app_graph = build_workflow(db)
    final_state: dict = dict(initial_state)
    node_start_times: dict[str, float] = {}

    try:
        logger.info("[_stream_chat] 开始 astream_events 工作流...")
        # 去重集合：astream_events v2 中子 chain 也会触发 on_chain_start/end，
        # 同一 langgraph_node 名称可能重复出现，只取每个节点的第一次事件
        reported_running: set[str] = set()
        reported_done: set[str] = set()
        step_traces: list[dict] = []  # 收集推理步骤供历史加载时恢复思维链

        async for event in app_graph.astream_events(initial_state, version="v2"):
            kind: str = event["event"]
            meta: dict = event.get("metadata", {})
            # langgraph_node 元数据标识当前所属顶层图节点
            lg_node: str = meta.get("langgraph_node", "")

            # ── 节点开始（每节点只报一次）────────────────────
            if (
                kind == "on_chain_start"
                and lg_node in _NODE_DISPLAY_NAMES
                and lg_node not in reported_running
            ):
                reported_running.add(lg_node)
                node_start_times[lg_node] = time.monotonic()
                sse_payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "running",
                }
                logger.info(f"[_stream_chat] step running: {lg_node}")
                yield _sse_data(sse_payload)

            # ── 节点完成（每节点只报一次）────────────────────
            elif kind == "on_chain_end" and lg_node in _NODE_DISPLAY_NAMES:
                output = _extract_node_output(event, lg_node)
                if lg_node in reported_done or not output:
                    continue
                reported_done.add(lg_node)
                elapsed_ms = int((time.monotonic() - node_start_times.get(lg_node, 0)) * 1000)
                # 合并节点输出到 final_state（允许 None 值传播）
                final_state.update(output)

                sse_payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "done",
                    "elapsed_ms": elapsed_ms,
                }
                # 节点特定数据
                if lg_node == "intent_recognition":
                    sse_payload["intent"] = final_state.get("intent") or ""
                    sse_payload["entities"] = final_state.get("entities") or {}
                elif lg_node == "entry_intent_classification":
                    sse_payload["entry_intent"] = final_state.get("entry_intent") or ""
                    sse_payload["entry_route"] = final_state.get("entry_route") or ""
                    sse_payload["entry_reason"] = final_state.get("entry_reason") or ""
                    sse_payload["blueprint_id"] = final_state.get("blueprint_id")
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node == "analysis_blueprint_execute":
                    result = final_state.get("sql_result") or {}
                    sse_payload["blueprint_id"] = final_state.get("blueprint_id")
                    sse_payload["sql"] = final_state.get("sql") or ""
                    sse_payload["rows"] = result.get("row_count", 0)
                    sse_payload["columns"] = result.get("columns", [])
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node in ("semantic_asset_resolution_node", "metric_resolution_node"):
                    sse_payload["semantic_asset_resolution"] = (
                        final_state.get("semantic_asset_resolution") or {}
                    )
                    sse_payload["metric_resolution"] = final_state.get("metric_resolution") or {}
                elif lg_node == "term_normalize_node":
                    sse_payload["term_normalization"] = (
                        final_state.get("term_normalization") or {}
                    )
                    sse_payload["entry_route"] = final_state.get("entry_route") or ""
                    sse_payload["route_payload"] = final_state.get("route_payload") or {}
                elif lg_node == "dsl_generate":
                    sse_payload["dsl"] = final_state.get("dsl") or {}
                    sse_payload["generation_mode"] = final_state.get("generation_mode") or ""
                elif lg_node == "schema_recall":
                    schema = final_state.get("schema_context", "") or ""
                    lines_ = [l for l in schema.split("\n") if l.strip() and not l.startswith("-")]
                    sse_payload["schema_summary"] = lines_[:3]
                elif lg_node == "dsl_compiler":
                    sse_payload["sql"] = final_state.get("sql") or ""
                elif lg_node == "sql_execute":
                    result = final_state.get("sql_result") or {}
                    sse_payload["rows"] = result.get("row_count", 0)
                    sse_payload["columns"] = result.get("columns", [])
                    sse_payload["column_labels"] = result.get("column_labels") or {}
                    sse_payload["elapsed_ms"] = elapsed_ms
                elif lg_node == "sql_audit":
                    diagnosis = (
                        final_state.get("sql_diagnosis")
                        or final_state.get("sql_audit_result")
                        or {}
                    )
                    sse_payload["sql_diagnosis"] = diagnosis
                    sse_payload["sql_audit_result"] = final_state.get("sql_audit_result") or {}
                    sse_payload["code"] = diagnosis.get("code")
                    sse_payload["severity"] = diagnosis.get("severity")
                    sse_payload["retryable"] = diagnosis.get("retryable")
                step_traces.append(sse_payload)
                logger.info(f"[_stream_chat] step done: {lg_node} ({elapsed_ms}ms)")
                yield _sse_data(sse_payload)

            # ── 图级结束事件：兜底合并完整最终状态 ───────────────
            elif kind == "on_chain_end" and not lg_node:
                output = _extract_node_output(event, "")
                if output:
                    final_state.update(output)

            # ── LLM token ───────────────────────────────────
            elif kind == "on_chat_model_stream":
                # report_generator 节点推送 token（打字效果）
                # 其他节点输出为结构化 JSON，不推送给前端
                # 注：同步节点在线程池中运行，token 可能无法全部回传；
                # 前端 onDone 会用 finalData.answer 作为完整答案兜底
                if lg_node and lg_node != "report_generator":
                    continue
                chunk = event.get("data", {}).get("chunk")
                token: str = getattr(chunk, "content", "") or ""
                if token:
                    yield _sse_data({"type": "token", "content": token})

        logger.info("[_stream_chat] astream_events 完成")

    except Exception as e:
        logger.exception(f"[_stream_chat] 工作流异常: {e}")
        yield _sse_data({"type": "step", "node": "error", "display_name": "错误", "status": "done"})
        yield _sse_data({"type": "final", "sql": None, "sql_list": [], "answer": f"处理出错：{e}"})
        return

    # ── 保存助手消息并发送 final 事件 ────────────────
    # 智能兜底：根据失败原因给出具体提示，而非生硬的"抱歉"
    raw_answer = final_state.get("answer")
    error = final_state.get("error")
    generation_mode = final_state.get("generation_mode")
    retry_count = final_state.get("retry_count", 0)
    sql_diagnosis = final_state.get("sql_diagnosis") or final_state.get("sql_audit_result")

    if raw_answer:
        answer = str(raw_answer)
    elif generation_mode == "inferred":
        if error:
            answer = f"AI 基于表结构推断查询时遇到问题：{error}。建议检查已选表的字段是否正确，或尝试在语义层中定义明确的指标。"
        else:
            answer = "AI 基于表结构推断查询时未能成功，请检查已选表配置或尝试换一种问法。"
    elif error:
        if sql_diagnosis:
            answer = f"查询处理出现问题：{error}"
        elif retry_count >= 3:
            answer = f"查询多次尝试后仍未能成功：{error}。建议检查语义层配置或数据源连接。"
        else:
            answer = f"查询处理出现问题：{error}。请稍后重试或换一种问法。"
    else:
        answer = "抱歉，暂时无法回答这个问题。请尝试选择数据集后提问，或检查语义层配置。"

    sql = final_state.get("sql")
    sql_list = final_state.get("sql_list") or []

    final_payload = {
        "type": "final",
        "sql": sql,
        "sql_list": sql_list,
        "answer": answer,
        "entry_intent": final_state.get("entry_intent"),
        "entry_route": final_state.get("entry_route"),
        "entry_reason": final_state.get("entry_reason"),
        "blueprint_id": final_state.get("blueprint_id"),
        "blueprint_match": final_state.get("blueprint_match"),
        "knowledge_term_id": final_state.get("knowledge_term_id"),
        "route_payload": final_state.get("route_payload"),
        "term_normalization": final_state.get("term_normalization"),
        "semantic_asset_resolution": final_state.get("semantic_asset_resolution"),
        "metric_resolution": final_state.get("metric_resolution"),
        "dataset_context_debug": final_state.get("dataset_context_debug"),
        "dsl": final_state.get("dsl"),
        "generation_mode": final_state.get("generation_mode"),
        "sql_result": final_state.get("sql_result"),
        "sql_diagnosis": sql_diagnosis,
        "sql_audit_result": final_state.get("sql_audit_result"),
        "conversation_id": conv_id,
        "title": conv.title,
    }
    logger.info(
        f"[_stream_chat] final: answer_len={len(answer)}, sql={sql}, error={error}, mode={generation_mode}"
    )
    yield _sse_data(final_payload)

    token_usage = final_state.get("token_usage")
    db.add(
        models.Message(
            conversation_id=conv_id,
            role="assistant",
            content=answer,
            sql_list=sql_list,
            token_usage=token_usage,
            step_trace=step_traces,
        )
    )
    db.commit()


@router.post("/stream")
def chat_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    """流式问数接口，返回 SSE 事件流。"""
    logger.info(
        f"[chat_stream] 接收到请求: question={payload.question[:30]}, dataset_id={payload.dataset_id}"
    )
    return EventSourceResponse(_stream_chat(payload, db))


@router.post("/feedback")
def chat_feedback(payload: schemas.ChatFeedback, db: Session = Depends(get_db)):
    """人工反馈接口，对接 LangGraph HumanFeedback 节点（Phase 3 完善）。"""
    # TODO: Phase 3 接入 HumanFeedback 节点的 approve/reject 逻辑
    return {"ok": True, "status": payload.action}
