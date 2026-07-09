# ============================================================
# File Name   : auth.py
# Description:
#   认证相关请求与响应 Schema。
#
# Responsibilities:
#   - 校验登录、注册输入。
#   - 统一 Token 与用户信息输出结构。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password_enc: str = Field(..., min_length=1, max_length=2048)


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=100)


class UserUpdateIn(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=100)
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    role: Literal["admin", "user"]
    is_superuser: bool

    model_config = ConfigDict(from_attributes=True)


class UserManageItemOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    role: Literal["admin", "user"]
    is_active: bool
    is_superuser: bool

    model_config = ConfigDict(from_attributes=True)
