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
from dataclasses import dataclass
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
RETRY_CHECKPOINTS_KEY = "retry_checkpoints"
SAFE_RETRY_CHECKPOINT_KINDS = {
    "dataset_confirmed",
    "query_context_ready",
    "artifact_generation_failed",
}
RETRY_CHECKPOINT_TTL_MINUTES = 30
_RETRY_CONTEXT_KEYS = {
    "question",
    "dataset_id",
    "route_decision",
    "time_context",
    "query_plan",
    "result_ref",
    "report_ref",
}
_RETRY_ROUTE_DECISION_KEYS = {
    "decision",
    "dataset_id",
    "dataset_name",
    "manifest_version",
    "bound_schema_version",
    "score",
    "reason",
}
_RETRY_QUERY_PLAN_KEYS = {
    "query_type",
    "execution_strategy",
    "planner_warnings",
    "decision_factors",
    "explanation",
}
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


@dataclass(frozen=True)
class RetryCheckpointRestore:
    """retry checkpoint 恢复结果，区分安全恢复和整任务降级。"""

    retry_scope: str
    checkpoint_ref: str | None = None
    checkpoint_kind: str | None = None
    dataset_id: int | None = None
    question: str | None = None
    context: dict[str, Any] | None = None
    task_id: str | None = None
    permission_scope: str | None = None
    fallback_reason: str | None = None


def session_key(payload_session_id: str | None, conversation_id: int | None) -> str:
    """生成业务多轮 session_id，避免与 Observability session_id 混用。"""

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
        current = capsules.get(THREAD_STATE_KEY)  # 线程级控制面状态与 dataset capsule 分桶隔离。
        thread_state = dict(current) if isinstance(current, dict) else {}
        thread_state.update(patch)  # 浅合并本轮状态补丁，避免覆盖未涉及的控制面字段。
        thread_state = jsonable_encoder(thread_state)  # JSON 列写入前清理 datetime/Decimal 等类型。
        capsules[THREAD_STATE_KEY] = thread_state  # 写回固定线程状态桶，保留其他 dataset capsule。
        state.subagent_capsules = capsules
        state.updated_at = datetime.now(timezone.utc)
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return thread_state

    def register_retry_checkpoint(
        self,
        *,
        session_id: str,
        checkpoint_kind: str,
        user_id: str,
        conversation_id: int | None,
        task_id: str,
        permission_scope: str,
        context: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> str:
        """登记用户可见 retry checkpoint，只保存可安全恢复的业务上下文。"""

        if checkpoint_kind not in SAFE_RETRY_CHECKPOINT_KINDS:
            raise ValueError(f"unsafe retry checkpoint kind: {checkpoint_kind}")
        if not task_id or "/" in str(task_id):
            raise ValueError("retry checkpoint task_id invalid")
        if not permission_scope:
            raise ValueError("retry checkpoint permission_scope required")
        state = self.load_or_create(session_id=session_id, user_id=user_id)
        checkpoint_ref = f"checkpoint://{task_id}/{checkpoint_kind}"
        expires_at = expires_at or (
            datetime.now(timezone.utc) + timedelta(minutes=RETRY_CHECKPOINT_TTL_MINUTES)
        )
        capsules = dict(state.subagent_capsules or {})
        thread_state = dict(capsules.get(THREAD_STATE_KEY) or {})
        checkpoints = dict(thread_state.get(RETRY_CHECKPOINTS_KEY) or {})
        safe_context = _sanitize_retry_checkpoint_context(context)
        record = {
            "checkpoint_ref": checkpoint_ref,
            "checkpoint_kind": checkpoint_kind,
            "user_id": str(user_id),
            "conversation_id": conversation_id,
            "task_id": str(task_id),
            "permission_scope": str(permission_scope),
            "context": safe_context,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        checkpoints[checkpoint_ref] = jsonable_encoder(record)
        if len(checkpoints) > 20:
            checkpoints = dict(list(checkpoints.items())[-20:])  # 只保留最近 checkpoint，避免线程状态无限增长。
        thread_state[RETRY_CHECKPOINTS_KEY] = checkpoints
        capsules[THREAD_STATE_KEY] = thread_state
        state.subagent_capsules = jsonable_encoder(capsules)
        state.updated_at = datetime.now(timezone.utc)
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return checkpoint_ref

    def restore_retry_checkpoint(
        self,
        checkpoint_ref: str | None,
        *,
        user_id: str,
        conversation_id: int | None,
    ) -> RetryCheckpointRestore:
        """按 checkpoint_ref 恢复安全上下文；任一校验失败都降级整任务重试。"""

        if not checkpoint_ref:
            return _retry_fallback(checkpoint_ref, "checkpoint_ref_missing")
        parsed = _parse_retry_checkpoint_ref(checkpoint_ref)
        if parsed is None:
            return _retry_fallback(checkpoint_ref, "checkpoint_ref_invalid")
        task_id, checkpoint_kind = parsed
        if checkpoint_kind not in SAFE_RETRY_CHECKPOINT_KINDS:
            return _retry_fallback(checkpoint_ref, "checkpoint_kind_unsafe")
        record = self._find_retry_checkpoint_record(checkpoint_ref)
        if record is None:
            return _retry_fallback(checkpoint_ref, "checkpoint_not_found")
        if str(record.get("task_id") or "") != task_id or record.get("checkpoint_kind") != checkpoint_kind:
            return _retry_fallback(checkpoint_ref, "checkpoint_ref_mismatch")
        if str(record.get("user_id") or "") != str(user_id):
            return _retry_fallback(checkpoint_ref, "user_mismatch")
        if record.get("conversation_id") is not None and conversation_id is not None:
            if int(record["conversation_id"]) != int(conversation_id):
                return _retry_fallback(checkpoint_ref, "conversation_mismatch")
        permission_scope = str(record.get("permission_scope") or "")
        context = dict(record.get("context") or {})
        dataset_id = _coerce_int_local(context.get("dataset_id"))
        if not permission_scope or (dataset_id is not None and permission_scope != f"dataset:{dataset_id}"):
            return _retry_fallback(checkpoint_ref, "permission_scope_mismatch")
        if _checkpoint_is_expired(record.get("expires_at")):
            return _retry_fallback(checkpoint_ref, "checkpoint_expired")
        question = str(context.get("question") or "").strip() or None
        return RetryCheckpointRestore(
            retry_scope="last_safe_checkpoint",
            checkpoint_ref=checkpoint_ref,
            checkpoint_kind=checkpoint_kind,
            dataset_id=dataset_id,
            question=question,
            context=context,
            task_id=task_id,
            permission_scope=permission_scope,
        )

    def _find_retry_checkpoint_record(self, checkpoint_ref: str) -> dict[str, Any] | None:
        """在 ConversationState 的线程桶中查找 checkpoint，避免暴露底层存储结构。"""

        rows = self.db.query(models.ConversationState).all()
        for state in rows:
            capsules = dict(state.subagent_capsules or {})
            thread_state = capsules.get(THREAD_STATE_KEY)
            if not isinstance(thread_state, dict):
                continue
            checkpoints = thread_state.get(RETRY_CHECKPOINTS_KEY)
            if not isinstance(checkpoints, dict):
                continue
            record = checkpoints.get(checkpoint_ref)
            if isinstance(record, dict):
                return dict(record)
        return None

    def lead_multiturn_context(self, state: models.ConversationState | None) -> dict[str, Any]:
        """组装 LeadAgent 可消费的控制面多轮上下文。"""

        if not state:
            return {}
        messages = list(state.messages or [])
        capsules = dict(state.subagent_capsules or {})
        thread_state = capsules.get(THREAD_STATE_KEY)
        thread_state = thread_state if isinstance(thread_state, dict) else {}
        last_user = next((item for item in reversed(messages) if item.get("role") == "user"), None)  # 只给控制面最近用户问题。
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
            selected_dataset_id = _resolve_dataset_candidate(pending, response, question)  # 恢复 dataset 澄清选择。
            if selected_dataset_id is not None:
                retry_checkpoint = {
                    "kind": "dataset_choice",
                    "checkpoint_ref": response.get("checkpoint_ref") or pending.get("checkpoint_ref"),
                    "original_question": pending.get("original_question"),
                    "candidate_id": response.get("candidate_id") or response.get("selected_dataset_id"),
                    "confirmed_dataset_id": selected_dataset_id,
                }
                return {
                    "status": "resolved",
                    "type": "dataset",
                    "dataset_id": selected_dataset_id,
                    "confirmed_dataset_id": selected_dataset_id,
                    "retry_checkpoint": retry_checkpoint,
                    "original_question": pending.get("original_question"),
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
            injected = dict(response)  # 术语澄清回答要注入原链路，不能当成普通新问题。
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
        updated = (  # 条件 UPDATE 保证并发请求只有一个 turn 能把 idle 推进到 pending。
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
        messages.append(  # 用户消息与 turn_index 同事务提交，保证历史回放和多轮 prompt 对齐。
            {
                "turn": int(state.turn_index or 0) + 1,
                "conversation_id": conversation_id,
                "role": "user",
                "content": question,
                "created_at": now,
            }
        )
        if answer:
            messages.append(  # assistant 消息跟随同一 turn 写入，便于历史回放成对恢复。
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
        self._maybe_compact_state(state, trace_context=trace_context)  # 落库前压缩，写入最近窗口和摘要。
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
    """调用 Observability Prompt Management 中的 datalogue-compaction prompt 压缩旧轮次。"""

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


def _retry_fallback(checkpoint_ref: str | None, reason: str) -> RetryCheckpointRestore:
    return RetryCheckpointRestore(
        retry_scope="whole_task",
        checkpoint_ref=checkpoint_ref,
        fallback_reason=reason,
    )


def _parse_retry_checkpoint_ref(checkpoint_ref: str) -> tuple[str, str] | None:
    prefix = "checkpoint://"
    if not isinstance(checkpoint_ref, str) or not checkpoint_ref.startswith(prefix):
        return None
    rest = checkpoint_ref[len(prefix) :]
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _checkpoint_is_expired(value: Any) -> bool:
    if not value:
        return True
    try:
        if isinstance(value, datetime):
            expires_at = value
        else:
            expires_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)
    except Exception:  # noqa: BLE001
        return True


def _sanitize_retry_checkpoint_context(context: dict[str, Any]) -> dict[str, Any]:
    """清洗 checkpoint 恢复上下文，只保留业务层可恢复字段。"""

    raw = context if isinstance(context, dict) else {}
    safe: dict[str, Any] = {}
    for key in _RETRY_CONTEXT_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if key == "route_decision":
            safe[key] = _pick_retry_dict(value, _RETRY_ROUTE_DECISION_KEYS)
        elif key == "query_plan":
            safe[key] = _pick_retry_dict(value, _RETRY_QUERY_PLAN_KEYS)
        else:
            safe[key] = value
    if "dataset_id" in safe:
        safe["dataset_id"] = _coerce_int_local(safe.get("dataset_id"))
    return jsonable_encoder(safe)


def _pick_retry_dict(value: Any, allowed_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    picked = {key: value.get(key) for key in allowed_keys if key in value}
    return {key: val for key, val in picked.items() if val is not None}


def _coerce_int_local(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    selected_dataset_id = (
        response.get("selected_dataset_id")
        or response.get("candidate_id")
        or pending.get("selected_dataset_id")
    )
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
