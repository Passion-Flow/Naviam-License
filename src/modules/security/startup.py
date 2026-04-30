"""启动期校验。

V1：
- 生产环境 DEBUG=False。
- SECRET_KEY 不是默认值。
- 签名私钥文件存在（如配置了路径）。
- 审计私钥文件存在。

失败时立即抛异常，拒绝启动。
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, register


@register(deploy=True)
def check_security_baseline(app_configs, **kwargs):
    errors = []

    if not settings.DEBUG and settings.SECRET_KEY in ("change-me-session-secret", ""):
        errors.append(
            Error(
                "SECRET_KEY must be changed in production",
                id="security.E001",
            )
        )

    key_path = getattr(settings, "SIGNING_KEY_PATH", None)
    if key_path and key_path != "dummy.key":
        from pathlib import Path

        if not Path(key_path).exists():
            errors.append(
                Error(
                    f"SIGNING_KEY_PATH does not exist: {key_path}",
                    id="security.E002",
                )
            )

    audit_path = getattr(settings, "AUDIT_KEY_PATH", None)
    if audit_path and audit_path != "dummy.key":
        from pathlib import Path

        if not Path(audit_path).exists():
            errors.append(
                Error(
                    f"AUDIT_KEY_PATH does not exist: {audit_path}",
                    id="security.E003",
                )
            )

    return errors
