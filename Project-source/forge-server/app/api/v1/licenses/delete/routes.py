"""DELETE /api/v1/licenses/{license_id} —— 硬删除 license（数据库直删）。

与 revoke 不同：revoke 把 license_id 入 CRL，license 行还在；
delete 直接把行删掉，并级联删除该 license 的所有 heartbeat / nonce / revocation 条目。
不可恢复。

工作流：审计可疑数据 / 客户解约后彻底清理；与 revoke 选择互斥。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.audit import ACTION_LICENSE_DELETED, ACTOR_USER, record_audit
from app.middleware.dual_auth import require_admin_session
from app.repositories.licenses import LicenseRepository
from app.state import AppState, get_state

router = APIRouter()


class DeleteLicenseResponse(BaseModel):
    license_id: str
    cascaded: dict


@router.delete("/{license_id}", response_model=DeleteLicenseResponse)
async def hard_delete_license(
    license_id: str,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> DeleteLicenseResponse:
    if state.license_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="license backend not configured",
        )
    repo: LicenseRepository = state.license_repository  # type: ignore[assignment]
    result = await repo.hard_delete(license_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="license not found")

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_LICENSE_DELETED,
        target_type="license",
        target_id=license_id,
        payload=result,
    )
    return DeleteLicenseResponse(license_id=license_id, cascaded=result)
