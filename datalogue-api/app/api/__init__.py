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

from fastapi import APIRouter, Depends

from app.api import (
    agentscope_control_plane,
    agent_team,
    artifacts,
    auth,
    conversation,
    datasource,
    dataset,
    llm,
    messages,
    navigation,
    workbench,
)
from app.api.deps import require_api_admin, require_api_user

router = APIRouter()

# 登录、刷新令牌和退出登录必须允许在 access token 缺失或失效时调用。
router.include_router(auth.public_router, prefix="/auth", tags=["认证"])

# 业务接口统一经过登录拦截，新增路由应默认注册到该路由器，避免遗漏单接口鉴权。
protected_router = APIRouter(dependencies=[Depends(require_api_user)])
protected_router.include_router(auth.router, prefix="/auth", tags=["认证"])
protected_router.include_router(datasource.router, prefix="/datasource", tags=["数据源"])
protected_router.include_router(navigation.router, prefix="/navigation", tags=["导航统计"])
protected_router.include_router(dataset.router, prefix="/dataset", tags=["数据集"])
protected_router.include_router(conversation.router, prefix="/conversation", tags=["对话"])
protected_router.include_router(agent_team.router, prefix="/agent-team", tags=["Agent Team"])
protected_router.include_router(messages.router, prefix="/messages", tags=["消息反馈"])
protected_router.include_router(artifacts.router, prefix="/artifacts", tags=["查询产物"])
protected_router.include_router(workbench.router, prefix="/workbench", tags=["工作台"])

# LLM 密钥、模型测试和 AgentScope credential 属于系统级配置，只允许管理员访问。
admin_router = APIRouter(dependencies=[Depends(require_api_admin)])
admin_router.include_router(llm.router, prefix="/llm", tags=["LLM 配置"])
admin_router.include_router(
    agentscope_control_plane.router,
    prefix="/agentscope-control",
    tags=["AgentScope 控制面"],
)

router.include_router(protected_router)
router.include_router(admin_router)
