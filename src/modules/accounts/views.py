"""Account DRF views.

端点：
- POST /v1/auth/login/          用户名+密码登录；若已绑 2FA 返回 requires_2fa=true。
- POST /v1/auth/totp/           登录流程中的 2FA 校验。
- POST /v1/auth/logout/         登出。
- GET  /v1/auth/me/             当前用户信息。
- POST /v1/auth/change-password/ 强制/主动改密。
- GET  /v1/auth/totp/setup/     获取 2FA QR URI。
- POST /v1/auth/totp/setup/     确认绑定 2FA。
"""
from __future__ import annotations

from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import LoginAttempt, User
from .permissions import IsSuperAdmin
from .serializers import (
    ChangePasswordSerializer,
    DisableTOTPSerializer,
    LoginSerializer,
    MeSerializer,
    TOTPVerifySerializer,
)
from .services import (
    change_password,
    confirm_totp,
    disable_totp,
    get_recovery_codes,
    log_login_attempt,
    setup_totp,
    verify_totp,
)
from modules.audit.services import append_event
from modules.security.signing import get_audit_signer


def _client_ip(request: Request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _client_ua(request: Request) -> str | None:
    return request.META.get("HTTP_USER_AGENT")


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def login_view(request: Request) -> Response:
    ser = LoginSerializer(data=request.data, context={"request": request})
    if not ser.is_valid():
        log_login_attempt(
            username=request.data.get("email", "")[:150],
            ip=_client_ip(request),
            ua=_client_ua(request),
            result="bad_password",
        )
        return Response(ser.errors, status=status.HTTP_401_UNAUTHORIZED)

    user: User = ser.validated_data["user"]

    if user.totp_confirmed:
        request.session["pending_2fa_user_id"] = str(user.id)
        return Response(
            {"requires_2fa": True, "message": "totp verification required"},
            status=status.HTTP_202_ACCEPTED,
        )

    django_login(request, user)
    user.last_login = timezone.now()
    user.last_login_ip = _client_ip(request)
    user.save(update_fields=["last_login", "last_login_ip"])
    log_login_attempt(
        username=user.username,
        ip=_client_ip(request),
        ua=_client_ua(request),
        result="success",
    )
    audit_signer = get_audit_signer()
    append_event(
        actor_id=str(user.id),
        actor_name=user.username,
        actor_kind="user",
        actor_ip=_client_ip(request),
        action="login",
        target_kind="user",
        target_id=str(user.id),
        payload={"method": "password", "user_agent": _client_ua(request) or ""},
        signer=audit_signer,
    )
    return Response(
        {"requires_2fa": False, "user": MeSerializer(user).data},
        status=status.HTTP_200_OK,
    )


# ScopedRateThrottle 在每次请求时从 view 实例上读 throttle_scope；
# @api_view 会把 function 包成 WrappedAPIView 类，所以 throttle_scope 必须挂到
# .cls 而不是 function 对象本身（function 上的属性不会传递到 class）。
login_view.cls.throttle_scope = "auth_login"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def totp_verify_view(request: Request) -> Response:
    pending_id = request.session.get("pending_2fa_user_id")
    if not pending_id:
        return Response(
            {"detail": "no pending 2fa session"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(id=pending_id)
    except User.DoesNotExist:
        request.session.pop("pending_2fa_user_id", None)
        return Response(
            {"detail": "session expired"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ser = TOTPVerifySerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    code = ser.validated_data["code"]

    if not verify_totp(user, code):
        log_login_attempt(
            username=user.username,
            ip=_client_ip(request),
            ua=_client_ua(request),
            result="2fa_failed",
        )
        return Response(
            {"detail": "invalid totp code"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    request.session.pop("pending_2fa_user_id", None)
    django_login(request, user)
    user.last_login = timezone.now()
    user.last_login_ip = _client_ip(request)
    user.save(update_fields=["last_login", "last_login_ip"])
    log_login_attempt(
        username=user.username,
        ip=_client_ip(request),
        ua=_client_ua(request),
        result="success",
    )
    audit_signer = get_audit_signer()
    append_event(
        actor_id=str(user.id),
        actor_name=user.username,
        actor_kind="user",
        actor_ip=_client_ip(request),
        action="login",
        target_kind="user",
        target_id=str(user.id),
        payload={"method": "totp", "user_agent": _client_ua(request) or ""},
        signer=audit_signer,
    )
    return Response(
        {"user": MeSerializer(user).data},
        status=status.HTTP_200_OK,
    )


totp_verify_view.cls.throttle_scope = "auth_totp"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    user = request.user
    audit_signer = get_audit_signer()
    append_event(
        actor_id=str(user.id),
        actor_name=user.username,
        actor_kind="user",
        actor_ip=_client_ip(request),
        action="logout",
        target_kind="user",
        target_id=str(user.id),
        payload={},
        signer=audit_signer,
    )
    django_logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request: Request) -> Response:
    return Response(MeSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def change_password_view(request: Request) -> Response:
    ser = ChangePasswordSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    user: User = request.user
    change_password(user, ser.validated_data["new_password"])
    django_logout(request)
    return Response(
        {"detail": "password changed; please re-login"},
        status=status.HTTP_200_OK,
    )


change_password_view.cls.throttle_scope = "auth_change_password"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def login_history_view(request: Request) -> Response:
    attempts = (
        LoginAttempt.objects.filter(username=request.user.username)
        .order_by("-created_at")[:50]
    )
    data = [
        {
            "id": a.id,
            "ip": a.ip,
            "ua": a.ua,
            "result": a.result,
            "created_at": a.created_at,
        }
        for a in attempts
    ]
    return Response(data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def totp_setup_view(request: Request) -> Response:
    user: User = request.user
    if request.method == "GET":
        secret, uri = setup_totp(user)
        return Response({"secret": secret, "uri": uri})

    ser = TOTPVerifySerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    if confirm_totp(user, ser.validated_data["code"]):
        return Response(
            {
                "detail": "totp confirmed",
                "recovery_codes": get_recovery_codes(user) or [],
            }
        )
    return Response(
        {"detail": "invalid totp code"},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def totp_disable_view(request: Request) -> Response:
    ser = DisableTOTPSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    disable_totp(request.user)
    return Response({"detail": "totp disabled"}, status=status.HTTP_200_OK)
