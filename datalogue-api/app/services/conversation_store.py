# ============================================================
# File Name   : conversation_store.py
# Description:
#   多轮对话会话状态存储服务。
#
# Responsibilities:
#   - 管理 session 级 ConversationState 的加载、保存和轮次锁。
#   - 为 LeadAgent 跨轮状态、SubAgent 胶囊和消息压缩提供持久化入口。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.graph.llm import get_llm
from app.schemas.capsule import capsule_meta
from app.services.observability.tracer import get_observability_tracer
from app.services.observability.prompts import get_prompt_manager
from app.utils.token import estimate_text_tokens


logger = logging.getLogger(__name__)

DATALOGUE_COMPACTION_PROMPT_NAME = "datalogue-compaction"
THREAD_STATE_KEY = "_thread"
DATALOGUE_COMPACTION_FALLBACK_PROMPT = """你是 Datalogue 多轮问数会话压缩器。

请把旧对话压缩为简洁中文摘要，只保留：
1. 叙事线：用户在分析什么业务问题，以及对话进展。
2. 用户偏好：偏好的口径、表达、输出风格。
3. 未解决问题：仍挂起的澄清、待确认项或风险。

不要保留具体查询条件、指标、维度、过滤器、SQL、完整结果行或可执行查询状态；这些由 SubAgent capsule 保存。

已有摘要：
{{existing_summary}}

待压缩旧消息：
{{messages_json}}

请输出 800 字以内的中文摘要。"""


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


def session_key(payload_session_id: str | None, conversation_id: int | None) -> str:
    """生成业务多轮 session_id，避免与 Langfuse session_id 混用。"""

    if payload_session_id and payload_session_id.strip():
        return payload_session_id.strip()[:120]
    if conversation_id is not None:
        return f"conversation-{conversation_id}"
    return "conversation-new"


class ConversationStore:
    """ConversationState DAO。

    锁使用条件 UPDATE 实现，兼容 SQLite 测试环境和 PostgreSQL 生产环境。
    """

    def __init__(self, db: Session):
        self.db = db

    def load(self, session_id: str) -> models.ConversationState | None:
        return self.db.get(models.ConversationState, session_id)

    def load_or_create(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> models.ConversationState:
        state = self.load(session_id)
        if state:
            return state
        state = models.ConversationState(
            session_id=session_id,
            user_id=user_id,
            messages=[],
            facts=[],
            subagent_capsules={},
            status="idle",
        )
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return state

    def get_thread_state(self, session_id: str | None) -> dict[str, Any]:
        """读取 session 级线程记忆，第一版固定保存在 SubAgent capsule 桶内。"""

        if not session_id:
            return {}
        state = self.load(session_id)
        if not state:
            return {}
        capsules = dict(state.subagent_capsules or {})
        thread_state = capsules.get(THREAD_STATE_KEY)
        return dict(thread_state) if isinstance(thread_state, dict) else {}

    def update_thread_state(
        self,
        session_id: str | None,
        patch: dict[str, Any],
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """以浅合并方式更新线程记忆，并写入 ConversationState.subagent_capsules。"""

        if not session_id or not isinstance(patch, dict):
            return {}
        state = self.load_or_create(session_id=session_id, user_id=user_id or "1")
        capsules = dict(state.subagent_capsules or {})
        current = capsules.get(THREAD_STATE_KEY)
        thread_state = dict(current) if isinstance(current, dict) else {}
        thread_state.update(patch)
        thread_state = jsonable_encoder(thread_state)
        capsules[THREAD_STATE_KEY] = thread_state
        state.subagent_capsules = capsules
        state.updated_at = datetime.now(timezone.utc)
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return thread_state

    def lead_multiturn_context(self, state: models.ConversationState | None) -> dict[str, Any]:
        """组装 LeadAgent 可消费的控制面多轮上下文。"""

        if not state:
            return {}
        messages = list(state.messages or [])
        capsules = dict(state.subagent_capsules or {})
        thread_state = capsules.get(THREAD_STATE_KEY)
        thread_state = thread_state if isinstance(thread_state, dict) else {}
        last_user = next((item for item in reversed(messages) if item.get("role") == "user"), None)
        last_assistant = next(
            (item for item in reversed(messages) if item.get("role") == "assistant"),
            None,
        )
        return {
            "active_dataset_id": state.active_dataset_id,
            "summary": state.compacted_summary,
            "facts": state.facts or [],
            "resolved_time_context": state.resolved_time_context,
            "pending_clarification": state.pending_clarification,
            "turn_index": state.turn_index,
            "last_question": (last_user or {}).get("content"),
            "last_answer_summary": (last_assistant or {}).get("content"),
            "last_success_task": thread_state.get("last_success_task"),
            "active_task": thread_state.get("active_task"),
            "capsule_metas": self.capsule_metas(state),
        }

    def resolve_pending_clarification(
        self,
        state: models.ConversationState | None,
        *,
        question: str,
        clarification_response: Any = None,
    ) -> dict[str, Any]:
        """解析 ConversationState 中的挂起澄清，返回本轮应注入的恢复动作。"""

        pending = (state.pending_clarification or {}) if state else {}
        if not isinstance(pending, dict) or not pending:
            return {"status": "none"}
        response = _clarification_response_dict(clarification_response)
        kind = str(pending.get("kind") or "")

        if kind in {"manifest_route", "dataset_missing", "dataset_choice"}:
            selected_dataset_id = _resolve_dataset_candidate(pending, response, question)
            if selected_dataset_id is not None:
                return {
                    "status": "resolved",
                    "type": "dataset",
                    "dataset_id": selected_dataset_id,
                    "clear_pending": True,
                    "reason": "dataset_candidate_selected",
                }
            if _looks_like_topic_switch(question):
                return {
                    "status": "cleared",
                    "type": "dataset",
                    "clear_pending": True,
                    "reason": "user_changed_topic",
                }
            return {"status": "pending", "type": "dataset", "pending": pending}

        if kind == "term_conflict_clarification":
            injected = dict(response)
            if pending.get("clarification_id") and not injected.get("clarification_id"):
                injected["clarification_id"] = pending.get("clarification_id")
            if question and not injected.get("selected_text"):
                injected["selected_text"] = question
            conversation_id = pending.get("conversation_id")
            if _looks_like_topic_switch(question) and not response:
                return {
                    "status": "cleared",
                    "type": "term",
                    "clear_pending": True,
                    "reason": "user_changed_topic",
                }
            return {
                "status": "inject",
                "type": "term",
                "conversation_id": conversation_id,
                "dataset_id": pending.get("dataset_id"),
                "clarification_response": injected,
                "reason": "restore_term_clarification",
            }

        if _looks_like_topic_switch(question):
            return {
                "status": "cleared",
                "type": kind or "generic",
                "clear_pending": True,
                "reason": "user_changed_topic",
            }
        return {"status": "pending", "type": kind or "generic", "pending": pending}

    def capsule_metas(self, state: models.ConversationState | None) -> dict[str, dict[str, Any]]:
        """仅导出 LeadAgent 可读的 capsule 元字段。"""

        metas: dict[str, dict[str, Any]] = {}
        capsules = (state.subagent_capsules or {}) if state else {}
        for dataset_id, capsule in capsules.items():
            if dataset_id == THREAD_STATE_KEY:
                continue
            if not isinstance(capsule, dict):
                continue
            try:
                metas[str(dataset_id)] = capsule_meta(
                    {
                        "capsule_version": capsule.get("capsule_version") or capsule.get("version") or "",
                        "dataset_id": capsule.get("dataset_id") or dataset_id,
                        "schema_version": capsule.get("schema_version")
                        or capsule.get("bound_schema_version")
                        or "",
                        "updated_turn": capsule.get("updated_turn")
                        or capsule.get("turn_index")
                        or 0,
                    }
                ).model_dump()
            except Exception:
                metas[str(dataset_id)] = {
                    "capsule_version": "invalid",
                    "dataset_id": str(dataset_id),
                    "schema_version": "",
                    "updated_turn": 0,
                }
        return metas

    def valid_prior_capsule(
        self,
        state: models.ConversationState | None,
        *,
        dataset_id: int | str | None,
        expected_schema_version: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """读取可注入 SubAgent 的上一轮 capsule，版本或 schema 不匹配时作废。"""

        if not state or dataset_id is None:
            return None, {"status": "missing", "reason": "no_state_or_dataset"}
        key = str(dataset_id)
        capsule = (state.subagent_capsules or {}).get(key)
        if not isinstance(capsule, dict):
            return None, {"status": "missing", "reason": "no_capsule", "dataset_id": key}
        version = str(capsule.get("capsule_version") or capsule.get("version") or "")
        if version not in {"1.0", "subagent.v1"}:
            return None, {
                "status": "invalid",
                "reason": "unsupported_capsule_version",
                "dataset_id": key,
                "capsule_version": version,
            }
        capsule_schema = capsule.get("schema_version") or capsule.get("bound_schema_version")
        if expected_schema_version and capsule_schema and str(capsule_schema) != str(expected_schema_version):
            return None, {
                "status": "stale",
                "reason": "schema_version_mismatch",
                "dataset_id": key,
                "capsule_schema_version": capsule_schema,
                "expected_schema_version": expected_schema_version,
            }
        return capsule, {
            "status": "loaded",
            "reason": "capsule_matched",
            "dataset_id": key,
            "capsule_version": version,
            "schema_version": capsule_schema,
        }

    def with_updated_capsule(
        self,
        state: models.ConversationState | None,
        *,
        dataset_id: int | str | None,
        capsule: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """返回写入本轮 out_capsule 后的新胶囊桶。"""

        if not state or dataset_id is None or not isinstance(capsule, dict):
            return None
        capsules = dict(state.subagent_capsules or {})
        capsules[str(dataset_id)] = capsule
        return capsules

    def acquire_turn_lock(
        self,
        *,
        session_id: str,
        lock_owner: str,
        ttl_seconds: int,
    ) -> bool:
        now = datetime.utcnow()
        locked_until = now + timedelta(seconds=ttl_seconds)
        updated = (
            self.db.query(models.ConversationState)
            .filter(models.ConversationState.session_id == session_id)
            .filter(
                or_(
                    models.ConversationState.status == "idle",
                    models.ConversationState.locked_until.is_(None),
                    models.ConversationState.locked_until <= now,
                )
            )
            .update(
                {
                    "status": "turn_pending",
                    "lock_owner": lock_owner,
                    "locked_until": locked_until,
                    "updated_at": now,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return updated == 1

    def release_turn_lock(
        self,
        *,
        session_id: str,
        lock_owner: str | None = None,
    ) -> None:
        query = self.db.query(models.ConversationState).filter(
            models.ConversationState.session_id == session_id
        )
        if lock_owner:
            query = query.filter(
                or_(
                    models.ConversationState.lock_owner == lock_owner,
                    models.ConversationState.lock_owner.is_(None),
                )
            )
        query.update(
            {
                "status": "idle",
                "lock_owner": None,
                "locked_until": None,
                "updated_at": datetime.utcnow(),
            },
            synchronize_session=False,
        )
        self.db.commit()

    def append_completed_turn(
        self,
        *,
        session_id: str,
        question: str,
        answer: str | None,
        conversation_id: int | None,
        active_dataset_id: int | str | None,
        resolved_time_context: dict[str, Any] | None = None,
        pending_clarification: dict[str, Any] | None = None,
        clear_pending_clarification: bool = False,
        subagent_capsules: dict[str, Any] | None = None,
        trace_context: Any | None = None,
    ) -> models.ConversationState:
        state = self.load(session_id)
        if not state:
            raise ValueError(f"ConversationState 不存在: {session_id}")
        now = datetime.utcnow().isoformat()
        messages = list(state.messages or [])
        messages.append(
            {
                "turn": int(state.turn_index or 0) + 1,
                "conversation_id": conversation_id,
                "role": "user",
                "content": question,
                "created_at": now,
            }
        )
        if answer:
            messages.append(
                {
                    "turn": int(state.turn_index or 0) + 1,
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": answer,
                    "created_at": now,
                }
            )
        state.messages = messages
        state.turn_index = int(state.turn_index or 0) + 1
        state.active_dataset_id = str(active_dataset_id) if active_dataset_id is not None else state.active_dataset_id
        if resolved_time_context is not None:
            state.resolved_time_context = resolved_time_context
        if clear_pending_clarification:
            state.pending_clarification = None
        elif pending_clarification is not None:
            state.pending_clarification = pending_clarification
        if subagent_capsules is not None:
            state.subagent_capsules = subagent_capsules
        self._maybe_compact_state(state, trace_context=trace_context)
        state.status = "idle"
        state.lock_owner = None
        state.locked_until = None
        state.updated_at = datetime.utcnow()
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return state

    def _maybe_compact_state(
        self,
        state: models.ConversationState,
        *,
        trace_context: Any | None = None,
    ) -> None:
        """超过阈值后压缩旧消息，最近 2 轮原文保留给展示和兜底。"""

        settings = get_settings()
        if not settings.MULTITURN_COMPACTION_ENABLED:
            return
        messages = list(state.messages or [])
        if not messages:
            return
        estimated_tokens = estimate_text_tokens(
            json.dumps(
                {
                    "summary": state.compacted_summary or "",
                    "messages": messages,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        if estimated_tokens < int(settings.MULTITURN_COMPACTION_TOKEN_THRESHOLD or 8000):
            return
        old_messages, recent_messages = _split_messages_for_compaction(messages, keep_turns=2)
        if not old_messages:
            return
        tracer = get_observability_tracer()
        tracer.start_span(
            trace_context,
            node="context-compaction",
            display_name="context-compaction",
            input_payload={
                "session_id": state.session_id,
                "estimated_tokens": estimated_tokens,
                "threshold": int(settings.MULTITURN_COMPACTION_TOKEN_THRESHOLD or 8000),
                "message_count_before": len(messages),
                "old_message_count": len(old_messages),
                "recent_message_count": len(recent_messages),
                "prompt_name": DATALOGUE_COMPACTION_PROMPT_NAME,
            },
        )
        error: str | None = None
        summary_source = "llm"
        try:
            state.compacted_summary = _compact_old_messages(
                self.db,
                existing_summary=state.compacted_summary,
                old_messages=old_messages,
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            summary_source = "fallback"
            logger.warning("多轮消息压缩失败，使用本地兜底摘要: %s", exc)
            state.compacted_summary = _fallback_compaction_summary(
                state.compacted_summary,
                old_messages,
            )
        state.messages = recent_messages
        tracer.end_span(
            trace_context,
            node="context-compaction",
            output_payload={
                "triggered": True,
                "summary_source": summary_source,
                "summary_length": len(state.compacted_summary or ""),
                "message_count_after": len(recent_messages),
                "kept_turns": 2,
            },
            error=error,
        )

    def reset_stale_turns(self, *, older_than_seconds: int = 300) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=older_than_seconds)
        updated = (
            self.db.query(models.ConversationState)
            .filter(models.ConversationState.status == "turn_pending")
            .filter(
                or_(
                    models.ConversationState.locked_until.is_(None),
                    models.ConversationState.locked_until <= cutoff,
                )
            )
            .update(
                {
                    "status": "idle",
                    "lock_owner": None,
                    "locked_until": None,
                    "updated_at": datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return int(updated or 0)


def pending_clarification_from_final_payload(
    final_payload: dict[str, Any],
    *,
    original_question: str,
) -> dict[str, Any] | None:
    """把 final payload 中的澄清信息压成 ConversationState 可恢复的挂起态。"""

    route_payload = final_payload.get("route_payload") or {}
    if not isinstance(route_payload, dict):
        return None
    kind = route_payload.get("kind")
    if kind not in {"term_conflict_clarification", "manifest_route", "dataset_missing", "dataset_choice", "clarification"}:
        return None
    pending = {
        **route_payload,
        "kind": kind,
        "conversation_id": final_payload.get("conversation_id"),
        "dataset_id": final_payload.get("dataset_id")
        or (final_payload.get("route_decision") or {}).get("dataset_id"),
        "original_question": original_question,
        "created_at": datetime.utcnow().isoformat(),
    }
    if kind == "manifest_route":
        decision = route_payload.get("decision")
        if decision == "no_match":
            pending["kind"] = "dataset_missing"
        elif decision == "ambiguous":
            pending["kind"] = "dataset_choice"
    return pending


def _split_messages_for_compaction(
    messages: list[dict[str, Any]],
    *,
    keep_turns: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 turn 保留最近 N 轮原文，其余进入摘要。"""

    turns = sorted(
        {
            int(item.get("turn"))
            for item in messages
            if isinstance(item, dict) and item.get("turn") is not None
        }
    )
    if not turns:
        keep_count = max(1, keep_turns * 2)
        return messages[:-keep_count], messages[-keep_count:]
    keep_turn_values = set(turns[-keep_turns:])
    old_messages: list[dict[str, Any]] = []
    recent_messages: list[dict[str, Any]] = []
    for item in messages:
        target = recent_messages if int(item.get("turn") or 0) in keep_turn_values else old_messages
        target.append(item)
    return old_messages, recent_messages


def _compact_old_messages(
    db: Session,
    *,
    existing_summary: str | None,
    old_messages: list[dict[str, Any]],
) -> str:
    """调用 Langfuse Prompt Management 中的 datalogue-compaction prompt 压缩旧轮次。"""

    prompt = get_prompt_manager().get_text_prompt(
        DATALOGUE_COMPACTION_PROMPT_NAME,
        fallback=DATALOGUE_COMPACTION_FALLBACK_PROMPT,
    )
    messages_json = json.dumps(old_messages, ensure_ascii=False, default=str)[:24000]
    system = SystemMessage(
        content=prompt.compile(
            existing_summary=existing_summary or "无",
            messages_json=messages_json,
        )
    )
    human = HumanMessage(content="请按要求输出压缩后的会话摘要。")
    response = get_llm(temperature=0.1, role="lead_agent", db=db).invoke([system, human])
    summary = str(getattr(response, "content", response) or "").strip()
    if not summary:
        return _fallback_compaction_summary(existing_summary, old_messages)
    return summary[:4000]


def _fallback_compaction_summary(
    existing_summary: str | None,
    old_messages: list[dict[str, Any]],
) -> str:
    """LLM 不可用时的本地摘要兜底，只保留叙事线和挂起信息。"""

    snippets: list[str] = []
    if existing_summary:
        snippets.append(str(existing_summary).strip())
    for item in old_messages[-8:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        snippets.append(f"{role}: {content[:180]}")
    if not snippets:
        return existing_summary or ""
    return "\n".join(snippets)[-4000:]


def _clarification_response_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if isinstance(payload, dict):
        return {key: value for key, value in payload.items() if value is not None}
    return {}


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").lower())


def _selected_index(response: dict[str, Any], question: str) -> int | None:
    value = response.get("selected_index")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    normalized = _normalize_text(response.get("selected_text") or question)
    for word, index in _ORDINAL_WORDS.items():
        if _normalize_text(word) == normalized or _normalize_text(word) in normalized:
            return index
    match = re.search(r"(?:选择|选|第)?\s*(\d+)", str(response.get("selected_text") or question or ""))
    return int(match.group(1)) if match else None


def _candidate_dataset_id(candidate: dict[str, Any]) -> int | None:
    for key in ("dataset_id", "id", "datasetId"):
        value = candidate.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _resolve_dataset_candidate(
    pending: dict[str, Any],
    response: dict[str, Any],
    question: str,
) -> int | None:
    selected_dataset_id = response.get("selected_dataset_id") or pending.get("selected_dataset_id")
    if selected_dataset_id is not None:
        try:
            return int(selected_dataset_id)
        except (TypeError, ValueError):
            return None
    candidates = [item for item in (pending.get("candidates") or []) if isinstance(item, dict)]
    selected_index = _selected_index(response, question)
    if selected_index is not None:
        for index, candidate in enumerate(candidates, start=1):
            if int(candidate.get("index") or index) == selected_index:
                return _candidate_dataset_id(candidate)
    selected_text = _normalize_text(response.get("selected_text") or question)
    for candidate in candidates:
        aliases = [
            candidate.get("dataset_name"),
            candidate.get("name"),
            candidate.get("title"),
            candidate.get("business_domain"),
        ]
        for alias in aliases:
            alias_text = _normalize_text(alias)
            if alias_text and (alias_text == selected_text or alias_text in selected_text):
                return _candidate_dataset_id(candidate)
    return None


def _looks_like_topic_switch(question: str) -> bool:
    normalized = _normalize_text(question)
    return bool(re.search(r"(换个问题|重新查|重新问|不用了|取消|算了|新问题|另一个问题)", normalized))
