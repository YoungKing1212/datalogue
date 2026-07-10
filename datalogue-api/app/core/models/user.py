# ============================================================
# File Name   : user.py
# Description:
#   平台用户认证模型定义。
#
# Responsibilities:
#   - 存储登录账号、密码哈希和用户状态。
#   - 为会话与权限控制提供用户主键锚点。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from sqlalchemy import Boolean, Column, Integer, String

from app.core.database import Base
from app.core.models.base import TimestampMixin


class User(Base, TimestampMixin):
    """平台用户表，避免与数据库关键字 user 冲突，使用 app_user。"""

    __tablename__ = "app_user"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=True, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(16), nullable=False, default="user", server_default="user")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_superuser = Column(Boolean, nullable=False, default=False, server_default="false")
