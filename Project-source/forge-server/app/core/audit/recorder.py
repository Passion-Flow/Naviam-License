"""审计写入助手 —— 统一从 Request 抽取元数据，统一空仓储兜底。

调用方写一行：
    await record_audit(state, request, action=..., actor_type=..., actor_id=..., ...)

不抛异常（审计失败不能阻断业务流）；失败时仅记录到 logger.warning。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request

    from app.state import AppState

logger = logging.getLogger(__name__)


ACTOR_USER = "user"
ACTOR_API_KEY = "api_key"
ACTOR_SYSTEM = "system"

ACTION_AUTH_LOGIN_SUCCESS = "auth.login.success"
ACTION_AUTH_LOGIN_FAILURE = "auth.login.failure"
ACTION_AUTH_LOGOUT = "auth.logout"
ACTION_AUTH_PASSWORD_CHANGED = "auth.password.changed"
ACTION_ADMIN_USER_CREATED = "admin.user.created"
ACTION_ADMIN_USER_DEACTIVATED = "admin.user.deactivated"
ACTION_ADMIN_USER_REACTIVATED = "admin.user.reactivated"
ACTION_ADMIN_USER_PASSWORD_RESET = "admin.user.password_reset"
ACTION_LICENSE_ISSUED = "license.issued"
ACTION_LICENSE_REVOKED = "license.revoked"
ACTION_CUSTOMER_CREATED = "customer.created"
ACTION_CUSTOMER_UPDATED = "customer.updated"
ACTION_CUSTOMER_ARCHIVED = "customer.archived"
ACTION_PRODUCT_CREATED = "product.created"
ACTION_PRODUCT_UPDATED = "product.updated"
ACTION_KEY_GENERATED = "key.generated"
ACTION_KEY_ROTATED = "key.rotated"
ACTION_KEY_REVOKED = "key.revoked"
ACTION_KEY_DELETED = "key.deleted"
ACTION_LICENSE_DELETED = "license.deleted"
ACTION_CUSTOMER_DELETED = "customer.deleted"
ACTION_PRODUCT_DELETED = "product.deleted"
ACTION_APIKEY_DELETED = "apikey.deleted"
ACTION_ADMIN_USER_DELETED = "admin.user.deleted"


_REQUEST_ID_HEADER = "x-request-id"
_FORWARDED_FOR_HEADER = "x-forwarded-for"


def _extract_client_ip(request: "Request | None") -> str | None:
    if request is None:
        return None
    fwd = request.headers.get(_FORWARDED_FOR_HEADER)
    if fwd:
        return fwd.split(",", 1)[0].strip() or None
    client = request.client
    return client.host if client else None


def _extract_request_id(request: "Request | None") -> str | None:
    if request is None:
        return None
    return request.headers.get(_REQUEST_ID_HEADER)


def _extract_user_agent(request: "Request | None") -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    if ua is None:
        return None
    return ua[:256]


async def record_audit(
    state: "AppState",
    request: "Request | None",
    *,
    actor_type: str,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """写一条审计；仓储未配置时静默跳过（in-memory 部署）。

    审计失败不允许阻断业务调用 —— 任何异常都被吞掉并打 warning 日志。
    """
    repo = state.audit_log_repository
    if repo is None:
        return
    try:
        await repo.record(  # type: ignore[union-attr]
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            request_id=_extract_request_id(request),
            client_ip=_extract_client_ip(request),
            user_agent=_extract_user_agent(request),
        )
    except Exception:
        logger.warning("audit record failed for action=%s target=%s", action, target_id, exc_info=True)
