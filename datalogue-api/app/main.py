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

# 初始化带颜色的日志
settings = get_settings()
setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


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


@app.get("/health")
async def health():
    return {"status": "ok"}
