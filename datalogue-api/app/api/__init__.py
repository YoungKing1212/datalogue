# ============================================================
# File Name   : __init__.py
# Description:
#   聚合 API 路由。
#
# Responsibilities:
#   - 注册聊天、数据集、数据源和会话路由。
#   - 向 FastAPI 应用暴露统一 router。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from fastapi import APIRouter

from app.api import (
    agentic_shell,
    artifacts,
    bi_agent,
    chat,
    conversation,
    datasource,
    dataset,
    internal_subagent,
    llm,
    messages,
    workbench,
)

router = APIRouter()

router.include_router(datasource.router, prefix="/datasource", tags=["数据源"])
router.include_router(dataset.router, prefix="/dataset", tags=["数据集"])
router.include_router(conversation.router, prefix="/conversation", tags=["对话"])
router.include_router(chat.router, prefix="/chat", tags=["问数"])
router.include_router(agentic_shell.router, prefix="/agentic-shell", tags=["Agentic Shell"])
router.include_router(llm.router, prefix="/llm", tags=["LLM 配置"])
router.include_router(messages.router, prefix="/messages", tags=["消息反馈"])
router.include_router(internal_subagent.router, prefix="/internal", tags=["内部 SubAgent"])
router.include_router(artifacts.router, prefix="/artifacts", tags=["查询产物"])
router.include_router(workbench.router, prefix="/workbench", tags=["工作台"])
router.include_router(bi_agent.router, prefix="/bi-agent", tags=["BI Agent"])
