# ============================================================
# File Name   : test_llm_config.py
# Description:
#   LLM 模型配置管理和 AgentScope 执行适配测试。
#
# Responsibilities:
#   - 验证模型配置 API 不泄露密钥且不再暴露角色绑定。
#   - 验证 get_llm 通过 AgentScope 适配器创建客户端。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from agentscope.message._block import TextBlock
from agentscope.model._model_response import ChatResponse
from app.core.config import Settings
from app.core.security import encrypt_password
from app.models import LLMModelConfig
from app.services.llm_config import resolve_llm_config


class FakeAgentScopeCredentialClient:
    credentials: dict[str, dict] = {}

    def __init__(self, *, base_url: str, **_kwargs):
        self.base_url = base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def list_credentials(self):
        return list(self.credentials.values())

    async def upsert_openai_credential(self, *, credential_id: str, name: str, api_key: str, base_url: str | None):
        self.credentials[credential_id] = {
            "id": credential_id,
            "data": {
                "id": credential_id,
                "name": name,
                "type": "openai_credential",
                "api_key": api_key,
                "base_url": base_url,
            },
        }
        return credential_id

    async def update_credential(self, credential_id: str, payload: dict):
        data = self.credentials.setdefault(credential_id, {"id": credential_id, "data": {"id": credential_id}})["data"]
        data.update(payload.get("data") or {})
        return {"credential_id": credential_id}

    async def delete_credential(self, credential_id: str):
        self.credentials.pop(credential_id, None)
        return {"deleted": True}


@pytest.fixture(autouse=True)
def _isolate_live_agentscope_credentials(monkeypatch):
    """单测只使用测试内的 credential fake，避免读取本机真实 AgentScope 状态。"""

    monkeypatch.setattr("app.services.llm_config._fetch_agentscope_credentials", lambda _settings: [])


def test_llm_model_crud_masks_api_key(client, db_session, monkeypatch):
    """模型配置 API 不返回明文 Key，且新密钥只写入 AgentScope credential。"""
    FakeAgentScopeCredentialClient.credentials = {}
    monkeypatch.setattr("app.api.llm.AgentScopeServiceClient", FakeAgentScopeCredentialClient)
    payload = {
        "name": "AgentScope SQL",
        "provider": "openai-compatible",
        "base_url": "http://localhost:4000/v1",
        "model": "datalogue-sql",
        "api_key": "sk-secret",
        "status": "active",
        "request_timeout_seconds": 45,
        "thinking_enabled": True,
    }
    resp = client.post("/api/llm/models", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key" not in data
    assert data["api_key_set"] is True
    assert data["thinking_enabled"] is True
    assert data["credential_id"] == f"datalogue-openai-compatible-model-{data['id']}"

    config = db_session.get(LLMModelConfig, data["id"])
    assert config is not None
    assert config.api_key_enc is None
    assert config.thinking_enabled is True
    assert FakeAgentScopeCredentialClient.credentials[data["credential_id"]]["data"]["api_key"] == "sk-secret"

    get_resp = client.get(f"/api/llm/models/{data['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["credential_id"] == data["credential_id"]
    assert get_resp.json()["api_key_set"] is True

    resp = client.put(
        f"/api/llm/models/{data['id']}",
        json={"name": "AgentScope SQL v2", "api_key": "", "thinking_enabled": False},
    )
    assert resp.status_code == 200
    db_session.refresh(config)
    assert config.name == "AgentScope SQL v2"
    assert config.api_key_enc is None
    assert FakeAgentScopeCredentialClient.credentials[data["credential_id"]]["data"]["api_key"] == "sk-secret"
    assert config.thinking_enabled is False


def test_llm_model_create_without_key_keeps_credential_unset(client, db_session, monkeypatch):
    """未填写 Key 的模型配置只能保存为投影，不能创建空 AgentScope credential。"""
    FakeAgentScopeCredentialClient.credentials = {}
    monkeypatch.setattr("app.api.llm.AgentScopeServiceClient", FakeAgentScopeCredentialClient)

    resp = client.post(
        "/api/llm/models",
        json={
            "name": "Draft Model",
            "provider": "openai-compatible",
            "base_url": "http://localhost:4000/v1",
            "model": "draft-model",
            "api_key": "",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key_set"] is False
    assert data["credential_id"] not in FakeAgentScopeCredentialClient.credentials
    config = db_session.get(LLMModelConfig, data["id"])
    assert config is not None
    assert config.api_key_enc is None


def test_llm_model_list_migrates_legacy_key_to_agentscope(client, db_session, monkeypatch):
    """历史 DB 加密 Key 应在列表接口被补注册到 AgentScope，并清空本地列。"""
    FakeAgentScopeCredentialClient.credentials = {}
    monkeypatch.setattr("app.api.llm.AgentScopeServiceClient", FakeAgentScopeCredentialClient)
    config = LLMModelConfig(
        name="Legacy Model",
        provider="openai-compatible",
        base_url="http://localhost:4000/v1",
        model="legacy-model",
        api_key_enc=encrypt_password("sk-legacy"),
        status="active",
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)

    resp = client.get("/api/llm/models")

    assert resp.status_code == 200
    row = next(item for item in resp.json() if item["id"] == config.id)
    credential_id = row["credential_id"]
    assert row["api_key_set"] is True
    assert FakeAgentScopeCredentialClient.credentials[credential_id]["data"]["api_key"] == "sk-legacy"
    db_session.refresh(config)
    assert config.api_key_enc is None


def test_role_binding_api_removed(client, monkeypatch):
    """模型配置功能保留，但 role binding API 不再存在。"""
    FakeAgentScopeCredentialClient.credentials = {}
    monkeypatch.setattr("app.api.llm.AgentScopeServiceClient", FakeAgentScopeCredentialClient)
    model_resp = client.post(
        "/api/llm/models",
        json={
            "name": "Report Model",
            "provider": "openai-compatible",
            "base_url": "http://localhost:4000/v1",
            "model": "report-model",
            "api_key": "sk-report",
        },
    )
    assert model_resp.status_code == 200

    assert client.get("/api/llm/roles").status_code == 404
    assert client.get("/api/llm/role-bindings").status_code == 404
    assert client.put("/api/llm/role-bindings", json={"bindings": {"report": 1}}).status_code == 404


def test_resolve_llm_config_uses_default_active_config_without_role_binding(db_session):
    """未显式选择模型时，不读 role binding，只使用默认启用配置或环境变量。"""
    settings = Settings(
        OPENAI_API_KEY="env-key",
        OPENAI_BASE_URL="https://env.example/v1",
        LLM_MODEL="env-model",
    )
    env_config = resolve_llm_config(settings, role="report", db=db_session)
    assert env_config.source == "env"
    assert env_config.model == "env-model"
    assert env_config.thinking_enabled is False

    first_model = LLMModelConfig(
        name="First DB",
        provider="openai-compatible",
        base_url="http://localhost:4000/v1",
        model="first-model",
        api_key_enc=None,
        status="active",
        thinking_enabled=False,
    )
    latest_model = LLMModelConfig(
        name="Latest DB",
        provider="openai-compatible",
        base_url="http://localhost:4000/v1",
        model="latest-model",
        api_key_enc=None,
        status="active",
        thinking_enabled=True,
    )
    db_session.add_all([first_model, latest_model])
    db_session.commit()

    report_config = resolve_llm_config(settings, role="report", db=db_session)
    assert report_config.model == "latest-model"
    assert report_config.thinking_enabled is True


def test_resolve_llm_config_explicit_model_config_id_overrides_default(db_session):
    """聊天框显式选择模型时，应只覆盖本轮模型配置，不依赖角色绑定。"""
    settings = Settings(
        OPENAI_API_KEY="env-key",
        OPENAI_BASE_URL="https://env.example/v1",
        LLM_MODEL="env-model",
    )
    default_model = LLMModelConfig(
        name="Default DB",
        provider="openai-compatible",
        base_url="http://localhost:4000/v1",
        model="default-model",
        api_key_enc=None,
        status="active",
    )
    selected_model = LLMModelConfig(
        name="Selected DB",
        provider="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        api_key_enc=encrypt_password("sk-selected"),
        status="active",
        thinking_enabled=True,
    )
    db_session.add_all([selected_model, default_model])
    db_session.commit()

    resolved = resolve_llm_config(
        settings,
        role="lead_agent",
        db=db_session,
        model_config_id=selected_model.id,
    )

    assert resolved.role == "lead_agent"
    assert resolved.name == "Selected DB"
    assert resolved.model == "qwen-plus"
    assert resolved.api_key == "sk-selected"
    assert resolved.thinking_enabled is True


def test_get_llm_uses_database_role_config(db_session):
    """get_llm 应使用默认启用数据库配置创建 AgentScope 客户端。"""
    from app.core.security import encrypt_password
    from app.graph.llm import AgentScopeChatClient, ROLE_CALL_POLICIES, get_llm

    model = LLMModelConfig(
        name="Intent DB",
        provider="qwen",
        base_url="http://localhost:4000/v1",
        model="qwen-plus",
        api_key_enc=encrypt_password("sk-intent"),
        status="active",
        request_timeout_seconds=12,
        thinking_enabled=False,
    )
    db_session.add(model)
    db_session.commit()

    llm = get_llm(temperature=0.2, role="intent", db=db_session)

    assert isinstance(llm, AgentScopeChatClient)
    assert llm.provider == "qwen"
    assert llm.model == "qwen-plus"
    assert llm.api_key == "sk-intent"
    assert llm.api_base == "http://localhost:4000/v1"
    assert llm.temperature == 0.2
    assert llm.timeout == 12
    assert llm.model_kwargs == {"extra_body": {"enable_thinking": False}}
    assert llm.max_tokens == ROLE_CALL_POLICIES["intent"]["max_tokens"]
    assert llm.response_format == {"type": "json_object"}
    assert llm.datalogue_call_policy["structured_output"] is True
    assert llm.datalogue_thinking_enabled is False


def test_get_llm_keeps_thinking_when_enabled(db_session):
    """模型配置开启 Think 后，不应再下发禁用思考参数。"""
    from app.core.security import encrypt_password
    from app.graph.llm import AgentScopeChatClient, get_llm

    model = LLMModelConfig(
        name="Thinking DB",
        provider="qwen",
        base_url="http://localhost:4000/v1",
        model="qwen-plus",
        api_key_enc=encrypt_password("sk-thinking"),
        status="active",
        thinking_enabled=True,
    )
    db_session.add(model)
    db_session.commit()

    llm = get_llm(role="report", db=db_session)

    assert isinstance(llm, AgentScopeChatClient)
    assert llm.model == "qwen-plus"
    assert llm.model_kwargs == {}
    assert llm.response_format is None
    assert llm.datalogue_thinking_enabled is True


def test_get_llm_uses_agentscope_openai_compatible_adapter(db_session):
    """历史 openai-compatible 配置应映射到 AgentScope 适配器。"""
    from app.core.security import encrypt_password
    from app.graph.llm import AgentScopeChatClient, get_llm

    model = LLMModelConfig(
        name="AgentScope MiniMax",
        provider="openai-compatible",
        base_url="https://api.minimaxi.com/v1",
        model="MiniMax-M3",
        api_key_enc=encrypt_password("sk-minimax"),
        status="active",
        request_timeout_seconds=30,
        thinking_enabled=False,
    )
    db_session.add(model)
    db_session.commit()

    llm = get_llm(temperature=0.1, role="lead_agent", db=db_session)

    assert isinstance(llm, AgentScopeChatClient)
    assert llm.model == "MiniMax-M3"
    assert llm.api_base == "https://api.minimaxi.com/v1"
    assert llm.api_key == "sk-minimax"
    assert llm.temperature == 0.1
    assert llm.timeout == 30
    assert llm.datalogue_thinking_enabled is False


def test_agentscope_chat_client_astream_yields_chunks(monkeypatch):
    """AgentScope 适配器应兼容报告节点使用的 astream 接口。"""
    from app.graph.llm import AgentScopeChatClient
    from langchain_core.messages import HumanMessage

    async def chunks():
        yield ChatResponse(content=[TextBlock(text="查询")], is_last=False)
        yield ChatResponse(content=[TextBlock(text="完成")], is_last=True)

    class FakeAgentScopeModel:
        def __call__(self, messages):
            assert messages[0].role == "user"
            return chunks()

    client = AgentScopeChatClient(
        provider="openai-compatible",
        model="test-model",
        api_key="sk-test",
        api_base="http://localhost:4000/v1",
        temperature=0.1,
        timeout=12,
        model_kwargs={},
        thinking_enabled=False,
    )
    monkeypatch.setattr(client, "_build_model", lambda stream: FakeAgentScopeModel())

    async def collect():
        return [chunk async for chunk in client.astream([HumanMessage(content="生成报告")])]

    streamed_chunks = asyncio.run(collect())

    assert [chunk.content for chunk in streamed_chunks] == ["查询", "完成"]


def test_llm_model_test_endpoint_persists_result(client, db_session, monkeypatch):
    """测试连接接口应通过 AgentScope credential 取 Key，并保存最近一次测试结果。"""
    FakeAgentScopeCredentialClient.credentials = {}
    monkeypatch.setattr("app.api.llm.AgentScopeServiceClient", FakeAgentScopeCredentialClient)
    model_resp = client.post(
        "/api/llm/models",
        json={
            "name": "Test Model",
            "provider": "openai-compatible",
            "base_url": "http://localhost:4000/v1",
            "model": "test-model",
            "api_key": "sk-test",
            "thinking_enabled": False,
        },
    )
    model_id = model_resp.json()["id"]
    credential_id = model_resp.json()["credential_id"]
    fake_response = MagicMock()
    fake_response.content = "OK"

    with patch("app.api.llm.AgentScopeChatClient") as agentscope_client:
        agentscope_client.return_value.invoke.return_value = fake_response
        resp = client.post(f"/api/llm/models/{model_id}/test", json={})

    kwargs = agentscope_client.call_args.kwargs
    assert kwargs["provider"] == "openai-compatible"
    assert kwargs["model"] == "test-model"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["api_base"] == "http://localhost:4000/v1"
    assert kwargs["model_kwargs"] == {}
    assert kwargs["max_tokens"] is None
    assert kwargs["response_format"] is None
    assert kwargs["thinking_enabled"] is False
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    config = db_session.get(LLMModelConfig, model_id)
    assert config.api_key_enc is None
    assert FakeAgentScopeCredentialClient.credentials[credential_id]["data"]["api_key"] == "sk-test"
    assert config.last_test_result["ok"] is True
    assert config.last_error_message is None
