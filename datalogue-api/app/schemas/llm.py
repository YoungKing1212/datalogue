# ============================================================
# File Name   : llm.py
# Description:
#   LLM 配置管理 API 的 Pydantic Schema。
#
# Responsibilities:
#   - 校验模型连接配置请求。
#   - 序列化前端设置页需要的模型配置响应。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMModelConfigCreate(BaseModel):
    name: str
    provider: str = "openai-compatible"
    base_url: str
    model: str
    api_key: Optional[str] = None
    status: str = "active"
    description: Optional[str] = None
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    thinking_enabled: bool = False


class LLMModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    request_timeout_seconds: Optional[float] = Field(default=None, gt=0)
    thinking_enabled: Optional[bool] = None


class LLMModelConfigOut(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str
    model: str
    status: str
    description: Optional[str] = None
    request_timeout_seconds: float
    thinking_enabled: bool = False
    api_key_set: bool = False
    last_test_result: Optional[dict[str, Any]] = None
    last_error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LLMTestResultOut(BaseModel):
    ok: bool
    message: str
    detail: Optional[dict[str, Any]] = None
