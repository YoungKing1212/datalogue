# 问数对话路由 — SSE 流式输出 + LangGraph Agent 工作流

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
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
    "schema_recall": "Schema 召回",
    "dsl_generate": "DSL 生成",
    "dsl_validate": "DSL 校验",
    "dsl_compiler": "SQL 编译",
    "sql_execute": "SQL 执行",
    "report_generator": "报告生成",
}



async def _stream_chat(payload: schemas.ChatRequest, db: Session):
    """SSE 流式问数：驱动 LangGraph 工作流，逐步发送节点进度事件。"""
    logger.info(f"[_stream_chat] 开始处理问题: {payload.question[:50]}")
    conv_id: int | None = payload.conversation_id

    # 查找或创建对话
    if conv_id:
        conv = db.get(models.Conversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
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
        "history": history,
        "intent": None,
        "entities": None,
        "schema_context": None,
        "dsl": None,
        "dsl_valid": False,
        "sql": None,
        "sql_result": None,
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
        import time
        logger.info("[_stream_chat] 开始 astream_events 工作流...")
        async for event in app_graph.astream_events(initial_state, version="v2"):
            kind: str = event["event"]
            name: str = event.get("name", "")
            meta: dict = event.get("metadata", {})
            # langgraph_node 元数据标识当前所属节点
            lg_node: str = meta.get("langgraph_node", name)

            # ── 节点开始 ────────────────────────────────────
            if kind == "on_chain_start" and lg_node in _NODE_DISPLAY_NAMES:
                node_start_times[lg_node] = time.monotonic()
                payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "running",
                }
                logger.info(f"[_stream_chat] step running: {lg_node}")
                yield {"data": json.dumps(payload, ensure_ascii=False)}

            # ── 节点完成 ────────────────────────────────────
            elif kind == "on_chain_end" and lg_node in _NODE_DISPLAY_NAMES:
                elapsed_ms = int((time.monotonic() - node_start_times.get(lg_node, 0)) * 1000)
                output: dict = event.get("data", {}).get("output", {}) or {}
                # 合并节点输出到 final_state
                if isinstance(output, dict):
                    for k, v in output.items():
                        if v is not None:
                            final_state[k] = v

                payload = {
                    "type": "step",
                    "node": lg_node,
                    "display_name": _NODE_DISPLAY_NAMES[lg_node],
                    "status": "done",
                    "elapsed_ms": elapsed_ms,
                }
                # 节点特定数据
                if lg_node == "intent_recognition":
                    payload["intent"]   = final_state.get("intent") or ""
                    payload["entities"] = final_state.get("entities") or {}
                elif lg_node == "dsl_generate":
                    payload["dsl"] = final_state.get("dsl") or {}
                elif lg_node == "schema_recall":
                    schema = final_state.get("schema_context", "") or ""
                    lines_  = [l for l in schema.split("\n") if l.strip() and not l.startswith("-")]
                    payload["schema_summary"] = lines_[:3]
                elif lg_node == "dsl_compiler":
                    payload["sql"] = final_state.get("sql") or ""
                elif lg_node == "sql_execute":
                    result = final_state.get("sql_result") or {}
                    payload["rows"]       = result.get("row_count", 0)
                    payload["columns"]    = result.get("columns", [])
                    payload["elapsed_ms"] = elapsed_ms
                logger.info(f"[_stream_chat] step done: {lg_node} ({elapsed_ms}ms)")
                yield {"data": json.dumps(payload, ensure_ascii=False)}

            # ── LLM token ───────────────────────────────────
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token: str = getattr(chunk, "content", "") or ""
                if token:
                    yield {"data": json.dumps({"type": "token", "content": token}, ensure_ascii=False)}

        logger.info("[_stream_chat] astream_events 完成")

    except Exception as e:
        logger.exception(f"[_stream_chat] 工作流异常: {e}")
        yield {"data": json.dumps({"type": "step", "node": "error", "display_name": "错误", "status": "done"}, ensure_ascii=False)}
        yield {"data": json.dumps({"type": "final", "sql": None, "sql_list": [], "answer": f"处理出错：{e}"}, ensure_ascii=False)}
        return

    # ── 保存助手消息并发送 final 事件 ────────────────
    answer: str = str(final_state.get("answer") or "抱歉，暂时无法回答这个问题。")
    sql       = final_state.get("sql")
    sql_list  = final_state.get("sql_list") or []

    final_payload = {
        "type": "final",
        "sql": sql,
        "sql_list": sql_list,
        "answer": answer,
    }
    logger.info(f"[_stream_chat] final: answer_len={len(answer)}, sql={sql}")
    yield {"data": json.dumps(final_payload, ensure_ascii=False)}

    token_usage = final_state.get("token_usage")
    db.add(models.Message(
        conversation_id=conv_id,
        role="assistant",
        content=answer,
        sql_list=sql_list,
        token_usage=token_usage,
    ))
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
