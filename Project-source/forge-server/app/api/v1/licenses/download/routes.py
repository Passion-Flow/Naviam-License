"""GET /api/v1/licenses/{license_id}/download —— 下载 .forge 文件。

鉴权：Admin Session / API Key 双鉴权（与 issue 一致；客户运维需要拉本项目的 license）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.middleware.dual_auth import require_admin_or_api_key
from app.repositories.licenses import LicenseRepository
from app.state import AppState, get_state

router = APIRouter()


@router.get("/{license_id}/download")
async def download_license(
    license_id: str,
    state: AppState = Depends(get_state),
    _actor: str = Depends(require_admin_or_api_key),
) -> Response:
    if state.license_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="license backend not configured",
        )
    repo: LicenseRepository = state.license_repository  # type: ignore[assignment]

    data = await repo.get_forge_file(license_id)
    if data is None:
        # 区分"license 不存在" vs "license 存在但 forge_file 未存档"
        if await repo.get(license_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="license not found")
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="forge file not archived for this license",
        )

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{license_id}.forge"',
            "Cache-Control": "no-store",
        },
    )
