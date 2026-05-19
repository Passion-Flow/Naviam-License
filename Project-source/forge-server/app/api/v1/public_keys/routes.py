"""GET /api/v1/public-keys/{key_id} — 公钥发布（不鉴权）。

Verifier 客户端可以拉公钥用于验签（offline 模式通常不拉，预先内置；hybrid/online 可拉）。
"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.key_storage import KeyStorageError
from app.state import AppState, get_state

router = APIRouter()


@router.get("/{key_id}")
async def get_public_key(
    key_id: str,
    state: AppState = Depends(get_state),
) -> dict[str, str]:
    try:
        public_key, algorithm = await state.key_storage.load_public(key_id)
    except KeyStorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="key not found") from exc
    return {
        "key_id": key_id,
        "algorithm": algorithm,
        "public_key_b64": base64.b64encode(public_key).decode("ascii"),
    }
