# ============================================================
# File Name   : deps.py
# Description:
#   API 鉴权依赖定义。
#
# Responsibilities:
#   - 解析 Bearer Token 并注入当前登录用户。
#   - 为管理员接口提供统一权限校验依赖。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import models
from app.core.database import get_db
from app.core.security import decode_token, is_token_invalid_error


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise cred_exc
        raw_user_id = payload.get("sub")
        if raw_user_id is None:
            raise cred_exc
        user_id = int(raw_user_id)
    except ValueError as exc:
        raise cred_exc from exc
    except Exception as exc:
        if is_token_invalid_error(exc):
            raise cred_exc from exc
        raise

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise cred_exc
    return user


def get_current_superuser(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_superuser and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


def require_api_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """统一业务 API 登录拦截依赖，便于路由聚合层集中保护所有接口。"""

    return current_user


def require_api_admin(current_user: models.User = Depends(get_current_superuser)) -> models.User:
    """统一系统配置 API 管理员拦截依赖。"""

    return current_user
