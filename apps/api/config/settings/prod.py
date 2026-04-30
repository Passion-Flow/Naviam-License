"""Production settings.

启动时由 modules.security.startup 校验关键安全参数；任意一项失败立即拒启动。
"""
from .base import *  # noqa: F401,F403

DEBUG = False
SECURE_SSL_REDIRECT = True
SECURE_HSTS_PRELOAD = True
