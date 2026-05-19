"""GET /api/v1/keys/{key_id}/export-public —— admin 视角导出公钥。

与公开端点 /api/v1/public-keys/{key_id}（verifier 客户端用，无鉴权）的区别：
- 公开端点：只返回 (algorithm, public_key)，给 verifier SDK 用
- admin 端点：含完整 metadata（status / created_at / activated_at / rotated_at / revoked_at），
  便于 admin 在 UI 上展示密钥生命周期 + 复制公钥
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.keys._schema import KeyResponse
from app.core.key_storage import KeyStorageError
from app.middleware.dual_auth import require_admin_session
from app.state import AppState, get_state

router = APIRouter()


@router.get("/{key_id}/export-public", response_model=KeyResponse)
async def export_public(
    key_id: str,
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
) -> KeyResponse:
    try:
        record = await state.key_storage.load(key_id)
    except KeyStorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found") from exc
    return KeyResponse.from_record(record)
