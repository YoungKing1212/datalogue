# ============================================================
# File Name   : main.py
# Description:
#   Datalogue API 的 FastAPI 应用入口。
#
# Responsibilities:
#   - 配置应用生命周期、跨域和日志。
#   - 挂载 API 路由和健康检查端点。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api import router as api_router
from app.agentscope_service import create_embedded_agentscope_app
from app.middlewares.tracing import (
    configure_agentscope_otel,
    shutdown_agentscope_otel,
)

# 初始化带颜色的日志，可选持久化到文件
settings = get_settings()
setup_logging(
    level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_agentscope_otel()
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        shutdown_agentscope_otel()


app = FastAPI(
    title="Datalogue API",
    description="数语 AI 原生智能问数平台后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


def mount_agentscope_service(target_app: FastAPI, app_settings) -> None:
    """按配置把 AgentScope Service 子应用挂到主应用下。"""

    if not app_settings.AGENTSCOPE_SERVICE_ENABLED:
        return

    mount_path = app_settings.AGENTSCOPE_MOUNT_PATH
    if any(route.path == mount_path for route in target_app.routes):
        # 测试或 reload 场景可能重复调用，避免重复挂载同一路径。
        return

    target_app.mount(
        mount_path,
        create_embedded_agentscope_app(app_settings),
        name="agentscope",
    )


mount_agentscope_service(app, settings)


@app.get("/health")
async def health():
    return {"status": "ok"}
