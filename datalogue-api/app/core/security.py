import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_settings = get_settings()


def _derive_key(key_str: str) -> bytes:
    return hashlib.sha256(key_str.encode("utf-8")).digest()


AES_KEY_BYTES = _derive_key(_settings.AES_KEY)


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
