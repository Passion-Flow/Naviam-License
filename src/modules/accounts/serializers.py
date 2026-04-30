"""DRF serializers for accounts."""
from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, trim_whitespace=False)
    password = serializers.CharField(required=True, write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        request = self.context.get("request")
        try:
            user = User.objects.get(email=attrs["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"detail": "invalid credentials"},
                code="authentication_failed",
            )
        authenticated_user = authenticate(
            request=request,
            username=user.username,
            password=attrs["password"],
        )
        if not authenticated_user:
            raise serializers.ValidationError(
                {"detail": "invalid credentials"},
                code="authentication_failed",
            )
        if not getattr(authenticated_user, "is_active", True):
            raise serializers.ValidationError(
                {"detail": "account disabled"},
                code="account_disabled",
            )
        attrs["user"] = authenticated_user
        return attrs


class TOTPVerifySerializer(serializers.Serializer):
    code = serializers.CharField(required=True, max_length=8, trim_whitespace=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs: dict) -> dict:
        user: User = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError(
                {"old_password": "incorrect"},
                code="wrong_password",
            )
        return attrs


class DisableTOTPSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        user: User = self.context["request"].user
        if not user.check_password(attrs["password"]):
            raise serializers.ValidationError(
                {"password": "incorrect"},
                code="wrong_password",
            )
        return attrs


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_superadmin",
            "must_change_pw",
            "totp_confirmed",
            "created_at",
        ]
        read_only_fields = fields
