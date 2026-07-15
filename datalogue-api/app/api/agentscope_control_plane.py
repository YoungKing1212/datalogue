# ============================================================
# File Name   : agentscope_control_plane.py
# Description:
#   AgentScope Service credential/model 控制面代理 API。
#
# Responsibilities:
#   - 代理 AgentScope credential schema、credential CRUD 与 ModelCard 查询。
#   - 统一注入 Datalogue 内部 AgentScope Service base URL 和用户边界。
#   - 避免前端继续依赖 Datalogue 自建 LLM 配置表。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agentscope_runtime.client import AgentScopeServiceClient
from app.core.config import get_settings
from app.core.database import get_db
from app.core.models.llm import LLMModelConfig

router = APIRouter()


def _agentscope_base_url() -> str:
    """读取 AgentScope Service base URL；缺失时 fail-closed，避免把 credential 写入旧表。"""

    base_url = get_settings().AGENTSCOPE_SERVICE_BASE_URL
    if not base_url:
        raise HTTPException(status_code=503, detail="AgentScope Service base URL not configured")
    return base_url


def _raise_proxy_error(exc: httpx.HTTPStatusError) -> None:
    """把 AgentScope Service HTTP 错误转成 Datalogue API 错误，同时保留状态码。"""

    try:
        detail: Any = exc.response.json()
    except ValueError:
        detail = exc.response.text or exc.response.reason_phrase
    raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc


def _sanitize_credential_payload(payload: Any) -> Any:
    """脱敏 AgentScope credential 响应；API Key 只允许写入，不允许经控制面回传。"""

    if isinstance(payload, list):
        return [_sanitize_credential_payload(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "api_key":
            sanitized["api_key_set"] = bool(value)
            continue
        sanitized[key] = _sanitize_credential_payload(value)
    return sanitized


def _credential_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    return dict(data) if isinstance(data, dict) else {}


def _credential_id(item: dict[str, Any]) -> str | None:
    data = _credential_data(item)
    value = item.get("id") or item.get("credential_id") or data.get("id")
    return str(value) if isinstance(value, str) and value else None


def _provider_from_credential_type(credential_type: str) -> str:
    """将 AgentScope credential 类型投影为 Datalogue 模型供应商，供旧连接测试接口兼容读取。"""

    if credential_type == "openai_credential":
        return "openai-compatible"
    return credential_type.removesuffix("_credential") or credential_type


def _apply_credential_projection(
    config: LLMModelConfig,
    *,
    credential_id: str,
    data: dict[str, Any],
) -> None:
    """把设置页提交的非敏感字段写入数据库；api_key 始终不进入 Datalogue DB。"""

    credential_type = str(data.get("type") or config.credential_type or "").strip()
    if not credential_type:
        raise ValueError("AgentScope credential 缺少 type")
    config.credential_id = credential_id
    config.credential_type = credential_type
    config.name = str(data.get("name") or config.name or credential_id).strip()
    config.provider = _provider_from_credential_type(credential_type)
    config.base_url = str(data.get("base_url") or config.base_url or "").strip()
    config.model = str(data.get("model") or data.get("model_name") or config.model or "").strip()
    config.status = str(data.get("status") or config.status or "active").strip()
    config.description = data.get("description") if data.get("description") is not None else config.description
    if data.get("request_timeout_seconds") is not None:
        config.request_timeout_seconds = float(data["request_timeout_seconds"])
    if data.get("thinking_enabled") is not None:
        config.thinking_enabled = bool(data["thinking_enabled"])
    if not config.base_url or not config.model:
        raise ValueError("LLM 配置必须包含 base_url 和 model")


def _upsert_llm_config_projection(
    db: Session,
    *,
    credential_id: str,
    data: dict[str, Any],
) -> LLMModelConfig:
    """以 credential ID 为唯一关联创建或更新数据库模型配置，避免名称参与运行时关联。"""

    config = db.query(LLMModelConfig).filter(LLMModelConfig.credential_id == credential_id).one_or_none()
    if config is None:
        # 仅用于一次性接管旧表中尚未绑定 credential 的同名记录；运行时不会再使用名称猜测。
        name = str(data.get("name") or "").strip()
        legacy = (
            db.query(LLMModelConfig)
            .filter(LLMModelConfig.credential_id.is_(None), LLMModelConfig.name == name)
            .all()
        )
        config = legacy[0] if len(legacy) == 1 else LLMModelConfig(
            name=name or credential_id,
            provider="openai-compatible",
            base_url=str(data.get("base_url") or ""),
            model=str(data.get("model") or data.get("model_name") or ""),
        )
        if config.id is None:
            db.add(config)
    _apply_credential_projection(config, credential_id=credential_id, data=data)
    db.commit()
    db.refresh(config)
    return config


def _serialize_credential_with_projection(
    credential: dict[str, Any],
    config: LLMModelConfig | None,
) -> dict[str, Any]:
    """把数据库配置投影回设置页，保证模型名、状态等不依赖原生 credential 的未知字段持久化。"""

    credential_id = _credential_id(credential)
    data = _credential_data(credential)
    if config is not None:
        data.update(
            {
                "id": credential_id,
                "type": config.credential_type,
                "name": config.name,
                "base_url": config.base_url,
                "model": config.model,
                "status": config.status,
                "description": config.description,
                "request_timeout_seconds": config.request_timeout_seconds,
                "thinking_enabled": bool(config.thinking_enabled),
            }
        )
    return {"id": credential_id, "data": data}


def _backfill_legacy_llm_config_link(
    db: Session,
    *,
    credential_id: str,
    data: dict[str, Any],
) -> None:
    """只接管一条可唯一确认的旧配置；凭据列表读取绝不凭空创建数据库模型配置。"""

    if db.query(LLMModelConfig).filter(LLMModelConfig.credential_id == credential_id).first():
        return
    name = str(data.get("name") or "").strip()
    legacy = (
        db.query(LLMModelConfig)
        .filter(LLMModelConfig.credential_id.is_(None), LLMModelConfig.name == name)
        .all()
    )
    if len(legacy) != 1:
        return
    _apply_credential_projection(legacy[0], credential_id=credential_id, data=data)
    db.commit()


@router.get("/credential/schemas")
async def list_credential_schemas():
    """读取 AgentScope 官方 credential schemas，供前端动态渲染凭证表单。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return await client.list_credential_schemas()
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


@router.get("/credentials")
async def list_credentials(db: Session = Depends(get_db)):
    """读取 AgentScope credential，并以数据库模型配置补齐设置页需要的非敏感字段。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            credentials = await client.list_credentials()
        for credential in credentials:
            credential_id = _credential_id(credential)
            if credential_id:
                # 对升级前的唯一同名旧配置完成一次接管，之后只依赖 credential_id 关联。
                _backfill_legacy_llm_config_link(
                    db,
                    credential_id=credential_id,
                    data=_credential_data(credential),
                )
        configs = {
            config.credential_id: config
            for config in db.query(LLMModelConfig).filter(LLMModelConfig.credential_id.is_not(None)).all()
        }
        return _sanitize_credential_payload(
            [
                _serialize_credential_with_projection(credential, configs.get(_credential_id(credential)))
                for credential in credentials
            ]
        )
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


@router.post("/credentials")
async def create_credential(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """创建 AgentScope credential 后立即把其真实 ID/type 回写数据库配置。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            created = await client.create_credential(payload)
            credential_id = _credential_id(created)
            if not credential_id:
                raise ValueError("AgentScope 创建 credential 后未返回 id")
            try:
                _upsert_llm_config_projection(
                    db,
                    credential_id=credential_id,
                    data=_credential_data(payload),
                )
            except Exception:
                # 远端凭据若无本地配置关联，后续无法被默认运行时安全选择，因此尽力补偿删除。
                await client.delete_credential(credential_id)
                raise
            return _sanitize_credential_payload(created)
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/credentials/{credential_id}")
async def update_credential(
    credential_id: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """更新 AgentScope credential；不维护 Datalogue 旧模型角色映射。

    前端表单为了避免 API Key 泄露，只在用户显式重填 key 时才把 ``api_key`` 打进 payload；
    若直接透传给 AgentScope Service，其 credential 使用 tagged-union 反序列化必然报
    ``api_key`` 缺失。这里把 patch 语义收敛回"partial update"：读现存 credential 数据，
    用前端提交的字段覆盖，最后整体 push 回 AgentScope。
    切换 credential ``type`` 时（如 deepseek→openai）不复用旧 key，由前端负责让用户重填。
    """

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            merged_payload = await _merge_credential_patch(client, credential_id, payload)
            updated = await client.update_credential(credential_id, merged_payload)
        _upsert_llm_config_projection(
            db,
            credential_id=credential_id,
            data=_credential_data(merged_payload),
        )
        return _sanitize_credential_payload(updated)
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _merge_credential_patch(
    client: AgentScopeServiceClient,
    credential_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """把前端 PATCH 语义解读为 partial update：现存字段兜底，patch 覆盖。

    - 只有当 patch 中 ``api_key`` 缺失或空串时，才从 AgentScope 现存 credential 中取回。
    - 一旦 ``type`` 变了（切 provider），认为旧 credential 已经作废，不复用其 api_key，
      让 AgentScope 侧的 pydantic 校验按原语义抛错，前端提示用户重填 key。
    - 404 由本函数就地抛出，避免把"找不到 credential"伪装成 500。
    """

    overlay_raw = payload.get("data")
    overlay: dict[str, Any] = dict(overlay_raw) if isinstance(overlay_raw, dict) else {}

    existing_list = await client.list_credentials()
    existing_item = next(
        (item for item in existing_list if item.get("id") == credential_id),
        None,
    )
    if existing_item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Credential '{credential_id}' not found.",
        )

    existing_data = existing_item.get("data")
    existing_data = dict(existing_data) if isinstance(existing_data, dict) else {}

    # partial-update：existing 打底，overlay 覆盖。
    merged: dict[str, Any] = {**existing_data, **overlay}

    # 切 provider（type 变了）时旧 api_key 一定要作废，强制前端重填；
    # 否则 overlay 缺 api_key 时用 existing 兜底，避免误清空。
    overlay_type = overlay.get("type")
    existing_type = existing_data.get("type")
    type_changed = bool(overlay_type) and bool(existing_type) and overlay_type != existing_type
    overlay_key = str(overlay.get("api_key") or "").strip()
    if type_changed:
        merged.pop("api_key", None)
    elif not overlay_key:
        existing_key = existing_data.get("api_key")
        if existing_key:
            merged["api_key"] = existing_key

    return {"data": merged}


@router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: str, db: Session = Depends(get_db)):
    """删除 AgentScope credential 及其数据库模型配置，避免产生孤儿默认配置。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            result = await client.delete_credential(credential_id)
        db.query(LLMModelConfig).filter(LLMModelConfig.credential_id == credential_id).delete()
        db.commit()
        return result
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


@router.get("/model")
async def list_models(provider: str = Query(..., min_length=1)):
    """按 provider 读取 AgentScope ModelCard 列表。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return await client.list_models(provider=provider)
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)
