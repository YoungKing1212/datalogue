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

from fastapi import Depends, HTTPException, Request, status
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
    return _resolve_current_user(token=token, db=db)


def _resolve_current_user(*, token: str, db: Session) -> models.User:
    """解析并校验访问令牌；供普通请求与长连接复用相同安全语义。"""

    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access" or payload.get("sub") is None:
            raise cred_exc
        user_id = int(payload["sub"])
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


def require_api_user(
    request: Request,
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """统一业务 API 登录拦截依赖，便于路由聚合层集中保护所有接口。"""

    password_change_allowed_paths = {"/api/auth/me", "/api/auth/change-password"}
    if current_user.must_change_password and request.url.path not in password_change_allowed_paths:
        # 管理员重置后的临时密码只能用于进入改密流程，不能访问任何业务数据。
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": "请先修改临时密码",
            },
        )
    return current_user


def require_api_admin(current_user: models.User = Depends(get_current_superuser)) -> models.User:
    """统一系统配置 API 管理员拦截依赖。"""

    return current_user
