# ============================================================
# File Name   : security.py
# Description:
#   SQL 和请求处理安全辅助函数。
#
# Responsibilities:
#   - 在执行前校验 SQL 安全性。
#   - 集中维护轻量级安全检查逻辑。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

import base64
import binascii
import hashlib
import os
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_settings = get_settings()
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
PASSWORD_STORAGE_PREFIX = "b64$"


def _derive_key(key_str: str) -> bytes:
    return hashlib.sha256(key_str.encode("utf-8")).digest()


AES_KEY_BYTES = _derive_key(_settings.AES_KEY)


def hash_password(plain: str) -> str:
    hashed = _pwd_context.hash(plain)
    # 统一把哈希结果做 base64 包装后再落库，避免明文可读形态直接暴露在数据库中。
    encoded = base64.b64encode(hashed.encode("utf-8")).decode("utf-8")
    return f"{PASSWORD_STORAGE_PREFIX}{encoded}"


def _unwrap_password_storage(stored: str) -> str | None:
    if not stored:
        return None
    if not stored.startswith(PASSWORD_STORAGE_PREFIX):
        return None
    encoded = stored[len(PASSWORD_STORAGE_PREFIX) :]
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None


def verify_password(plain: str, hashed: str) -> bool:
    normalized_hash = _unwrap_password_storage(hashed)
    if not normalized_hash:
        return False
    try:
        return _pwd_context.verify(plain, normalized_hash)
    except ValueError:
        return False


def create_token(sub: str, expires: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
    }
    return jwt.encode(payload, _settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _settings.SECRET_KEY, algorithms=["HS256"])


def is_token_invalid_error(exc: Exception) -> bool:
    return isinstance(exc, JWTError)


def encrypt_password(plain: str) -> str:
    aesgcm = AESGCM(AES_KEY_BYTES)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")


def decrypt_password(cipher_b64: str) -> str:
    data = base64.b64decode(cipher_b64)
    nonce, ct = data[:12], data[12:]
    aesgcm = AESGCM(AES_KEY_BYTES)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")
