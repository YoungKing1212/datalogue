# ============================================================
# File Name   : test_security.py
# Description:
#   SQL 安全检查测试。
#
# Responsibilities:
#   - 验证危险 SQL 语句会被拒绝。
#   - 覆盖允许的只读查询模式。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
安全模块测试 — 密码加解密
"""

from app.core.security import encrypt_password, decrypt_password


class TestSecurity:
    """测试 AES 加密解密"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密后再解密应得到原文"""
        original = "my_secret_password_123"
        encrypted = encrypt_password(original)
        # 密文不应等于原文
        assert encrypted != original
        # 密文是 base64 格式
        decrypted = decrypt_password(encrypted)
        assert decrypted == original

    def test_encrypt_different_nonce(self):
        """同一密码两次加密结果应不同（nonce 随机）"""
        password = "same_password"
        enc1 = encrypt_password(password)
        enc2 = encrypt_password(password)
        assert enc1 != enc2
        # 但都能正确解密
        assert decrypt_password(enc1) == password
        assert decrypt_password(enc2) == password

    def test_encrypt_empty_string(self):
        """空字符串加密解密"""
        original = ""
        encrypted = encrypt_password(original)
        decrypted = decrypt_password(encrypted)
        assert decrypted == original

    def test_encrypt_unicode(self):
        """Unicode 密码加密解密"""
        original = "密码123!@#"
        encrypted = encrypt_password(original)
        decrypted = decrypt_password(encrypted)
        assert decrypted == original
