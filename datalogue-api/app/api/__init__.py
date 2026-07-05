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
    agentscope_control_plane,
    agent_team,
    artifacts,
    conversation,
    datasource,
    dataset,
    messages,
    workbench,
)

router = APIRouter()

router.include_router(datasource.router, prefix="/datasource", tags=["数据源"])
router.include_router(dataset.router, prefix="/dataset", tags=["数据集"])
router.include_router(conversation.router, prefix="/conversation", tags=["对话"])
router.include_router(agent_team.router, prefix="/agent-team", tags=["Agent Team"])
router.include_router(
    agentscope_control_plane.router,
    prefix="/agentscope-control",
    tags=["AgentScope 控制面"],
)
router.include_router(messages.router, prefix="/messages", tags=["消息反馈"])
router.include_router(artifacts.router, prefix="/artifacts", tags=["查询产物"])
router.include_router(workbench.router, prefix="/workbench", tags=["工作台"])
