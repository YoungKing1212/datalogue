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

from contextlib import AsyncExitStack, asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base, SessionLocal
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.models import User
from app.core.security import hash_password
from app.api import router as api_router
from app.runtime.engine import create_embedded_runtime_app
from app.runtime.engine.otel_setup import setup_runtime_tracing

# 初始化带颜色的日志，可选持久化到文件
settings = get_settings()
logger = logging.getLogger(__name__)


def _parse_cors_origins(raw_origins: str) -> list[str]:
    origins = [item.strip() for item in (raw_origins or "").split(",") if item.strip()]
    if origins:
        return origins
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


def _bootstrap_admin_if_needed() -> None:
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.BOOTSTRAP_ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=settings.BOOTSTRAP_ADMIN_USERNAME,
                full_name="系统管理员",
                hashed_password=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
                role="admin",
                is_superuser=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.warning(
                "Bootstrap admin created: username=%s. Please change password immediately.",
                settings.BOOTSTRAP_ADMIN_USERNAME,
            )
            return

        # Bootstrap 只负责首次建号；已有账号可能已由管理员改过密码或权限，启动流程不能覆盖。
        logger.info(
            "Bootstrap admin already exists: username=%s.",
            settings.BOOTSTRAP_ADMIN_USERNAME,
        )
    finally:
        db.close()


setup_logging(
    level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _bootstrap_admin_if_needed()
    # OTel 必须在 AgentScope 子应用生命周期前初始化，否则 TracingMiddleware 会按 no-op 透传。
    setup_runtime_tracing(settings)
    async with AsyncExitStack() as stack:
        for child_app in getattr(app.state, "managed_lifespan_apps", []):
            # Starlette 挂载子应用不会自动进入子应用 lifespan；AgentScope 的 Redis 连接池依赖这里显式进入。
            await stack.enter_async_context(child_app.router.lifespan_context(child_app))
        yield


app = FastAPI(
    title="Datalogue API",
    description="数语 AI 原生智能问数平台后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(settings.CORS_ALLOW_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


def mount_agentscope_service(root_app: FastAPI, app_settings) -> None:
    """按配置把官方 AgentScope Service 挂载为 Datalogue 子应用。"""

    if not app_settings.AGENTSCOPE_SERVICE_ENABLED:
        return

    mount_path = app_settings.AGENTSCOPE_MOUNT_PATH.rstrip("/") or "/agentscope"
    agentscope_app = create_embedded_runtime_app(app_settings)
    managed_lifespan_apps = list(getattr(root_app.state, "managed_lifespan_apps", []))
    managed_lifespan_apps.append(agentscope_app)
    root_app.state.managed_lifespan_apps = managed_lifespan_apps
    # 子应用只在配置开启时创建；避免测试或禁用环境提前初始化 AgentScope 外部依赖。
    root_app.mount(
        mount_path,
        agentscope_app,
        name="agentscope_service",
    )


mount_agentscope_service(app, settings)


@app.get("/health")
async def health():
    return {"status": "ok"}
