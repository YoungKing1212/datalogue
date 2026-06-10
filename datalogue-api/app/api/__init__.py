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

from app.api import datasource, dataset, conversation, chat, llm

router = APIRouter()

router.include_router(datasource.router, prefix="/datasource", tags=["数据源"])
router.include_router(dataset.router, prefix="/dataset", tags=["数据集"])
router.include_router(conversation.router, prefix="/conversation", tags=["对话"])
router.include_router(chat.router, prefix="/chat", tags=["问数"])
router.include_router(llm.router, prefix="/llm", tags=["LLM 配置"])
