# ============================================================
# File Name   : llm.py
# Description:
#   LLM 模型配置管理 API 端点。
#
# Responsibilities:
#   - 提供前端维护模型配置的接口。
#   - 通过 AgentScope credential 保存密钥并测试模型连接。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.core import models, schemas
from app.agentscope_runtime.client import AgentScopeServiceClient
from app.core.config import get_settings
from app.core.database import get_db
from app.core.llm import AgentScopeChatClient, _llm_call_policy, build_llm_model_kwargs
from app.core.llm_config import (
    DEFAULT_LLM_ROLE,
    ResolvedLLMConfig,
    credential_api_key_from_items,
    credential_id_for_model_config,
    model_config_to_dict,
)
from app.core.security import encrypt_password

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_model_config(db: Session, config_id: int) -> models.LLMModelConfig:
    config = db.get(models.LLMModelConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="LLM 模型配置不存在")
    return config


def _validate_status(status: str | None) -> str | None:
    if status is None:
        return None
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="status 仅支持 active / disabled")
    return status


def _agentscope_base_url() -> str:
    settings = get_settings()
    return (settings.AGENTSCOPE_SERVICE_BASE_URL or "http://127.0.0.1:8000/agentscope").rstrip("/")


async def _list_agentscope_credentials() -> list[dict]:
    async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
        return await client.list_credentials()


async def _upsert_agentscope_model_credential(
    *,
    config: models.LLMModelConfig,
    api_key: str | None,
) -> str | None:
    """把模型配置密钥写入 AgentScope credential；Datalogue DB 不保存明文密钥。"""

    credential_id = credential_id_for_model_config(config.id)
    async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
        if api_key:
            return await client.upsert_openai_credential(
                credential_id=credential_id,
                name=f"Datalogue {config.name}",
                api_key=api_key,
                base_url=config.base_url,
            )
        await client.update_credential(
            credential_id,
            {
                "data": {
                    "name": f"Datalogue {config.name}",
                    "base_url": config.base_url,
                },
            },
        )
        return credential_id


def _credential_ids(credentials: list[dict]) -> set[str]:
    result: set[str] = set()
    for item in credentials:
        data = item.get("data") if isinstance(item.get("data"), dict) else item
        item_id = item.get("id") or item.get("credential_id") or data.get("id")
        if isinstance(item_id, str) and item_id:
            result.add(item_id)
    return result


async def _api_key_for_config(config: models.LLMModelConfig) -> str:
    """从 AgentScope credential 读取模型密钥；Datalogue DB 不保存密钥。"""

    credentials = await _list_agentscope_credentials()
    return credential_api_key_from_items(credentials, config.credential_id)


@router.get("/models", response_model=List[schemas.LLMModelConfigOut])
async def list_llm_models(db: Session = Depends(get_db)):
    """获取所有 LLM 模型配置，响应不包含明文 API Key。"""

    configs = db.query(models.LLMModelConfig).order_by(models.LLMModelConfig.id.desc()).all()
    credential_ids = _credential_ids(await _list_agentscope_credentials())
    return [model_config_to_dict(config, credential_ids) for config in configs]


@router.post("/models", response_model=schemas.LLMModelConfigOut)
async def create_llm_model(payload: schemas.LLMModelConfigCreate, db: Session = Depends(get_db)):
    """创建 LLM 模型配置；密钥写入 AgentScope credential，DB 只保留模型配置投影。"""

    _validate_status(payload.status)
    api_key = payload.api_key.strip() if payload.api_key else None
    config = models.LLMModelConfig(
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        status=payload.status,
        description=payload.description,
        request_timeout_seconds=payload.request_timeout_seconds,
        thinking_enabled=payload.thinking_enabled,
        # 兼容旧接口：仍保存 AES-GCM 密文，供 AgentScope credential 丢失时自动恢复。
        api_key_enc=encrypt_password(api_key) if api_key else None,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    if api_key:
        try:
            config.credential_id = await _upsert_agentscope_model_credential(
                config=config, api_key=api_key
            )
            config.credential_type = "openai_credential"
            db.commit()
            db.refresh(config)
        except Exception as exc:
            # credential 写入失败时回滚本地投影，避免页面出现不可用的“半条配置”。
            db.delete(config)
            db.commit()
            raise HTTPException(
                status_code=502, detail=f"AgentScope credential 写入失败: {exc}"
            ) from exc
    logger.info(
        "LLM 模型配置创建成功: id=%s, provider=%s, model=%s",
        config.id,
        config.provider,
        config.model,
    )
    credential_ids = {config.credential_id} if config.credential_id else set()
    return model_config_to_dict(config, credential_ids)


@router.get("/models/{config_id}", response_model=schemas.LLMModelConfigOut)
async def get_llm_model(config_id: int, db: Session = Depends(get_db)):
    """获取单个 LLM 模型配置。"""

    config = _get_model_config(db, config_id)
    credential_ids = _credential_ids(await _list_agentscope_credentials())
    return model_config_to_dict(config, credential_ids)


@router.put("/models/{config_id}", response_model=schemas.LLMModelConfigOut)
async def update_llm_model(
    config_id: int,
    payload: schemas.LLMModelConfigUpdate,
    db: Session = Depends(get_db),
):
    """更新 LLM 模型配置；api_key 为空时不覆盖已保存密钥。"""

    config = _get_model_config(db, config_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_status(data.get("status"))
    raw_api_key = data.pop("api_key", None)
    api_key = raw_api_key.strip() if isinstance(raw_api_key, str) else None
    previous_api_key_enc = config.api_key_enc
    previous_values = {key: getattr(config, key) for key in data}
    for key, value in data.items():
        setattr(config, key, value)
    if api_key:
        config.api_key_enc = encrypt_password(api_key)
    db.commit()
    db.refresh(config)
    try:
        if api_key:
            config.credential_id = await _upsert_agentscope_model_credential(
                config=config, api_key=api_key
            )
            config.credential_type = "openai_credential"
            db.commit()
            db.refresh(config)
        elif config.credential_id in _credential_ids(await _list_agentscope_credentials()):
            # 已有 credential 时同步名称/Base URL，避免页面配置与运行凭据漂移。
            await _upsert_agentscope_model_credential(config=config, api_key=None)
    except Exception as exc:
        # 外部 credential 同步失败时恢复本地改动，避免密钥或运行参数出现半成功状态。
        for key, value in previous_values.items():
            setattr(config, key, value)
        config.api_key_enc = previous_api_key_enc
        db.commit()
        raise HTTPException(
            status_code=502, detail=f"AgentScope credential 更新失败: {exc}"
        ) from exc
    logger.info("LLM 模型配置更新成功: id=%s", config.id)
    credential_ids = _credential_ids(await _list_agentscope_credentials())
    return model_config_to_dict(config, credential_ids)


@router.delete("/models/{config_id}")
async def delete_llm_model(config_id: int, db: Session = Depends(get_db)):
    """删除 LLM 模型配置，同时尽量清理对应 AgentScope credential。"""

    config = _get_model_config(db, config_id)
    credential_id = config.credential_id
    try:
        if credential_id:
            async with AgentScopeServiceClient(base_url=_agentscope_base_url()) as client:
                await client.delete_credential(credential_id)
    except Exception:
        logger.warning(
            "AgentScope credential 删除失败，继续删除本地配置: credential_id=%s",
            credential_id,
            exc_info=True,
        )
    db.delete(config)
    db.commit()
    logger.info("LLM 模型配置删除成功: id=%s", config_id)
    return {"ok": True}


@router.post("/models/{config_id}/test", response_model=schemas.LLMTestResultOut)
async def test_llm_model(config_id: int, db: Session = Depends(get_db)):
    """测试模型配置是否可用，并保存最近一次测试结果。"""

    config = _get_model_config(db, config_id)
    started_at = time.perf_counter()
    try:
        api_key = await _api_key_for_config(config)
        resolved = ResolvedLLMConfig(
            role=DEFAULT_LLM_ROLE,
            source="agentscope_credential",
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key=api_key,
            request_timeout_seconds=float(config.request_timeout_seconds),
            thinking_enabled=bool(config.thinking_enabled),
            credential_id=config.credential_id,
            credential_type=config.credential_type,
        )
        call_policy = _llm_call_policy(resolved.role)
        llm = AgentScopeChatClient(
            provider=resolved.provider,
            model=resolved.model,
            api_key=api_key,
            api_base=config.base_url,
            temperature=0,
            timeout=config.request_timeout_seconds,
            model_kwargs=build_llm_model_kwargs(config),
            thinking_enabled=bool(config.thinking_enabled),
            max_tokens=call_policy.get("max_tokens"),
            response_format=call_policy.get("response_format"),
            call_policy=call_policy,
        )
        response = await llm.ainvoke([HumanMessage(content="请回复 OK，用于连接测试。")])
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        content = str(response.content or "")[:200]
        result = {"ok": True, "latency_ms": elapsed_ms, "sample": content}
        config.last_test_result = result
        config.last_error_message = None
        db.commit()
        return {"ok": True, "message": "模型连接测试成功", "detail": result}
    except Exception as exc:  # pragma: no cover - 具体异常由模型服务决定
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        err = str(exc)[:500]
        result = {"ok": False, "latency_ms": elapsed_ms, "error": err}
        config.last_test_result = result
        config.last_error_message = err
        db.commit()
        logger.warning("LLM 模型连接测试失败: id=%s, error=%s", config_id, err)
        return {"ok": False, "message": "模型连接测试失败", "detail": result}
