"""POST /api/v1/api-keys —— 签发一把新的 API Key。

仅 Admin Session（API Key 不允许自己签发新 key —— 防止 verifier 端 lateral movement）。
明文只在响应里返回一次，之后只能查 key_id / prefix。

可选 TTL：`expires_in_days` 给定时设过期时间；不给 = 永不过期（向后兼容旧客户）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.audit import ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories.api_keys import ApiKeyRepository
from app.state import AppState, get_state

router = APIRouter()


ACTION_APIKEY_ISSUED = "apikey.issued"


def _max_expires_in_days() -> int:
    """上限走 settings，避免硬编码 (HARD RULE 无硬编码)。默认 10 年。"""
    from app.settings import get_settings

    return get_settings().api_key_max_expires_in_days


class IssueApiKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1, max_length=128)
    project_label: str = Field(min_length=1, max_length=128)
    # None / 不传 = 永不过期（保留向后兼容）。
    # > 0 = 从 now 起的天数；上限由 settings.api_key_max_expires_in_days 决定。
    expires_in_days: int | None = Field(default=None, ge=1)

    @field_validator("expires_in_days")
    @classmethod
    def _check_max(cls, v: int | None) -> int | None:
        if v is not None and v > _max_expires_in_days():
            raise ValueError(f"expires_in_days exceeds max {_max_expires_in_days()}")
        return v


class IssueApiKeyResponse(BaseModel):
    key_id: str
    plaintext: str  # 仅签发时返回一次
    key_prefix: str
    customer_id: str
    project_label: str
    status: str
    created_at: datetime
    expires_at: datetime | None


@router.post("", response_model=IssueApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def issue_api_key(
    body: IssueApiKeyBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> IssueApiKeyResponse:
    if state.api_key_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api key backend not configured",
        )

    expires_at: datetime | None = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    repo: ApiKeyRepository = state.api_key_repository  # type: ignore[assignment]
    model, plaintext = await repo.issue(
        customer_id=body.customer_id,
        project_label=body.project_label,
        expires_at=expires_at,
    )

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_APIKEY_ISSUED,
        target_type="api_key",
        target_id=model.key_id,
        payload={
            "customer_id": body.customer_id,
            "project_label": body.project_label,
            "key_prefix": model.key_prefix,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )

    return IssueApiKeyResponse(
        key_id=model.key_id,
        plaintext=plaintext,
        key_prefix=model.key_prefix,
        customer_id=model.customer_id,
        project_label=model.project_label,
        status=model.status,
        created_at=model.created_at,
        expires_at=model.expires_at,
    )
