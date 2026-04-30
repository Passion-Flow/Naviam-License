"""Account business services.

职责：
- 密码创建与校验（Argon2id 由 Django 默认 hasher 处理）。
- TOTP secret / recovery code 的加解密（Fernet，密钥派生自 SECRET_KEY）。
- 登录尝试记录。
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from pyotp import TOTP

from .models import LoginAttempt, User


def _fernet() -> Fernet:
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(plain: bytes) -> bytes:
    return _fernet().encrypt(plain)


def _decrypt(cipher: bytes) -> bytes:
    return _fernet().decrypt(cipher)


def setup_totp(user: User) -> tuple[str, str]:
    """为用户生成 TOTP secret；返回 (secret, provisioning_uri)。"""
    secret = TOTP.random_base32()
    user.totp_secret = _encrypt(secret.encode())
    user.totp_confirmed = False
    user.save(update_fields=["totp_secret", "totp_confirmed", "updated_at"])
    uri = TOTP(secret).provisioning_uri(
        name=user.username,
        issuer_name=settings.APP_NAME,
    )
    return secret, uri


def confirm_totp(user: User, code: str) -> bool:
    """用户输入一次性 code，校验通过后标记 2FA 就绪，并生成 recovery codes。"""
    if not user.totp_secret:
        return False
    secret = _decrypt(user.totp_secret).decode()
    totp = TOTP(secret)
    if not totp.verify(code, valid_window=1):
        return False
    codes = [secrets.token_hex(4) for _ in range(8)]
    user.recovery_codes = _encrypt(json.dumps(codes).encode())
    user.totp_confirmed = True
    user.save(update_fields=["recovery_codes", "totp_confirmed", "updated_at"])
    return True


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret:
        return False
    secret = _decrypt(user.totp_secret).decode()
    return TOTP(secret).verify(code, valid_window=1)


def disable_totp(user: User) -> None:
    user.totp_secret = None
    user.recovery_codes = None
    user.totp_confirmed = False
    user.save(update_fields=["totp_secret", "recovery_codes", "totp_confirmed", "updated_at"])


def change_password(user: User, new_password: str) -> None:
    user.set_password(new_password)
    user.must_change_pw = False
    user.save(update_fields=["password", "must_change_pw", "updated_at"])


def log_login_attempt(
    *,
    username: str,
    ip: str | None,
    ua: str | None,
    result: str,
    reason: str | None = None,
) -> None:
    LoginAttempt.objects.create(
        username=username,
        ip=ip or "0.0.0.0",
        ua=ua,
        result=result,
        reason=reason,
    )


def get_recovery_codes(user: User) -> list[str] | None:
    if not user.recovery_codes:
        return None
    return json.loads(_decrypt(user.recovery_codes).decode())
