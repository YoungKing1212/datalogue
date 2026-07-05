# ============================================================
# File Name   : test_agentscope_control_plane_api.py
# Description:
#   AgentScope credential/model 控制面代理 API 测试。
#
# Responsibilities:
#   - 确认 Datalogue 只代理 AgentScope Service 的 credential/model 资源。
#   - 防止新模型控制面回写旧 llm_model_config 或 role binding。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

import pytest


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
        return {"openai_credential": {"title": "OpenAI API", "properties": {"api_key": {"type": "string"}}}}

    async def list_credentials(self):
        self.calls.append(("list_credentials", None))
        return [{"id": "cred-1", "data": {"name": "默认凭证"}}]

    async def create_credential(self, payload):
        self.calls.append(("create_credential", payload))
        return {"credential_id": "cred-1"}

    async def update_credential(self, credential_id, payload):
        self.calls.append(("update_credential", (credential_id, payload)))
        return {"credential_id": credential_id, "updated": True}

    async def delete_credential(self, credential_id):
        self.calls.append(("delete_credential", credential_id))
        return {"deleted": True}

    async def list_models(self, *, provider: str):
        self.calls.append(("list_models", provider))
        return [{"name": "gpt-4.1", "model_type": "chat"}]


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
    list_response = client.get("/api/agentscope-control/credentials")
    create_response = client.post(
        "/api/agentscope-control/credentials",
        json={"data": {"type": "openai_credential", "api_key": "sk-test"}},
    )
    update_response = client.patch(
        "/api/agentscope-control/credentials/cred-1",
        json={"data": {"name": "更新后的凭证"}},
    )
    delete_response = client.delete("/api/agentscope-control/credentials/cred-1")

    assert list_response.json() == [{"id": "cred-1", "data": {"name": "默认凭证"}}]
    assert create_response.json() == {"credential_id": "cred-1"}
    assert update_response.json() == {"credential_id": "cred-1", "updated": True}
    assert delete_response.json() == {"deleted": True}
    assert ("create_credential", {"data": {"type": "openai_credential", "api_key": "sk-test"}}) in (
        FakeAgentScopeControlPlaneClient.calls
    )
    assert ("update_credential", ("cred-1", {"data": {"name": "更新后的凭证"}})) in (
        FakeAgentScopeControlPlaneClient.calls
    )
    assert ("delete_credential", "cred-1") in FakeAgentScopeControlPlaneClient.calls


def test_agentscope_control_plane_proxies_models(client):
    response = client.get("/api/agentscope-control/model?provider=openai_credential")

    assert response.status_code == 200
    assert response.json() == [{"name": "gpt-4.1", "model_type": "chat"}]
    assert ("list_models", "openai_credential") in FakeAgentScopeControlPlaneClient.calls
