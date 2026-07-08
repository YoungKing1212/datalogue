# ============================================================
# File Name   : title_generator.py
# Description:
#   对话标题自动生成服务。
#
# Responsibilities:
#   - 在第一轮对话完成后，利用 LLM 从用户问题和 AI 回复生成简短标题。
#   - 异步执行，不阻塞主链路。
#
# Author      : yangkai
# Created On  : 2026-07-08
# ============================================================

import logging
import re
import threading

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.models.agentscope_workbench import AgentScopeSession
from app.models.conversation import Conversation
from app.services.llm_config import resolve_llm_config

logger = logging.getLogger(__name__)

_TITLE_GENERATION_ROLE = "title_generation"

# 匹配 thinking 块的正则（<think>...</think> 或类似格式）
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def _strip_thinking_blocks(text: str) -> str:
    """移除可能存在的 thinking 块，避免影响标题生成。"""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _postprocess_title(title: str) -> str:
    """对 LLM 生成的标题进行后处理：移除多余标记、截断长度。"""
    text = title.strip()
    # 移除可能的引号包裹
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()
    # 移除可能的 "Title:" 前缀
    text = re.sub(r"^title\s*[:：]\s*", "", text, flags=re.IGNORECASE).strip()
    # 限制长度
    return text[:80].strip()


def generate_title(
    user_message: str,
    assistant_response: str,
    settings: Settings,
    db: Session,
) -> str | None:
    """调用 LLM 生成对话标题。"""
    try:
        config = resolve_llm_config(settings, role=_TITLE_GENERATION_ROLE, db=db)
        if not config.api_key or not config.base_url:
            logger.warning("标题生成跳过：缺少 LLM 配置")
            return None

        user_message_clean = _strip_thinking_blocks(user_message or "")
        assistant_response_clean = _strip_thinking_blocks(assistant_response or "")

        # 构建 prompt
        prompt = (
            "Generate a short, descriptive title (3-7 words) for a conversation that starts with the following exchange. "
            "The title should capture the main topic or intent. Write the title in Chinese.\n\n"
            "User: {user_message}\n"
            "Assistant: {assistant_response}\n\n"
            "Title:"
        ).format(
            user_message=user_message_clean[:500],
            assistant_response=assistant_response_clean[:500],
        )

        # 调用 LLM
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 100,
                },
            )
            response.raise_for_status()
            result = response.json()

            choices = result.get("choices", [])
            if not choices or not isinstance(choices, list):
                logger.warning("标题生成失败：LLM 返回格式异常")
                return None

            choice = choices[0]
            if not isinstance(choice, dict):
                return None

            message = choice.get("message", {})
            if not isinstance(message, dict):
                return None

            title_text = message.get("content", "")
            if not title_text:
                return None

            title = _postprocess_title(title_text)
            if title:
                logger.debug("标题生成成功：%s", title)
                return title
            return None

    except httpx.TimeoutException:
        logger.warning("标题生成跳过：LLM 请求超时")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("标题生成跳过：LLM 请求失败 %s", e)
        return None
    except Exception:
        logger.exception("标题生成异常")
        return None


def _update_session_title_sync(
    thread_id: str,
    title: str,
    legacy_conversation_id: int | None,
) -> None:
    """同步更新会话标题（在后台线程中执行）。"""
    db = SessionLocal()
    try:
        # 更新 AgentScopeSession
        session = (
            db.query(AgentScopeSession)
            .filter(AgentScopeSession.thread_id == thread_id)
            .one_or_none()
        )
        if session and (session.title is None or session.title == "" or len(session.title) <= 80):
            # 只有当原标题为空或只是简短截取时才更新
            session.title = title[:200]
            db.commit()

        # 如果有关联的 legacy conversation，也更新它
        if legacy_conversation_id:
            conversation = (
                db.query(Conversation)
                .filter(Conversation.id == legacy_conversation_id)
                .one_or_none()
            )
            if conversation:
                conversation.title = title[:200]
                db.commit()

    except Exception:
        logger.exception("更新会话标题失败")
        db.rollback()
    finally:
        db.close()


def maybe_auto_title(
    db: Session,
    thread_id: str,
    user_message: str,
    assistant_response: str,
    legacy_conversation_id: int | None = None,
) -> None:
    """尝试自动生成并更新会话标题（在后台线程中执行）。"""
    # 先检查是否需要生成
    session = (
        db.query(AgentScopeSession).filter(AgentScopeSession.thread_id == thread_id).one_or_none()
    )
    if session and session.title and len(session.title) > 80:
        # 已有较长标题，认为已经生成过
        return

    settings = get_settings()
    title = generate_title(user_message, assistant_response, settings, db)
    if title:
        _update_session_title_sync(thread_id, title, legacy_conversation_id)


def maybe_auto_title_async(
    db: Session,
    thread_id: str,
    user_message: str,
    assistant_response: str,
    legacy_conversation_id: int | None = None,
) -> None:
    """启动后台线程尝试自动生成并更新会话标题。"""
    # 先在当前 DB 会话检查是否需要生成
    session = (
        db.query(AgentScopeSession).filter(AgentScopeSession.thread_id == thread_id).one_or_none()
    )
    if session and session.title and len(session.title) > 80:
        # 已有较长标题，认为已经生成过
        return

    # 启动后台线程
    thread = threading.Thread(
        target=maybe_auto_title,
        args=(db, thread_id, user_message, assistant_response),
        kwargs={"legacy_conversation_id": legacy_conversation_id},
        daemon=True,
        name="auto-title",
    )
    thread.start()
