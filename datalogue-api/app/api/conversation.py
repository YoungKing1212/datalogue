# ============================================================
# File Name   : conversation.py
# Description:
#   会话管理 API 端点。
#
# Responsibilities:
#   - 创建、列出、重命名、归档和删除会话。
#   - 为 assistant-ui 线程提供持久化消息历史。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

import re
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.observability.tracer import build_langfuse_trace_url
from app import schemas, models

router = APIRouter()


_PUBLIC_HISTORY_BLOCKED_KEYS = {
    "candidate_assets",
    "column",
    "column_labels",
    "columns",
    "control_plane",
    "data",
    "dataset_context_debug",
    "datasource_context",
    "direct_sql",
    "dsl",
    "explainability",
    "field",
    "fields",
    "lead_agent_context",
    "merge_debug",
    "out_capsule",
    "patch",
    "query_plan",
    "query_plan_debug",
    "query_profile",
    "query_task_capsule",
    "raw",
    "raw_result",
    "raw_sql",
    "records",
    "result",
    "result_artifact",
    "result_rows",
    "rows",
    "sample_rows",
    "schema",
    "schema_context",
    "schema_summary",
    "sql",
    "sql_audit_result",
    "sql_diagnosis",
    "sql_list",
    "sql_result",
    "sql_retry_trace",
    "subagent_control_plane",
    "table",
    "tables",
}
_PUBLIC_HISTORY_SQL_RE = re.compile(
    r"(?is)\b(select|insert|update|delete|drop|alter|create|with)\b"
    r".{0,200}\b(from|into|set|table|join|where|values)\b"
)
_PUBLIC_HISTORY_STEP_LABELS = {
    "message_gateway": "任务理解",
    "message-gateway": "任务理解",
    "lead_agent_tools": "能力匹配",
    "manifest_route": "场景匹配",
    "clarification_resolution": "澄清处理",
    "intent_recognition": "意图识别",
    "entry_intent_classification": "入口判断",
    "analysis_blueprint_execute": "分析蓝图执行",
    "candidate_assets": "数据资产匹配",
    "subagent.candidate_assets": "数据资产匹配",
    "query_plan": "查询规划",
    "subagent.query_plan": "查询规划",
    "schema_recall": "数据范围确认",
    "term_normalize_node": "术语标准化",
    "semantic_asset_resolution_node": "语义资产解析",
    "metric_resolution_node": "指标解析",
    "dsl_generate": "查询生成",
    "dsl_validate": "查询校验",
    "dsl_compiler": "执行计划生成",
    "sql_execute": "查询执行",
    "sql_audit": "结果诊断",
    "report_generator": "结果整理",
}


def _is_public_history_blocked_key(key: str) -> bool:
    """判断历史回放 API 字段是否属于内部执行面。"""

    key_lower = key.lower()
    return (
        key_lower in _PUBLIC_HISTORY_BLOCKED_KEYS
        or "sql" in key_lower
        or key_lower.endswith("_schema")
        or key_lower.endswith("_table")
        or key_lower.endswith("_field")
        or key_lower.endswith("_column")
    )


def _safe_public_history_value(value: Any, *, key_name: str = "") -> Any:
    """递归生成浏览器可见历史值；完整 metadata 只保留在数据库和 trace 面。"""

    if _is_public_history_blocked_key(key_name):
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _is_public_history_blocked_key(key):
                continue
            safe_item = _safe_public_history_value(item, key_name=key)
            if safe_item in (None, "", [], {}):
                continue
            sanitized[key] = safe_item
        return sanitized
    if isinstance(value, list):
        return [
            item
            for item in (_safe_public_history_value(item, key_name=key_name) for item in value[:8])
            if item not in (None, "", [], {})
        ]
    if isinstance(value, str):
        text = value.strip()
        if _PUBLIC_HISTORY_SQL_RE.search(text):
            return None
        return text[:1000]
    return value


def _safe_public_ref(value: Any) -> str | dict[str, Any] | None:
    """只保留公开 ref 句柄和业务级类型，兼容 string 与 {ref_id, ref_type} 两种契约。"""

    if isinstance(value, str) and (
        value.startswith("artifact:") or value.startswith("trace:") or value.startswith("checkpoint://")
    ):
        return value
    if isinstance(value, dict):
        ref_id = value.get("ref_id") or value.get("ref")
        if isinstance(ref_id, str) and (
            ref_id.startswith("artifact:") or ref_id.startswith("trace:") or ref_id.startswith("checkpoint://")
        ):
            # ref 对象是前端 ArtifactCard 的稳定输入；这里只保留句柄、类型和标签，不回放 nested payload。
            safe: dict[str, Any] = {"ref_id": ref_id}
            ref_type = _safe_public_history_value(value.get("ref_type"))
            label = _safe_public_history_value(value.get("label"))
            if ref_type:
                safe["ref_type"] = ref_type
            if label:
                safe["label"] = label
            return safe
    return None


def _safe_public_refs(value: Any) -> list[str | dict[str, Any]]:
    """只把公开 ref 句柄带回历史消息，避免嵌套对象夹带执行细节。"""

    if not isinstance(value, list):
        return []
    safe_refs: list[str | dict[str, Any]] = []
    for item in value[:8]:
        ref = _safe_public_ref(item)
        if ref is not None:
            safe_refs.append(ref)
    return safe_refs


def _safe_artifact_card(card: Any) -> dict[str, Any] | None:
    """历史 ArtifactCard 只回放业务摘要、refs 和动作禁用态，不回放 raw preview。"""

    if not isinstance(card, dict):
        return None
    safe_card: dict[str, Any] = {
        "title": _safe_public_history_value(card.get("title")) or "查询结果",
    }
    status = _safe_public_history_value(card.get("status"))
    summary_for_chat = _safe_public_history_value(card.get("summary_for_chat"))
    primary_ref = _safe_public_ref(card.get("primary_ref"))
    related_refs = _safe_public_refs(card.get("related_refs"))
    if status is not None:
        safe_card["status"] = status
    if summary_for_chat is not None:
        safe_card["summary_for_chat"] = summary_for_chat
    if "preview_payload" in card:
        safe_card["preview_payload"] = None  # 旧卡片可能带 raw preview，历史回放只保留“存在过”的空占位。
    if primary_ref is not None:
        safe_card["primary_ref"] = primary_ref
    if related_refs:
        safe_card["related_refs"] = related_refs
    actions: list[dict[str, Any]] = []
    for action in card.get("actions") or []:
        if not isinstance(action, dict):
            continue
        actions.append(
            {
                "action_type": _safe_public_history_value(action.get("action_type")),
                "label": _safe_public_history_value(action.get("label")),
                "ref": action.get("ref") if isinstance(action.get("ref"), str) else "",
                "disabled": bool(action.get("disabled")),
                "disabled_reason": _safe_public_history_value(action.get("disabled_reason")),
            }
        )
    safe_actions = [item for item in actions if item.get("action_type") or item.get("label")]
    if safe_actions:
        safe_card["actions"] = safe_actions
    return safe_card


def _safe_observability_metadata(metadata: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Langfuse/observability 只暴露定位 trace 所需的公开索引。"""

    source = metadata.get(key)
    if not isinstance(source, dict):
        return None
    safe = {
        trace_key: source.get(trace_key)
        for trace_key in ("trace_id", "session_id", "trace_url")
        if source.get(trace_key) is not None
    }
    return safe or None


def _public_subagent_tool_result(value: Any) -> dict[str, Any] | None:
    """SubAgent tool 结果只保留状态、数据集和 artifact ref，不回放控制面。"""

    if not isinstance(value, dict):
        return None
    safe = {
        "status": _safe_public_history_value(value.get("status")),
        "dataset_id": value.get("dataset_id"),
        "display_summary": _safe_public_history_value(value.get("display_summary")),
        "error_summary": _safe_public_history_value(value.get("error_summary")),
        "result_ref": value.get("result_ref") if isinstance(value.get("result_ref"), str) else None,
        "report_ref": value.get("report_ref") if isinstance(value.get("report_ref"), str) else None,
    }
    return {key: item for key, item in safe.items() if item not in (None, "", [], {})} or None


def _public_response_metadata(metadata: Any) -> dict[str, Any] | None:
    """把落库 response_metadata 投影成用户历史回放 DTO。"""

    if not isinstance(metadata, dict):
        return None
    safe: dict[str, Any] = {}
    for key in (
        "answer_explanation",
        "query_caliber",
        "business_caliber",
        "result_ref",
        "report_ref",
        "primary_ref",
        "task_id",
        "trace_id",
        "retry_checkpoint",
        "repair_plan_ref",
        "repair_failure_class",
        "repair_status",
        "repair_attempts",
        "repair_requires_user_confirmation",
        "repair_plan",
        "route_decision",
        "clarification",
        "feedback",
    ):
        if key in metadata:
            value = _safe_public_history_value(metadata.get(key), key_name=key)
            if value not in (None, "", [], {}):
                safe[key] = value
    if metadata.get("artifact_card"):
        safe_card = _safe_artifact_card(metadata.get("artifact_card"))
        if safe_card:
            safe["artifact_card"] = safe_card
    related_refs = _safe_public_refs(metadata.get("related_refs"))
    if related_refs:
        safe["related_refs"] = related_refs
    subagent_tool_result = _public_subagent_tool_result(metadata.get("subagent_tool_result"))
    if subagent_tool_result:
        safe["subagent_tool_result"] = subagent_tool_result
    if isinstance(metadata.get("subagent_tool_results"), list):
        safe_results = [
            item
            for item in (
                _public_subagent_tool_result(result)
                for result in metadata.get("subagent_tool_results", [])[:8]
            )
            if item
        ]
        if safe_results:
            safe["subagent_tool_results"] = safe_results
    for key in ("langfuse", "observability"):
        trace_payload = _safe_observability_metadata(metadata, key)
        if trace_payload:
            safe[key] = trace_payload
    return safe or None


def _public_step_label(step: dict[str, Any]) -> str:
    raw = str(step.get("node") or step.get("display_name") or step.get("name") or "").strip()
    return _PUBLIC_HISTORY_STEP_LABELS.get(raw, "任务处理")


def _public_step_trace(step_trace: Any) -> list[dict[str, Any]] | None:
    """历史 step_trace 只保留业务阶段、状态和耗时，内部节点名不发给浏览器。"""

    if not isinstance(step_trace, list):
        return None
    public_steps: list[dict[str, Any]] = []
    for step in step_trace[:20]:
        if not isinstance(step, dict):
            continue
        public_step: dict[str, Any] = {
            "type": "step",
            "node": "business_step",
            "display_name": _public_step_label(step),
        }
        if step.get("status") is not None:
            public_step["status"] = _safe_public_history_value(step.get("status"))
        if step.get("elapsed_ms") is not None:
            public_step["elapsed_ms"] = step.get("elapsed_ms")
        if step.get("row_count") is not None:
            public_step["row_count"] = step.get("row_count")
        if step.get("column_count") is not None:
            public_step["column_count"] = step.get("column_count")
        public_steps.append(public_step)
    return public_steps or None


def _public_message(message: models.Message) -> dict[str, Any]:
    """生成 MessageOut 的公共 DTO，避免历史接口泄露旧 metadata 内部字段。"""

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "sql_list": None,
        "report_html": None,
        "token_usage": _safe_public_history_value(message.token_usage),
        "step_trace": _public_step_trace(message.step_trace),
        "response_metadata": _public_response_metadata(message.response_metadata),
        "created_at": message.created_at,
    }


def _with_observability_links(message: models.Message) -> models.Message:
    """为历史消息动态补齐 Langfuse trace 深链，不回写数据库。"""

    metadata = dict(message.response_metadata or {})
    langfuse = dict(metadata.get("langfuse") or {})
    trace_id = langfuse.get("trace_id")
    if not trace_id:
        return message

    settings = get_settings()
    base_url = (
        langfuse.get("base_url")
        or metadata.get("observability", {}).get("base_url")
        or settings.LANGFUSE_BASE_URL
        or settings.LANGFUSE_HOST
    )
    project_id = (
        langfuse.get("project_id")
        or metadata.get("observability", {}).get("project_id")
        or settings.LANGFUSE_PROJECT_ID
    )
    trace_url = (
        langfuse.get("trace_url")
        or metadata.get("observability", {}).get("trace_url")
        or build_langfuse_trace_url(
            base_url=base_url,
            project_id=project_id,
            trace_id=trace_id,
        )
    )
    langfuse.update({
        "base_url": base_url,
        "project_id": project_id,
        "trace_url": trace_url,
    })
    metadata["langfuse"] = langfuse
    observability = dict(metadata.get("observability") or {})
    observability.update({
        "base_url": base_url,
        "project_id": project_id,
        "trace_url": trace_url,
        "environment": observability.get("environment") or langfuse.get("environment"),
        "release": observability.get("release") or langfuse.get("release"),
        "prompt_label": observability.get("prompt_label") or langfuse.get("prompt_label"),
    })
    metadata["observability"] = observability
    message.response_metadata = metadata
    return message


@router.get("", response_model=List[schemas.ConversationOut])
def list_conversations(
    archived: bool = Query(default=False, description="true 取归档列表，false 取常规列表"),
    db: Session = Depends(get_db),
):
    """列出对话，默认仅返回未归档。"""
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.archived == archived)
        .order_by(  # 新建空会话可能只有 created_at，排序需稳定兜底。
            models.Conversation.updated_at.desc().nullslast(),
            models.Conversation.created_at.desc().nullslast(),
            models.Conversation.id.desc(),
        )
        .all()
    )


@router.post("", response_model=schemas.ConversationOut, status_code=201)
def create_conversation(payload: schemas.ConversationCreate, db: Session = Depends(get_db)):
    """创建空会话（assistant-ui initialize 流程使用，title 缺省为「新对话」）。"""
    import uuid

    conv = models.Conversation(
        title=payload.title,
        thread_id=payload.thread_id or f"thread-{uuid.uuid4().hex[:12]}",
        user_id=1,
        dataset_id=payload.dataset_id,
        archived=False,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{conv_id}", response_model=schemas.ConversationDetailOut)
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    messages = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv_id)
        .order_by(models.Message.created_at)
        .all()
    )
    messages = [_public_message(_with_observability_links(message)) for message in messages]
    return {"conversation": conv, "messages": messages}


@router.patch("/{conv_id}", response_model=schemas.ConversationOut)
def rename_conversation(
    conv_id: int,
    payload: schemas.ConversationRename,
    db: Session = Depends(get_db),
):
    """重命名对话。"""
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv.title = payload.title
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/{conv_id}/archive", response_model=schemas.ConversationOut)
def archive_conversation(conv_id: int, db: Session = Depends(get_db)):
    """归档对话。"""
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv.archived = True
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/{conv_id}/unarchive", response_model=schemas.ConversationOut)
def unarchive_conversation(conv_id: int, db: Session = Depends(get_db)):
    """取消归档。"""
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    conv.archived = False
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.query(models.Message).filter(models.Message.conversation_id == conv_id).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}
