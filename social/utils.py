import base64
import os
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet | None:
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if not key:
        return None
    # 如果提供的是原始 key（32 urlsafe base64），直接使用；否则从明文派生（仅开发环境）
    try:
        Fernet(key)
        return Fernet(key)
    except Exception:
        # 开发兜底：将明文转 urlsafe_b64（不建议生产）
        padded = base64.urlsafe_b64encode(key.encode().ljust(32, b'0')[:32])
        return Fernet(padded)


def encrypt_text(plaintext: str | None) -> str:
    if not plaintext:
        return ''
    f = _get_fernet()
    if not f:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext: str | None) -> str:
    if not ciphertext:
        return ''
    f = _get_fernet()
    if not f:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # 兼容旧明文
        return ciphertext


