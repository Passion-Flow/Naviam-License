"""POST /api/v1/licenses/bulk-revoke —— 批量吊销 license。

Admin Session only（敏感操作，禁止 API Key 调用）。
请求体：{ "license_ids": [...], "reason": "..." }，至多 200 条/次。

返回每条的结果（已吊销 / 不存在 / 已是吊销态）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import ACTION_LICENSE_REVOKED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class BulkRevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    license_ids: list[str] = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=512)


class BulkRevokeItem(BaseModel):
    license_id: str
    status: Literal["revoked", "not_found", "already_revoked"]


class BulkRevokeResponse(BaseModel):
    items: list[BulkRevokeItem]
    revoked_count: int
    not_found_count: int
    already_revoked_count: int


@router.post(
    "/bulk-revoke",
    response_model=BulkRevokeResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_revoke(
    body: BulkRevokeBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> BulkRevokeResponse:
    repo = state.license_repository
    # de-dup 同样 license_id；保持原顺序
    seen: set[str] = set()
    ordered_ids = [x for x in body.license_ids if not (x in seen or seen.add(x))]

    items: list[BulkRevokeItem] = []
    revoked_count = not_found_count = already_count = 0

    # 提前拉一遍已吊销列表，避免每条 license 都查一次 store
    existing = {e.license_id for e in await state.revocation_store.list_entries()}

    for lid in ordered_ids:
        if repo is not None:
            row = await repo.get(lid)  # type: ignore[union-attr]
            if row is None:
                items.append(BulkRevokeItem(license_id=lid, status="not_found"))
                not_found_count += 1
                continue
        if lid in existing:
            items.append(BulkRevokeItem(license_id=lid, status="already_revoked"))
            already_count += 1
            continue
        await state.crl_manager.revoke(lid, reason=body.reason, revoked_by=actor_id)
        items.append(BulkRevokeItem(license_id=lid, status="revoked"))
        revoked_count += 1

    # 一条整批审计 + 一条 webhook（载荷里塞每条结果）
    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_LICENSE_REVOKED,
        target_type="license_bulk",
        target_id=f"bulk:{len(ordered_ids)}",
        payload={
            "reason": body.reason,
            "ids": ordered_ids,
            "revoked": revoked_count,
            "not_found": not_found_count,
            "already_revoked": already_count,
        },
    )
    from app.core.webhooks import emit_event
    await emit_event(
        "license.bulk_revoked",
        {
            "actor": f"admin:{actor_id}",
            "reason": body.reason,
            "revoked": revoked_count,
            "items": [i.model_dump() for i in items],
        },
    )

    now = datetime.now(timezone.utc)  # noqa: F841 — kept for symmetry; not in response
    return BulkRevokeResponse(
        items=items,
        revoked_count=revoked_count,
        not_found_count=not_found_count,
        already_revoked_count=already_count,
    )
