"""
Forge Server — Pydantic Settings

无硬编码 HARD RULE 的落地点：所有环境相关值、业务常量都从 .env / 环境变量读入。
业务代码通过 get_settings() 拿到本对象，**不**直接读 os.environ。
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # ─────────────────────────────────────────────────────────
    # Server
    # ─────────────────────────────────────────────────────────
    server_host: str = Field(default="0.0.0.0")
    server_port: int = Field(default=13001)
    server_reload: bool = Field(default=False)
    server_log_level: Literal["debug", "info", "warning", "error"] = "info"

    # ─────────────────────────────────────────────────────────
    # Database (字段化 / 4 provider)
    # ─────────────────────────────────────────────────────────
    database_type: Literal["postgres", "mysql", "oracle", "tidb"] = "postgres"
    database_host: str
    database_port: int
    database_username: str
    database_password: str
    database_database: str
    database_pool_size: int = 10
    database_ssl_mode: Literal["disable", "require", "verify-full"] = "disable"

    # ─────────────────────────────────────────────────────────
    # Cache (字段化 / Redis)
    # ─────────────────────────────────────────────────────────
    cache_type: Literal["redis"] = "redis"
    cache_host: str
    cache_port: int
    cache_username: str = ""
    cache_password: str
    cache_db_app: int = 0
    cache_db_session: int = 1
    cache_db_celery_broker: int = 2
    cache_db_celery_result: int = 3

    # ─────────────────────────────────────────────────────────
    # Object Storage (字段化 / 8 provider, 公有云走 access key/secret)
    # ─────────────────────────────────────────────────────────
    object_storage_type: Literal[
        "local",
        "s3",
        "azure-blob",
        "aliyun-oss",
        "google-storage",
        "tencent-cos",
        "volcengine-tos",
        "huawei-obs",
    ] = "local"

    # local 双模
    object_storage_local_mode: Literal["filesystem", "minio"] = "filesystem"
    object_storage_local_path: str = ""
    object_storage_local_minio_host: str = ""
    object_storage_local_minio_port: int = 0
    object_storage_local_minio_username: str = ""
    object_storage_local_minio_password: str = ""

    # 公有云通用字段（按 provider 选填，业务代码经 adapter 读取）
    object_storage_endpoint: str = ""
    object_storage_region: str = ""
    object_storage_access_key_id: str = ""
    object_storage_access_key_secret: str = ""
    object_storage_bucket_license_files: str = ""
    object_storage_bucket_public_keys: str = ""
    object_storage_bucket_audit: str = ""

    # ─────────────────────────────────────────────────────────
    # Signing / Key Storage
    # ─────────────────────────────────────────────────────────
    signing_algorithms_enabled: list[Literal["ed25519", "rsa2048", "rsa4096", "sm2"]] = [
        "ed25519"
    ]
    signing_default_algorithm: Literal["ed25519", "rsa2048", "rsa4096", "sm2"] = "ed25519"

    key_storage_backend: Literal["local_file", "object_storage", "kms"] = "local_file"
    key_storage_local_path: str = ""
    key_master_passphrase: str  # 私钥落盘加密的主口令 — 绝不可写日志

    # ─────────────────────────────────────────────────────────
    # Auth
    # ─────────────────────────────────────────────────────────
    auth_session_secret: str
    auth_session_max_age_seconds: int = 60 * 60 * 24 * 7

    # API Key TTL upper bound — keeps customer-side mistakes from issuing
    # forever-keys. Default 10 years (any longer should re-issue, not extend).
    api_key_max_expires_in_days: int = 365 * 10

    auth_sso_enabled: bool = False
    auth_sso_protocol: Literal["oauth2", "saml", "oidc"] = "oauth2"
    # 具体 SSO 配置由前端管理员界面配置 + 落地 db；本处仅默认开关

    # Default admin bootstrap (forge .agent.md spec). All three values are
    # overridable via env so customers don't ship with the documented defaults.
    bootstrap_admin_username: str = "Admin"
    bootstrap_admin_email: str = "admin@forge.local"
    bootstrap_admin_password: str = "admin@forge.local"

    # /auth/login brute-force defense. After `threshold` failures within
    # `window_seconds` from the same (ip, username), respond 429 + Retry-After.
    auth_login_rate_limit_threshold: int = 5
    auth_login_rate_limit_window_seconds: int = 15 * 60

    # ─────────────────────────────────────────────────────────
    # Verifier API
    # ─────────────────────────────────────────────────────────
    verifier_api_require_mtls: bool = False
    heartbeat_default_interval_seconds: int = 60 * 60 * 24  # 24h

    # ─────────────────────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────────────────────
    log_format: Literal["json", "text"] = "json"  # 生产 / 交付一律 json

    # ─────────────────────────────────────────────────────────
    # External integrations (默认全关，私有化场景按需打开)
    # ─────────────────────────────────────────────────────────
    telemetry_enabled: bool = False
    error_reporting_enabled: bool = False

    # ─────────────────────────────────────────────────────────
    # Background tasks (forge-worker / forge-scheduler 用)
    # ─────────────────────────────────────────────────────────
    # Audit 保留天数；超期记录被 forge-scheduler 触发的 daily task 删除。
    # 0 = 不清理（合规要求"永不删"时设 0）。
    audit_retention_days: int = 365
    # License 到期前 N 天开始进 admin UI 警告列表。
    license_expiry_warn_days: int = 30
    # Heartbeats 表保留天数；超期归档到 object_storage（bucket_audit）。
    heartbeat_retention_days: int = 90

    # 默认密码 strict-mode：若启用，所有 /api/v1/* 写操作在用户用 bootstrap_admin_password
    # 登录的 session 下都会被拒绝（强制改密前不能做实事）。
    # 默认 false 兼容旧客户；private prod 强烈建议 true。
    auth_block_writes_on_default_password: bool = False

    # 启动期 strict 模式：DB / Cache / KeyStorage 健康自检任一失败 → sys.exit(1)。
    # 默认 true（生产）；本地开发可设 false 让缺 service 时也能跑起来看 UI。
    startup_strict: bool = True

    # Webhook —— 业务事件外推（license.issued / revoked / expiring 等）
    # 留空 = 不推送；非空 = POST 到该 URL（带 X-Forge-Signature HMAC）
    webhook_url: str = ""
    webhook_signing_secret: str = ""

    # Heartbeat 异常检测：同 license 在 anomaly_window_seconds 内出现 ≥ N 不同
    # 指纹 → 触发 audit + 可选 webhook。默认窗口 1 小时、N=3。
    heartbeat_anomaly_window_seconds: int = 60 * 60
    heartbeat_anomaly_threshold: int = 3

    # API Key 配额：默认 0 = 不限；> 0 时按 key_id+小时统计；超 → 429
    api_key_rate_limit_per_hour: int = 0
