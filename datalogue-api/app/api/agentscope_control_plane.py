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

from app.runtime.engine.client import AgentScopeServiceClient
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
    """更新 AgentScope credential；不维护 Datalogue 旧模型角色映射。"""

    try:
        async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
            return _sanitize_credential_payload(await client.update_credential(credential_id, payload))
    except httpx.HTTPStatusError as exc:
        _raise_proxy_error(exc)


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
