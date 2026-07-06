# ============================================================
# File Name   : test_agentscope_service_factory.py
# Description:
#   校验 Datalogue 嵌入式 AgentScope Service 的构造和挂载行为。
#
# Responsibilities:
#   - 验证 factory 按 Settings 创建 RedisStorage、RedisMessageBus 和 LocalWorkspaceManager。
#   - 验证主 FastAPI 应用只在配置开启时挂载 /agentscope 子应用。
#
# Author      : yangkai
# Created On  : 2026-07-04
# ============================================================

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings


def test_create_embedded_agentscope_app_wires_redis_and_workspace(monkeypatch, tmp_path):
    """factory 只负责装配官方 AgentScope 基础组件，不在构造阶段连接 Redis。"""

    from app.agentscope_service import app_factory

    calls: dict[str, object] = {}

    class FakeRedisStorage:
        def __init__(self, **kwargs):
            calls["storage_kwargs"] = kwargs

    class FakeRedisMessageBus:
        def __init__(self, **kwargs):
            calls["message_bus_kwargs"] = kwargs

    class FakeLocalWorkspaceManager:
        def __init__(self, **kwargs):
            calls["workspace_kwargs"] = kwargs

    def fake_create_app(**kwargs):
        calls["create_app_kwargs"] = kwargs
        return FastAPI(title="fake-agentscope")

    monkeypatch.setattr(app_factory, "RedisStorage", FakeRedisStorage)
    monkeypatch.setattr(app_factory, "RedisMessageBus", FakeRedisMessageBus)
    monkeypatch.setattr(app_factory, "LocalWorkspaceManager", FakeLocalWorkspaceManager)
    monkeypatch.setattr(app_factory, "agentscope_create_app", fake_create_app)

    settings = Settings(
        # 测试逐项 Redis 参数时必须显式关闭连接串，避免本地 .env 覆盖成 URL 优先路径。
        AGENTSCOPE_REDIS_URL=None,
        AGENTSCOPE_REDIS_HOST="redis.internal",
        AGENTSCOPE_REDIS_PORT=6380,
        AGENTSCOPE_REDIS_DB=2,
        AGENTSCOPE_REDIS_PASSWORD="secret",
        AGENTSCOPE_WORKSPACE_BASEDIR=str(tmp_path / "workspaces"),
        AGENTSCOPE_WORKSPACE_TTL_SECONDS=120.5,
    )

    app = app_factory.create_embedded_agentscope_app(settings)

    assert app.title == "fake-agentscope"
    assert calls["storage_kwargs"] == {
        "host": "redis.internal",
        "port": 6380,
        "db": 2,
        "password": "secret",
    }
    assert calls["message_bus_kwargs"] == calls["storage_kwargs"]
    assert calls["workspace_kwargs"] == {
        "basedir": str(tmp_path / "workspaces"),
        "ttl": 120.5,
    }
    create_app_kwargs = calls["create_app_kwargs"]
    assert set(create_app_kwargs) == {
        "storage",
        "message_bus",
        "workspace_manager",
        "extra_credentials",
        "extra_agent_middlewares",
        "extra_agent_tools",
        "custom_subagent_templates",
    }
    assert isinstance(create_app_kwargs["storage"], FakeRedisStorage)
    assert isinstance(create_app_kwargs["message_bus"], FakeRedisMessageBus)
    assert isinstance(create_app_kwargs["workspace_manager"], FakeLocalWorkspaceManager)
    assert [credential.__name__ for credential in create_app_kwargs["extra_credentials"]] == [
        "DatalogueLLMCredential"
    ]
    assert callable(create_app_kwargs["extra_agent_middlewares"])
    assert callable(create_app_kwargs["extra_agent_tools"])
    assert [template.type for template in create_app_kwargs["custom_subagent_templates"]] == [
        "bi",
        "report",
        "python",
        "audit",
    ]


def test_main_mounts_agentscope_service_only_when_enabled(monkeypatch):
    """main.py 按配置开关挂载 AgentScope Service 子应用。"""

    from app import main as main_module

    mounted: dict[str, object] = {}

    def fake_create_embedded_agentscope_app(settings):
        mounted["settings"] = settings
        return FastAPI(title="fake-agentscope")

    monkeypatch.setattr(
        main_module,
        "create_embedded_agentscope_app",
        fake_create_embedded_agentscope_app,
        raising=False,
    )

    root_app = FastAPI()
    disabled = Settings(AGENTSCOPE_SERVICE_ENABLED=False)
    main_module.mount_agentscope_service(root_app, disabled)
    assert all(route.path != "/agentscope" for route in root_app.routes)

    enabled = Settings(
        AGENTSCOPE_SERVICE_ENABLED=True,
        AGENTSCOPE_MOUNT_PATH="/agentscope",
    )
    main_module.mount_agentscope_service(root_app, enabled)

    assert any(route.path == "/agentscope" for route in root_app.routes)
    assert mounted["settings"] is enabled


def test_main_lifespan_enters_mounted_agentscope_service_lifespan(monkeypatch):
    """父应用启动时必须显式进入 AgentScope 子应用 lifespan，确保 Redis 组件完成初始化。"""

    from app import main as main_module

    events: list[str] = []

    @asynccontextmanager
    async def fake_child_lifespan(_app):
        events.append("child-enter")
        yield
        events.append("child-exit")

    def fake_create_embedded_agentscope_app(_settings):
        return FastAPI(title="fake-agentscope", lifespan=fake_child_lifespan)

    monkeypatch.setattr(main_module.Base.metadata, "create_all", lambda **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "create_embedded_agentscope_app",
        fake_create_embedded_agentscope_app,
        raising=False,
    )

    root_app = FastAPI(lifespan=main_module.lifespan)
    main_module.mount_agentscope_service(
        root_app,
        Settings(
            AGENTSCOPE_SERVICE_ENABLED=True,
            AGENTSCOPE_MOUNT_PATH="/agentscope",
        ),
    )

    with TestClient(root_app):
        assert events == ["child-enter"]

    assert events == ["child-enter", "child-exit"]
