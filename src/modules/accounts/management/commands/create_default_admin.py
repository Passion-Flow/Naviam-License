"""创建默认超管账号。

用法：
    python manage.py create_default_admin

从 settings 读取 DEFAULT_ADMIN_* 变量；若账号已存在则跳过。
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from modules.accounts.models import User


class Command(BaseCommand):
    help = "Create default super-admin from settings if not exists"

    def handle(self, *args, **options) -> None:
        email = settings.DEFAULT_ADMIN_EMAIL
        password = settings.DEFAULT_ADMIN_PASSWORD

        if User.objects.filter(username=email).exists():
            self.stdout.write(self.style.WARNING(f"admin '{email}' already exists; skipping"))
            return

        User.objects.create_superuser(
            username=email,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"created default admin: {email}"))
