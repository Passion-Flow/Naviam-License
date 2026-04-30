"""Development overrides.

仅本机使用；生产严禁使用本配置。
"""
from .base import *  # noqa: F401,F403

DEBUG = True
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 0
SECURE_SSL_REDIRECT = False

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000"]
