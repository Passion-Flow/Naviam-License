"""Account models: User + LoginAttempt.

User 继承 AbstractBaseUser + PermissionsMixin，完全匹配 V1 单超管模型。
"""
from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def get_by_natural_key(self, username: str) -> "User":
        return self.get(username=username)
    def create_user(
        self,
        username: str,
        email: str,
        password: str | None = None,
        **extra: object,
    ) -> "User":
        if not email:
            raise ValueError("email required")
        # username 强制与 email 一致（邮箱格式）
        username = email
        user = self.model(username=username, email=email, **extra)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        username: str,
        email: str,
        password: str | None = None,
        **extra: object,
    ) -> "User":
        extra.setdefault("is_active", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_superadmin", True)
        extra.setdefault("must_change_pw", True)
        return self.create_user(username, email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_superadmin = models.BooleanField(default=False)
    must_change_pw = models.BooleanField(default=True)
    totp_secret = models.BinaryField(null=True, blank=True)
    totp_confirmed = models.BooleanField(default=False)
    recovery_codes = models.BinaryField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.username


class LoginAttempt(models.Model):
    id = models.BigAutoField(primary_key=True)
    username = models.CharField(max_length=150)
    ip = models.GenericIPAddressField()
    ua = models.TextField(null=True, blank=True)
    result = models.CharField(
        max_length=16,
        choices=[
            ("success", "success"),
            ("bad_password", "bad_password"),
            ("locked", "locked"),
            ("2fa_failed", "2fa_failed"),
        ],
    )
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "accounts_login_attempt"
        indexes = [
            models.Index(fields=["username", "-created_at"]),
            models.Index(fields=["ip", "-created_at"]),
        ]
