# ============================================================
# File Name   : test_agentscope_control_plane_api.py
# Description:
#   AgentScope credential/model 控制面代理 API 测试。
#
# Responsibilities:
#   - 确认 Datalogue 只代理 AgentScope Service 的 credential/model 资源。
#   - 防止新模型控制面回写旧本地模型配置或角色绑定。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from app.core.models.llm import LLMModelConfig
from app.core.security import decrypt_password, encrypt_password


class FakeAgentScopeControlPlaneClient:
    calls: list[tuple[str, object]] = []

    def __init__(self, *, base_url: str):
        self.base_url = base_url

    async def __aenter__(self):
        self.calls.append(("enter", self.base_url))
        return self

    async def __aexit__(self, *_exc: object):
        self.calls.append(("exit", None))

    async def list_credential_schemas(self):
        self.calls.append(("list_credential_schemas", None))
        return {
            "openai_credential": {
                "title": "OpenAI API",
                "properties": {"api_key": {"type": "string"}},
            }
        }

    async def list_credentials(self):
        self.calls.append(("list_credentials", None))
        # AgentScope 列表接口不会回传明文密钥，PATCH 必须从 Datalogue 本地密文恢复。
        return [
            {
                "id": "cred-1",
                "data": {
                    "name": "默认凭证",
                    "type": "openai_credential",
                    "base_url": "https://example.test/v1",
                    "model": "gpt-test",
                },
            }
        ]

    async def create_credential(self, payload):
        self.calls.append(("create_credential", payload))
        return {"credential_id": "cred-1", "data": {"api_key": "sk-created"}}

    async def update_credential(self, credential_id, payload):
        self.calls.append(("update_credential", (credential_id, payload)))
        return {"credential_id": credential_id, "updated": True, "data": {"api_key": "sk-updated"}}

    async def delete_credential(self, credential_id):
        self.calls.append(("delete_credential", credential_id))
        return {"deleted": True}

    async def list_models(self, *, provider: str):
        self.calls.append(("list_models", provider))
        return [{"name": "gpt-4.1", "model_type": "chat"}]


def _contains_api_key_field(value) -> bool:
    if isinstance(value, dict):
        return "api_key" in value or any(_contains_api_key_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_api_key_field(item) for item in value)
    return False


@pytest.fixture(autouse=True)
def _patch_agentscope_client(monkeypatch):
    FakeAgentScopeControlPlaneClient.calls = []
    monkeypatch.setattr(
        "app.api.agentscope_control_plane.AgentScopeServiceClient",
        FakeAgentScopeControlPlaneClient,
    )


def test_agentscope_control_plane_proxies_credential_schemas(client):
    response = client.get("/api/agentscope-control/credential/schemas")

    assert response.status_code == 200
    assert response.json()["openai_credential"]["title"] == "OpenAI API"
    assert ("list_credential_schemas", None) in FakeAgentScopeControlPlaneClient.calls


def test_agentscope_control_plane_proxies_credential_crud(client):
    create_response = client.post(
        "/api/agentscope-control/credentials",
        json={
            "data": {
                "name": "默认凭证",
                "type": "openai_credential",
                "api_key": "sk-test",
                "base_url": "https://example.test/v1",
                "model": "gpt-test",
            }
        },
    )
    list_response = client.get("/api/agentscope-control/credentials")
    update_response = client.patch(
        "/api/agentscope-control/credentials/cred-1",
        json={"data": {"name": "更新后的凭证"}},
    )
    delete_response = client.delete("/api/agentscope-control/credentials/cred-1")

    assert list_response.json() == [
        {
            "id": "cred-1",
            "data": {
                "name": "默认凭证",
                "type": "openai_credential",
                "base_url": "https://example.test/v1",
                "model": "gpt-test",
                "id": "cred-1",
                "config_id": list_response.json()[0]["data"]["config_id"],
                "status": "active",
                "description": None,
                "request_timeout_seconds": 60.0,
                "thinking_enabled": False,
                "api_key_set": True,
                "last_test_result": None,
                "last_error_message": None,
            },
        }
    ]
    assert create_response.json() == {"credential_id": "cred-1", "data": {"api_key_set": True}}
    assert update_response.json() == {
        "credential_id": "cred-1",
        "updated": True,
        "data": {"api_key_set": True},
    }
    assert delete_response.json() == {"deleted": True}
    assert _contains_api_key_field(list_response.json()) is False
    assert _contains_api_key_field(create_response.json()) is False
    assert _contains_api_key_field(update_response.json()) is False
    assert (
        "create_credential",
        {
            "data": {
                "name": "默认凭证",
                "type": "openai_credential",
                "api_key": "sk-test",
                "base_url": "https://example.test/v1",
                "model": "gpt-test",
            }
        },
    ) in (FakeAgentScopeControlPlaneClient.calls)
    # PATCH 语义收敛为 partial update：Datalogue 会先读现存 credential，把缺失字段
    # （尤其是 api_key/type）用现值兜底再回写，避免前端脱敏表单误清空 key。
    assert (
        "update_credential",
        (
            "cred-1",
            {
                "data": {
                    "name": "更新后的凭证",
                    "type": "openai_credential",
                    "api_key": "sk-test",
                    "base_url": "https://example.test/v1",
                    "model": "gpt-test",
                },
            },
        ),
    ) in FakeAgentScopeControlPlaneClient.calls
    assert ("delete_credential", "cred-1") in FakeAgentScopeControlPlaneClient.calls


def test_agentscope_control_plane_persists_api_key_as_local_ciphertext(client, db_session):
    """新增 credential 时只允许在本地落 AES-GCM 密文，接口响应不得泄露明文。"""

    response = client.post(
        "/api/agentscope-control/credentials",
        json={
            "data": {
                "name": "DeepSeek 主模型",
                "type": "deepseek_credential",
                "api_key": "sk-local-source-of-truth",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-v4-pro",
            }
        },
    )

    assert response.status_code == 200
    config = db_session.query(LLMModelConfig).filter_by(credential_id="cred-1").one()
    assert config.api_key_enc != "sk-local-source-of-truth"
    assert decrypt_password(config.api_key_enc) == "sk-local-source-of-truth"
    assert "sk-local-source-of-truth" not in response.text


def test_agentscope_control_plane_patch_updates_local_ciphertext(client, db_session):
    """用户显式更换 API Key 后，本地密文与 AgentScope 运行副本必须同步更新。"""

    config = LLMModelConfig(
        credential_id="cred-1",
        credential_type="openai_credential",
        name="默认凭证",
        provider="openai-compatible",
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key_enc="",
    )
    db_session.add(config)
    db_session.commit()

    response = client.patch(
        "/api/agentscope-control/credentials/cred-1",
        json={"data": {"api_key": "sk-rotated-local-key"}},
    )

    assert response.status_code == 200
    db_session.refresh(config)
    assert decrypt_password(config.api_key_enc) == "sk-rotated-local-key"
    assert "sk-rotated-local-key" not in response.text


def test_agentscope_control_plane_patch_returns_404_when_credential_missing(client):
    response = client.patch(
        "/api/agentscope-control/credentials/missing-id",
        json={"data": {"name": "any"}},
    )

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_agentscope_control_plane_patch_preserves_existing_api_key(client, db_session):
    config = LLMModelConfig(
        credential_id="cred-1",
        credential_type="openai_credential",
        name="默认凭证",
        provider="openai-compatible",
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key_enc=encrypt_password("sk-local-preserved"),
    )
    db_session.add(config)
    db_session.commit()

    response = client.patch(
        "/api/agentscope-control/credentials/cred-1",
        json={"data": {"description": "只改描述，不重填 key"}},
    )

    assert response.status_code == 200
    # 前端只改描述、没送 api_key → Datalogue 从本地 AES-GCM 密文恢复密钥。
    matching = [
        call
        for call in FakeAgentScopeControlPlaneClient.calls
        if call[0] == "update_credential" and call[1][0] == "cred-1"
    ]
    assert matching, "expected update_credential to be invoked"
    _, (_, forwarded_payload) = matching[-1]
    forwarded_data = forwarded_payload["data"]
    assert forwarded_data["api_key"] == "sk-local-preserved"
    assert forwarded_data["description"] == "只改描述，不重填 key"


def test_agentscope_control_plane_patch_drops_api_key_when_type_changes(client):
    response = client.patch(
        "/api/agentscope-control/credentials/cred-1",
        json={"data": {"type": "deepseek_credential"}},
    )

    assert response.status_code == 200
    # 切换 credential type（provider 变了）→ 旧 api_key 立即作废，由前端提示用户重填。
    matching = [
        call
        for call in FakeAgentScopeControlPlaneClient.calls
        if call[0] == "update_credential" and call[1][0] == "cred-1"
    ]
    assert matching, "expected update_credential to be invoked"
    _, (_, forwarded_payload) = matching[-1]
    forwarded_data = forwarded_payload["data"]
    assert "api_key" not in forwarded_data
    assert forwarded_data["type"] == "deepseek_credential"


def test_agentscope_control_plane_proxies_models(client):
    response = client.get("/api/agentscope-control/model?provider=openai_credential")

    assert response.status_code == 200
    assert response.json() == [{"name": "gpt-4.1", "model_type": "chat"}]
    assert ("list_models", "openai_credential") in FakeAgentScopeControlPlaneClient.calls


def test_agentscope_control_plane_tests_selected_model(client, db_session, monkeypatch):
    """模型列表里的测试按钮必须使用本地密钥真实调用所选模型，并持久化结果。"""

    config = LLMModelConfig(
        credential_id="cred-1",
        credential_type="openai_credential",
        name="默认凭证",
        provider="openai-compatible",
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key_enc=encrypt_password("sk-local-test"),
        request_timeout_seconds=45,
    )
    db_session.add(config)
    db_session.commit()

    class FakeAgentScopeChatClient:
        init_kwargs: dict | None = None

        def __init__(self, **kwargs):
            FakeAgentScopeChatClient.init_kwargs = kwargs

        async def ainvoke(self, messages):
            assert messages[0].content == "请只回复 OK，用于模型连接测试。"
            return AIMessage(content="OK")

    monkeypatch.setattr(
        "app.api.agentscope_control_plane.AgentScopeChatClient",
        FakeAgentScopeChatClient,
    )

    response = client.post(
        "/api/agentscope-control/credentials/cred-1/test",
        json={"model": "gpt-4.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["detail"]["model"] == "gpt-4.1"
    assert payload["detail"]["sample"] == "OK"
    assert FakeAgentScopeChatClient.init_kwargs["api_key"] == "sk-local-test"
    assert FakeAgentScopeChatClient.init_kwargs["model"] == "gpt-4.1"
    db_session.refresh(config)
    assert config.last_test_result["ok"] is True
    assert config.last_test_result["model"] == "gpt-4.1"
    assert config.last_error_message is None


def test_agentscope_control_plane_credentials_include_last_model_test(client, db_session):
    """凭证列表需要回显最近测试摘要，供设置页卡片展示。"""

    config = LLMModelConfig(
        credential_id="cred-1",
        credential_type="openai_credential",
        name="默认凭证",
        provider="openai-compatible",
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key_enc=encrypt_password("sk-local-test"),
        last_test_result={
            "ok": True,
            "model": "gpt-test",
            "latency_ms": 123,
            "sample": "OK",
        },
    )
    db_session.add(config)
    db_session.commit()

    response = client.get("/api/agentscope-control/credentials")

    assert response.status_code == 200
    data = response.json()[0]["data"]
    assert data["config_id"] == config.id
    assert data["last_test_result"]["latency_ms"] == 123
    assert data["last_error_message"] is None
