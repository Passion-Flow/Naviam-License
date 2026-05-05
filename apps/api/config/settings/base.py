"""Base settings shared across environments.

每个安全相关条目都直接对应 docs/security/* 与 docs/design/02-开发技术栈设计.md。
任何降级都必须经过 ADR。
"""
from __future__ import annotations

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_DIR = BASE_DIR.parent.parent

env = environ.Env()
environ.Env.read_env(str(PROJECT_DIR / ".env"))

# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="change-me-session-secret")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://127.0.0.1:3000"])

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = env("APP_TIMEZONE", default="Asia/Shanghai")
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------------------------------
# Apps
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "axes",
    "corsheaders",
    # 业务模块（src/modules）
    "modules.security",
    "modules.accounts",
    "modules.customers",
    "modules.products",
    "modules.licenses",
    "modules.activations",
    "modules.audit",
    "modules.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -----------------------------------------------------------------------------
# Database (Postgres)
# 团队约定：所有数据源走 type/host/port/username/password 分字段，禁止 URL 拼接。
# -----------------------------------------------------------------------------
POSTGRES_TYPE = env("POSTGRES_TYPE", default="postgresql")
POSTGRES_HOST = env("POSTGRES_HOST", default="127.0.0.1")
POSTGRES_PORT = env.int("POSTGRES_PORT", default=5432)
POSTGRES_DB = env("POSTGRES_DB", default="naviam_license")
POSTGRES_USERNAME = env("POSTGRES_USERNAME", default=env("POSTGRES_USER", default="naviam_license"))
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD")

DATABASES = {
    "default": {
        "ENGINE": f"django.db.backends.{POSTGRES_TYPE}",
        "HOST": POSTGRES_HOST,
        "PORT": POSTGRES_PORT,
        "USER": POSTGRES_USERNAME,
        "PASSWORD": POSTGRES_PASSWORD,
        "NAME": POSTGRES_DB,
        "OPTIONS": {"sslmode": "prefer"},
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------------------------------------------
# Cache / Session / Ratelimit (Redis)
# 同样按 type/host/port/username/password 拆分；Redis URL 仅在交付给 django-redis
# 后端时由本模块内部组装，不再暴露为环境变量。
# -----------------------------------------------------------------------------
REDIS_TYPE = env("REDIS_TYPE", default="redis")
REDIS_HOST = env("REDIS_HOST", default="127.0.0.1")
REDIS_PORT = env.int("REDIS_PORT", default=6379)
REDIS_USERNAME = env("REDIS_USERNAME", default="")
REDIS_PASSWORD = env("REDIS_PASSWORD")
REDIS_DB = env.int("REDIS_DB", default=0)

# 仅供 django-redis 后端使用；从分字段在内存中组装，不读 REDIS_URL 环境变量。
from urllib.parse import quote as _urlquote  # noqa: E402

_redis_userinfo = (
    f"{_urlquote(REDIS_USERNAME, safe='')}:{_urlquote(REDIS_PASSWORD, safe='')}"
    if REDIS_USERNAME
    else f":{_urlquote(REDIS_PASSWORD, safe='')}"
)
REDIS_URL = f"{REDIS_TYPE}://{_redis_userinfo}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"db": REDIS_DB},
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=12 * 3600)
SESSION_SAVE_EVERY_REQUEST = True

# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# django-axes
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # 15 分钟
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True

# -----------------------------------------------------------------------------
# Cookies / CSRF / Security headers
# -----------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"

SECURE_HSTS_SECONDS = 31_536_000  # 1 年
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

# CSP（django-csp）
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", "data:")
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_FORM_ACTION = ("'self'",)
CSP_BASE_URI = ("'self'",)

# -----------------------------------------------------------------------------
# DRF
# -----------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "60/min",
        "anon": "20/min",
        # === Phase 11：敏感端点单独限流（per-IP，叠加在 anon 之上） ===
        # 对应 ScopedRateThrottle；view 通过 throttle_scope 字段引用
        "auth_login": "5/min",            # 5 次/分钟 — 防爆破；axes 兜底锁定 5 次失败
        "auth_totp": "10/min",            # 用户输错码可重试，但限制总速率
        "auth_change_password": "5/min",  # 改密同样敏感
    },
    "EXCEPTION_HANDLER": "modules.security.exceptions.exception_handler",
}

# -----------------------------------------------------------------------------
# Static
# -----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# -----------------------------------------------------------------------------
# License signing keys
# -----------------------------------------------------------------------------
SIGNING_KEY_PATH = env("SIGNING_KEY_PATH", default=str(PROJECT_DIR / "secrets" / "signing.age"))
SIGNING_KEY_PASSPHRASE = env("SIGNING_KEY_PASSPHRASE", default=None)
SIGNING_KEY_BACKEND = env("SIGNING_KEY_BACKEND", default="file")  # file | kms | hsm
SIGNING_KEY_KID = env("SIGNING_KEY_KID", default="kid-1")

AUDIT_KEY_PATH = env("AUDIT_KEY_PATH", default=str(PROJECT_DIR / "secrets" / "audit.age"))
AUDIT_KEY_PASSPHRASE = env("AUDIT_KEY_PASSPHRASE", default=None)
AUDIT_KEY_KID = env("AUDIT_KEY_KID", default="audit-1")

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "modules.security.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# -----------------------------------------------------------------------------
# Application identity
# -----------------------------------------------------------------------------
APP_NAME = env("APP_NAME", default="License")
APP_SLUG = env("APP_SLUG", default="license")
# 历史上 .env.example 用 ADMIN_*，base.py 读 DEFAULT_ADMIN_*，env 永不生效。
# 现在两个名字都接受，DEFAULT_ADMIN_* 优先（与 startup.py / management command 一致）。
DEFAULT_ADMIN_USERNAME = env(
    "DEFAULT_ADMIN_USERNAME",
    default=env("ADMIN_USERNAME", default="Admin"),
)
DEFAULT_ADMIN_EMAIL = env(
    "DEFAULT_ADMIN_EMAIL",
    default=env("ADMIN_EMAIL", default="admin@workerspace.ai"),
)
DEFAULT_ADMIN_PASSWORD = env(
    "DEFAULT_ADMIN_PASSWORD",
    default=env("ADMIN_PASSWORD", default="admin@workerspace.ai"),
)

# -----------------------------------------------------------------------------
# CORS (dev only — prod uses explicit allow-list)
# -----------------------------------------------------------------------------
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://127.0.0.1:3000", "http://localhost:3000"],
)
