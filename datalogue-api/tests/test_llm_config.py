# ============================================================
# File Name   : test_llm_config.py
# Description:
#   LLM 模型配置管理和角色解析测试。
#
# Responsibilities:
#   - 验证模型配置 API 不泄露密钥且能保存角色绑定。
#   - 验证 get_llm 按数据库配置优先、环境变量兜底创建客户端。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.core.security import decrypt_password
from app.models import LLMModelConfig, LLMRoleBinding
from app.services.llm_config import resolve_llm_config


def test_llm_model_crud_masks_api_key(client, db_session):
    """模型配置 API 不应返回明文 API Key，空 Key 更新不覆盖旧密钥。"""
    payload = {
        "name": "LiteLLM SQL",
        "provider": "litellm",
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

    config = db_session.get(LLMModelConfig, data["id"])
    assert config is not None
    assert config.api_key_enc != "sk-secret"
    assert decrypt_password(config.api_key_enc) == "sk-secret"
    assert config.thinking_enabled is True

    resp = client.put(
        f"/api/llm/models/{data['id']}",
        json={"name": "LiteLLM SQL v2", "api_key": "", "thinking_enabled": False},
    )
    assert resp.status_code == 200
    db_session.refresh(config)
    assert config.name == "LiteLLM SQL v2"
    assert decrypt_password(config.api_key_enc) == "sk-secret"
    assert config.thinking_enabled is False


def test_role_bindings_round_trip(client):
    """角色绑定保存后可按固定角色集合读回。"""
    model_resp = client.post(
        "/api/llm/models",
        json={
            "name": "Report Model",
            "provider": "litellm",
            "base_url": "http://localhost:4000/v1",
            "model": "report-model",
            "api_key": "sk-report",
        },
    )
    model_id = model_resp.json()["id"]

    resp = client.put("/api/llm/role-bindings", json={"bindings": {"report": model_id}})
    assert resp.status_code == 200
    rows = {item["role"]: item["model_config_id"] for item in resp.json()}
    assert rows["report"] == model_id
    assert "default" in rows
    assert "lead_agent" in rows


def test_resolve_llm_config_role_and_default_fallback(db_session):
    """角色未绑定时先回退 default，再回退环境变量。"""
    settings = Settings(
        OPENAI_API_KEY="env-key",
        OPENAI_BASE_URL="https://env.example/v1",
        LLM_MODEL="env-model",
    )
    report_config = resolve_llm_config(settings, role="report", db=db_session)
    assert report_config.source == "env"
    assert report_config.model == "env-model"
    assert report_config.thinking_enabled is False

    default_model = LLMModelConfig(
        name="Default DB",
        provider="litellm",
        base_url="http://localhost:4000/v1",
        model="default-model",
        api_key_enc=None,
        status="active",
        thinking_enabled=False,
    )
    dsl_model = LLMModelConfig(
        name="DSL DB",
        provider="litellm",
        base_url="http://localhost:4000/v1",
        model="dsl-model",
        api_key_enc=None,
        status="active",
        thinking_enabled=True,
    )
    db_session.add_all([default_model, dsl_model])
    db_session.flush()
    db_session.add_all(
        [
            LLMRoleBinding(role="default", model_config_id=default_model.id),
            LLMRoleBinding(role="dsl", model_config_id=dsl_model.id),
        ]
    )
    db_session.commit()

    dsl_config = resolve_llm_config(settings, role="dsl", db=db_session)
    report_config = resolve_llm_config(settings, role="report", db=db_session)
    assert dsl_config.model == "dsl-model"
    assert dsl_config.thinking_enabled is True
    assert report_config.model == "default-model"
    assert report_config.thinking_enabled is False


def test_get_llm_uses_database_role_config(db_session):
    """get_llm 应使用角色绑定的数据库配置创建 LiteLLM SDK 客户端。"""
    from app.core.security import encrypt_password
    from app.graph.llm import LiteLLMChatClient, get_llm

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
    db_session.flush()
    db_session.add(LLMRoleBinding(role="intent", model_config_id=model.id))
    db_session.commit()

    llm = get_llm(temperature=0.2, role="intent", db=db_session)

    assert isinstance(llm, LiteLLMChatClient)
    assert llm.model == "qwen/qwen-plus"
    assert llm.api_key == "sk-intent"
    assert llm.api_base == "http://localhost:4000/v1"
    assert llm.temperature == 0.2
    assert llm.timeout == 12
    assert llm.model_kwargs == {"extra_body": {"enable_thinking": False}}
    assert llm.max_tokens == 256
    assert llm.response_format == {"type": "json_object"}
    assert llm.datalogue_call_policy["structured_output"] is True
    assert llm.datalogue_thinking_enabled is False


def test_get_llm_keeps_thinking_when_enabled(db_session):
    """模型配置开启 Think 后，不应再下发禁用思考参数。"""
    from app.core.security import encrypt_password
    from app.graph.llm import LiteLLMChatClient, get_llm

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
    db_session.flush()
    db_session.add(LLMRoleBinding(role="report", model_config_id=model.id))
    db_session.commit()

    llm = get_llm(role="report", db=db_session)

    assert isinstance(llm, LiteLLMChatClient)
    assert llm.model == "qwen/qwen-plus"
    assert llm.model_kwargs == {}
    assert llm.response_format is None
    assert llm.datalogue_thinking_enabled is True


def test_get_llm_uses_litellm_sdk_adapter(db_session):
    """显式 LiteLLM 模型名前缀应原样透传给 SDK 适配器。"""
    from app.core.security import encrypt_password
    from app.graph.llm import LiteLLMChatClient, get_llm

    model = LLMModelConfig(
        name="LiteLLM SDK MiniMax",
        provider="litellm_sdk",
        base_url="https://api.minimaxi.com/v1",
        model="minimax/MiniMax-M3",
        api_key_enc=encrypt_password("sk-minimax"),
        status="active",
        request_timeout_seconds=30,
        thinking_enabled=False,
    )
    db_session.add(model)
    db_session.flush()
    db_session.add(LLMRoleBinding(role="lead_agent", model_config_id=model.id))
    db_session.commit()

    llm = get_llm(temperature=0.1, role="lead_agent", db=db_session)

    assert isinstance(llm, LiteLLMChatClient)
    assert llm.model == "minimax/MiniMax-M3"
    assert llm.api_base == "https://api.minimaxi.com/v1"
    assert llm.api_key == "sk-minimax"
    assert llm.temperature == 0.1
    assert llm.timeout == 30
    assert llm.datalogue_thinking_enabled is False


def test_llm_model_test_endpoint_persists_result(client, db_session):
    """测试连接接口应保存最近一次测试结果。"""
    model_resp = client.post(
        "/api/llm/models",
        json={
            "name": "Test Model",
            "provider": "litellm",
            "base_url": "http://localhost:4000/v1",
            "model": "test-model",
            "api_key": "sk-test",
            "thinking_enabled": False,
        },
    )
    model_id = model_resp.json()["id"]
    fake_response = MagicMock()
    fake_response.content = "OK"

    with patch("app.api.llm.LiteLLMChatClient") as litellm_client:
        litellm_client.return_value.invoke.return_value = fake_response
        resp = client.post(f"/api/llm/models/{model_id}/test", json={})

    kwargs = litellm_client.call_args.kwargs
    assert kwargs["model"] == "openai/test-model"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["api_base"] == "http://localhost:4000/v1"
    assert kwargs["model_kwargs"] == {}
    assert kwargs["max_tokens"] is None
    assert kwargs["response_format"] is None
    assert kwargs["thinking_enabled"] is False
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    config = db_session.get(LLMModelConfig, model_id)
    assert config.last_test_result["ok"] is True
    assert config.last_error_message is None
