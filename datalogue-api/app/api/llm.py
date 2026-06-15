# ============================================================
# File Name   : llm.py
# Description:
#   LLM 模型配置管理 API 端点。
#
# Responsibilities:
#   - 提供前端维护模型配置和任务角色绑定的接口。
#   - 测试 OpenAI-compatible 模型连接并记录诊断结果。
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

from app import models, schemas
from app.core.database import get_db
from app.core.security import decrypt_password, encrypt_password
from app.graph.llm import LiteLLMChatClient, _litellm_model_name, _llm_call_policy, build_llm_model_kwargs
from app.services.llm_config import LLM_ROLES, ResolvedLLMConfig, ensure_llm_role, model_config_to_dict

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


@router.get("/roles")
def list_llm_roles():
    """返回系统支持的 LLM 任务角色。"""
    return {"roles": list(LLM_ROLES)}


@router.get("/models", response_model=List[schemas.LLMModelConfigOut])
def list_llm_models(db: Session = Depends(get_db)):
    """获取所有 LLM 模型配置，响应不包含明文 API Key。"""
    configs = db.query(models.LLMModelConfig).order_by(models.LLMModelConfig.id.desc()).all()
    return [model_config_to_dict(config) for config in configs]


@router.post("/models", response_model=schemas.LLMModelConfigOut)
def create_llm_model(payload: schemas.LLMModelConfigCreate, db: Session = Depends(get_db)):
    """创建 LLM 模型配置，API Key 加密存储。"""
    _validate_status(payload.status)
    config = models.LLMModelConfig(
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        api_key_enc=encrypt_password(payload.api_key) if payload.api_key else None,
        status=payload.status,
        description=payload.description,
        request_timeout_seconds=payload.request_timeout_seconds,
        thinking_enabled=payload.thinking_enabled,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    logger.info("LLM 模型配置创建成功: id=%s, provider=%s, model=%s", config.id, config.provider, config.model)
    return model_config_to_dict(config)


@router.get("/models/{config_id}", response_model=schemas.LLMModelConfigOut)
def get_llm_model(config_id: int, db: Session = Depends(get_db)):
    """获取单个 LLM 模型配置。"""
    return model_config_to_dict(_get_model_config(db, config_id))


@router.put("/models/{config_id}", response_model=schemas.LLMModelConfigOut)
def update_llm_model(
    config_id: int,
    payload: schemas.LLMModelConfigUpdate,
    db: Session = Depends(get_db),
):
    """更新 LLM 模型配置，api_key 为空时不覆盖旧密钥。"""
    config = _get_model_config(db, config_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_status(data.get("status"))
    api_key = data.pop("api_key", None)
    if api_key:
        data["api_key_enc"] = encrypt_password(api_key)
    for key, value in data.items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    logger.info("LLM 模型配置更新成功: id=%s", config.id)
    return model_config_to_dict(config)


@router.delete("/models/{config_id}")
def delete_llm_model(config_id: int, db: Session = Depends(get_db)):
    """删除 LLM 模型配置，并清空关联角色绑定。"""
    config = _get_model_config(db, config_id)
    for binding in db.query(models.LLMRoleBinding).filter_by(model_config_id=config_id).all():
        binding.model_config_id = None
    db.delete(config)
    db.commit()
    logger.info("LLM 模型配置删除成功: id=%s", config_id)
    return {"ok": True}


@router.post("/models/{config_id}/test", response_model=schemas.LLMTestResultOut)
def test_llm_model(config_id: int, db: Session = Depends(get_db)):
    """测试模型配置是否可用，并保存最近一次测试结果。"""
    config = _get_model_config(db, config_id)
    started_at = time.perf_counter()
    try:
        api_key = decrypt_password(config.api_key_enc) if config.api_key_enc else ""
        resolved = ResolvedLLMConfig(
            role="default",
            source="database",
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key=api_key,
            request_timeout_seconds=float(config.request_timeout_seconds),
            thinking_enabled=bool(config.thinking_enabled),
        )
        call_policy = _llm_call_policy(resolved.role)
        llm = LiteLLMChatClient(
            model=_litellm_model_name(resolved),
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
        response = llm.invoke([HumanMessage(content="请回复 OK，用于连接测试。")])
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


@router.get("/role-bindings", response_model=List[schemas.LLMRoleBindingOut])
def list_role_bindings(db: Session = Depends(get_db)):
    """读取所有 LLM 角色绑定，未配置的角色返回空绑定。"""
    bindings = {
        item.role: item.model_config_id
        for item in db.query(models.LLMRoleBinding).all()
        if item.role in LLM_ROLES
    }
    return [{"role": role, "model_config_id": bindings.get(role)} for role in LLM_ROLES]


@router.put("/role-bindings", response_model=List[schemas.LLMRoleBindingOut])
def update_role_bindings(
    payload: schemas.LLMRoleBindingsUpdate,
    db: Session = Depends(get_db),
):
    """保存 LLM 任务角色绑定。"""
    for role, config_id in payload.bindings.items():
        normalized_role = ensure_llm_role(role)
        if config_id is not None:
            config = _get_model_config(db, config_id)
            if config.status != "active":
                raise HTTPException(status_code=400, detail=f"角色 {normalized_role} 不能绑定停用模型")
        binding = db.query(models.LLMRoleBinding).filter_by(role=normalized_role).first()
        if not binding:
            binding = models.LLMRoleBinding(role=normalized_role)
            db.add(binding)
        binding.model_config_id = config_id
    db.commit()
    return list_role_bindings(db)
