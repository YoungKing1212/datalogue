# ============================================================
# File Name   : auth.py
# Description:
#   登录认证 API。
#
# Responsibilities:
#   - 提供注册、登录、续期、登出与当前用户信息接口。
#   - 通过 HttpOnly Cookie 管理 refresh token。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_superuser, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core import models, schemas
from app.core.security import (
    create_token,
    decode_token,
    decrypt_auth_password,
    hash_password,
    is_token_invalid_error,
    verify_password,
)

router = APIRouter()
settings = get_settings()


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=settings.AUTH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        secure=settings.AUTH_COOKIE_SECURE,
    )


def _build_access_token(user: models.User) -> str:
    return create_token(
        sub=str(user.id),
        expires=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def _build_refresh_token(user: models.User) -> str:
    return create_token(
        sub=str(user.id),
        expires=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: schemas.RegisterIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_superuser),
) -> schemas.UserOut:
    existing_query = db.query(models.User).filter(models.User.username == payload.username)
    if payload.email:
        existing_query = db.query(models.User).filter(
            or_(models.User.username == payload.username, models.User.email == payload.email)
        )
    existing_user = existing_query.first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名或邮箱已存在")

    user = models.User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        role="user",
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, response: Response, db: Session = Depends(get_db)) -> schemas.TokenOut:
    try:
        plain_password = decrypt_auth_password(payload.password_enc)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码密文无效") from exc

    user = (
        db.query(models.User)
        .filter(or_(models.User.username == payload.username, models.User.email == payload.username))
        .first()
    )
    if user is None or not verify_password(plain_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    access_token = _build_access_token(user)
    refresh_token = _build_refresh_token(user)
    _set_refresh_cookie(response, refresh_token)
    return schemas.TokenOut(access_token=access_token)


@router.post("/refresh", response_model=schemas.TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> schemas.TokenOut:
    refresh_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少刷新令牌")

    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效")
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效")
    except Exception as exc:
        if is_token_invalid_error(exc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效") from exc
        raise

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    # 续期时轮转 refresh token，降低长期凭证泄露后的风险窗口。
    new_refresh_token = _build_refresh_token(user)
    _set_refresh_cookie(response, new_refresh_token)
    return schemas.TokenOut(access_token=_build_access_token(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    # 退出只需要清理 refresh cookie；即使 access token 已过期，也必须允许用户彻底退出本机登录态。
    _clear_refresh_cookie(response)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)) -> schemas.UserOut:
    return current_user


@router.get("/users", response_model=list[schemas.UserManageItemOut])
def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_superuser),
) -> list[schemas.UserManageItemOut]:
    users = (
        db.query(models.User)
        .order_by(models.User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return users


@router.patch("/users/{user_id}", response_model=schemas.UserManageItemOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdateIn,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_superuser),
) -> schemas.UserManageItemOut:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if payload.email is not None and payload.email != user.email:
        duplicated_email = (
            db.query(models.User)
            .filter(models.User.email == payload.email, models.User.id != user_id)
            .first()
        )
        if duplicated_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被占用")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
        # 当角色降为普通用户时同步移除 superuser 标记，避免权限语义不一致。
        user.is_superuser = payload.role == "admin" and user.is_superuser

    if payload.is_active is not None:
        if current_admin.id == user.id and not payload.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录账号")
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_superuser),
) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    reset_password = f"{user.username}@123456"
    user.hashed_password = hash_password(reset_password)
    db.commit()


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_superuser),
) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if user.is_superuser:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="超级管理员账号不允许删除")
    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")

    db.delete(user)
    db.commit()
