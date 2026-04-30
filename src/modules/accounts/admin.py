"""Django admin for User.

V1 主要走前端 Console；admin 仅作为 fallback 与数据急救入口。
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "is_active", "is_superadmin", "must_change_pw", "created_at"]
    list_filter = ["is_active", "is_superadmin", "must_change_pw"]
    search_fields = ["username", "email"]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["username", "email", "password"]}),
        ("Status", {"fields": ["is_active", "is_superadmin", "must_change_pw"]}),
        ("2FA", {"fields": ["totp_confirmed"]}),
        ("Metadata", {"fields": ["id", "created_at", "updated_at", "last_login_ip"]}),
    ]

    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["username", "email", "password1", "password2"],
            },
        ),
    ]
