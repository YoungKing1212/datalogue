# ============================================================
# File Name   : test_agentscope_llm_resource_boundary.py
# Description:
#   验证 Datalogue LLM 配置表与 AgentScope credential 的职责边界。
#
# Responsibilities:
#   - 确认 /api/llm 模型配置 API 保持可用。
#   - 确认运行时默认模型优先读取 llm_model_config，密钥从 AgentScope credential 获取。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

from langchain_core.messages import AIMessage

from app.core.config import Settings
from app.core.models.llm import LLMModelConfig
from app.services.llm_config import credential_id_for_model_config, resolve_llm_config


class _FakeCredentialResponse:
    def __init__(self, credential_id: str):
        self.credential_id = credential_id

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "credentials": [
                {
                    "id": self.credential_id,
                    "data": {
                        "id": self.credential_id,
                        "name": "主链默认凭证",
                        "type": "openai_credential",
                        "api_key": "sk-agentscope",
                        "base_url": "https://agentscope.example/v1",
                    },
                }
            ]
        }


class _FakeHttpxClient:
    last_request: tuple[str, dict] | None = None
    credential_id = ""

    def __init__(self, *, base_url: str, timeout: float):
        self.base_url = base_url
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get(self, path: str, headers: dict | None = None):
        _FakeHttpxClient.last_request = (path, headers or {})
        return _FakeCredentialResponse(self.credential_id)


def _create_llm_config(db_session, *, status: str = "active") -> LLMModelConfig:
    config = LLMModelConfig(
        name="页面配置模型",
        provider="openai-compatible",
        base_url="https://db.example/v1",
        model="db-model",
        status=status,
        description="由设置页维护",
        request_timeout_seconds=45,
        thinking_enabled=True,
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


def test_local_llm_config_api_is_available(client, db_session, monkeypatch):
    config = _create_llm_config(db_session)
    credential_id = credential_id_for_model_config(config.id)

    async def fake_list_credentials():
        return [{"id": credential_id}]

    monkeypatch.setattr("app.api.llm._list_agentscope_credentials", fake_list_credentials)

    response = client.get("/api/llm/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == config.id
    assert payload[0]["credential_id"] == credential_id
    assert payload[0]["model"] == "db-model"
    assert payload[0]["api_key_set"] is True


def test_resolve_llm_config_uses_database_config_before_env(db_session, monkeypatch):
    config = _create_llm_config(db_session)
    _FakeHttpxClient.credential_id = credential_id_for_model_config(config.id)
    monkeypatch.setattr("app.services.llm_config.httpx.Client", _FakeHttpxClient)

    resolved = resolve_llm_config(
        Settings(
            AGENTSCOPE_SERVICE_BASE_URL="http://agentscope.test",
            OPENAI_API_KEY="sk-env-fallback",
            OPENAI_BASE_URL="https://env.example/v1",
            LLM_MODEL="env-model",
            LLM_TIMEOUT_SECONDS=30,
        ),
        role="lead_agent",
        db=db_session,
    )

    assert _FakeHttpxClient.last_request == ("/credential/", {"X-User-ID": "datalogue-agent-team"})
    assert resolved.source == "database"
    assert resolved.credential_id == credential_id_for_model_config(config.id)
    assert resolved.name == "页面配置模型"
    assert resolved.provider == "openai-compatible"
    assert resolved.base_url == "https://db.example/v1"
    assert resolved.model == "db-model"
    assert resolved.api_key == "sk-agentscope"
    assert resolved.request_timeout_seconds == 45
    assert resolved.thinking_enabled is True


def test_llm_model_connection_test_awaits_agentscope_chat_client(client, db_session, monkeypatch):
    config = _create_llm_config(db_session)

    async def fake_api_key_for_config(_config):
        return "sk-test"

    class FakeAgentScopeChatClient:
        called = False

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def ainvoke(self, messages):
            FakeAgentScopeChatClient.called = True
            assert messages[0].content == "请回复 OK，用于连接测试。"
            return AIMessage(content="OK")

    monkeypatch.setattr("app.api.llm._api_key_for_config", fake_api_key_for_config)
    monkeypatch.setattr("app.api.llm.AgentScopeChatClient", FakeAgentScopeChatClient)

    response = client.post(f"/api/llm/models/{config.id}/test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["detail"]["sample"] == "OK"
    assert FakeAgentScopeChatClient.called is True
    db_session.refresh(config)
    assert config.last_test_result["ok"] is True
    assert config.last_error_message is None
