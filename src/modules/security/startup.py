"""启动期校验。

V1：
- 生产环境 DEBUG=False。
- SECRET_KEY 不是默认值。
- 签名私钥文件存在（如配置了路径）。
- 审计私钥文件存在。
- 审计哈希链完整性校验通过（顺序遍历 + hmac.compare_digest 比对）。
- 默认凭证已被替换（admin 密码 / Postgres / Redis 默认值绝不能进生产）。

失败时立即抛异常，拒绝启动。
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, register

# === 默认值黑名单 ===
# .env.example 中提供的"开箱可跑"默认值；这些值进生产即认为部署疏忽。
# 任意字段命中则启动失败 — 没有商量、没有 override flag。
_DEFAULT_FORBIDDEN: dict[str, tuple[str, ...]] = {
    # base.py 内部 fallback + .env.example 占位
    "SECRET_KEY":             ("change-me-session-secret", "CHANGE_ME_DJANGO_SECRET_KEY", "",),
    "DEFAULT_ADMIN_PASSWORD": ("admin@workerspace.ai",),
    # Phase 1 命名规范的 dev 默认密码
    "POSTGRES_PASSWORD":      (
        "Postgres@!QAZxsw2.",
        "CHANGE_ME_POSTGRES_APP_PASSWORD",
        "CHANGE_ME_LONG_RANDOM_PASSWORD",
    ),
    "REDIS_PASSWORD":         (
        "Redis@!QAZxsw2.",
        "CHANGE_ME_REDIS_PASSWORD",
        "CHANGE_ME_LONG_RANDOM_PASSWORD_AT_LEAST_32_BYTES",
    ),
    "SIGNING_KEY_PASSPHRASE": ("CHANGE_ME_SIGNING_KEY_PASSPHRASE", "",),
    "AUDIT_KEY_PASSPHRASE":   ("CHANGE_ME_AUDIT_KEY_PASSPHRASE", "",),
}


def _check_default_credentials() -> list[Error]:
    """生产环境禁止使用 .env.example 默认值。"""
    errors: list[Error] = []
    for setting_name, forbidden_values in _DEFAULT_FORBIDDEN.items():
        actual = getattr(settings, setting_name, None)
        if actual is None:
            # 未配置：本函数不强制要求每项都有值（其他 check 各自负责存在性）
            continue
        if actual in forbidden_values:
            errors.append(
                Error(
                    f"{setting_name} is the .env.example default — must be replaced before production deploy",
                    id="security.E010",
                    hint=(
                        f"Set {setting_name} to a strong random value via your secrets manager. "
                        "These defaults appear in the public README and are world-known."
                    ),
                )
            )
    return errors


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

    # === 默认凭证校验（Phase 10）===
    if not settings.DEBUG:
        errors.extend(_check_default_credentials())

    # === 审计链完整性（crypto-spec.md §6） ===
    # 启动时全链 hash 校验：从最早到最新顺序计算并与表中 hash 字段比对。
    # 任一记录被改动会导致后续所有记录的 hash 失配。
    if not settings.DEBUG:
        try:
            from django.db import connection
            from modules.audit.services import AuditChainCorrupted, verify_chain

            # 仅在 audit 表已迁移完成的部署里跑（test/dev 首次启动可能还没建表）
            if "audit_event" in connection.introspection.table_names():
                try:
                    verify_chain()
                except AuditChainCorrupted as exc:
                    errors.append(
                        Error(
                            f"Audit chain corruption at event id={exc.event_id}: {exc.reason}",
                            id="security.E004",
                            hint=(
                                "Hash chain integrity is broken — possible tampering. "
                                "Investigate before allowing writes; do not bypass."
                            ),
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            # 启动期校验自身故障不应阻塞所有部署；记录为 Warning-级 Error
            errors.append(
                Error(
                    f"Audit chain verify failed to run: {exc!r}",
                    id="security.E005",
                )
            )

    return errors
