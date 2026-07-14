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
from fastapi import APIRouter, Body, HTTPException, Query

from app.agentscope_runtime.client import AgentScopeServiceClient
from app.core.config import get_settings

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


@router.get("/credential/schemas")
async def list_credential_schemas():
    """读取 AgentScope 官方 credential schemas，供前端动态渲染凭证表单。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return await client.list_credential_schemas()
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


@router.get("/credentials")
async def list_credentials():
    """读取 AgentScope credential 列表；Datalogue 不转换成旧模型配置 DTO。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return _sanitize_credential_payload(await client.list_credentials())
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


@router.post("/credentials")
async def create_credential(payload: dict[str, Any] = Body(...)):
    """创建 AgentScope credential；API key 只进入 AgentScope Service。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return _sanitize_credential_payload(await client.create_credential(payload))
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


@router.patch("/credentials/{credential_id}")
async def update_credential(credential_id: str, payload: dict[str, Any] = Body(...)):
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
            return _sanitize_credential_payload(
                await client.update_credential(credential_id, merged_payload)
            )
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


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
async def delete_credential(credential_id: str):
    """删除 AgentScope credential；调用方负责处理仍引用该凭证的 session。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return await client.delete_credential(credential_id)
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
