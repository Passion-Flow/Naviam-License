"""DRF permissions.

V1 仅单超管；所有写操作都要求 IsSuperAdmin。
读操作（如 list licenses）后续可开放给只读角色，V1 先统一要求登录。
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "is_superadmin", False)
        )
