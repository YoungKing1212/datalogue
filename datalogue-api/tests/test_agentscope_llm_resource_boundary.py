# ============================================================
# File Name   : test_agentscope_llm_resource_boundary.py
# Description:
#   验证 LLM 配置能力已迁移到 AgentScope credential/model 资源。
#
# Responsibilities:
#   - 确认 Datalogue 本地 /api/llm 模型配置 API 已关闭。
#   - 确认旧同步 LLM 工厂只从 AgentScope 默认 credential 解析连接信息。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

from app.core.config import Settings
from app.services.llm_config import DEFAULT_MODEL_CREDENTIAL_ID, resolve_llm_config


class _FakeCredentialResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "credentials": [
                {
                    "id": DEFAULT_MODEL_CREDENTIAL_ID,
                    "data": {
                        "id": DEFAULT_MODEL_CREDENTIAL_ID,
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

    def __init__(self, *, base_url: str, timeout: float):
        self.base_url = base_url
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get(self, path: str, headers: dict | None = None):
        _FakeHttpxClient.last_request = (path, headers or {})
        return _FakeCredentialResponse()


def test_local_llm_config_api_is_removed(client):
    assert client.get("/".join(["", "api", "llm", "models"])).status_code == 404
    assert (
        client.put("/".join(["", "api", "llm", "role" + "-bindings"]), json={"bindings": {"report": 1}}).status_code
        == 404
    )


def test_resolve_llm_config_uses_agentscope_default_credential(monkeypatch):
    monkeypatch.setattr("app.services.llm_config.httpx.Client", _FakeHttpxClient)

    config = resolve_llm_config(
        Settings(
            AGENTSCOPE_SERVICE_BASE_URL="http://agentscope.test",
            OPENAI_API_KEY="sk-env-fallback",
            OPENAI_BASE_URL="https://env.example/v1",
            LLM_MODEL="gpt-4.1-mini",
            LLM_TIMEOUT_SECONDS=45,
        ),
        role="lead_agent",
        db=object(),
    )

    assert _FakeHttpxClient.last_request == ("/credential/", {"X-User-ID": "datalogue-agent-team"})
    assert config.source == "agentscope_credential"
    assert config.credential_id == DEFAULT_MODEL_CREDENTIAL_ID
    assert config.name == "主链默认凭证"
    assert config.provider == "openai_credential"
    assert config.base_url == "https://agentscope.example/v1"
    assert config.api_key == "sk-agentscope"
    assert config.model == "gpt-4.1-mini"
    assert config.request_timeout_seconds == 45
