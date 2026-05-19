"""GET /api/v1/keys —— 列出所有签名密钥（admin only）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.v1.keys._schema import KeyResponse
from app.middleware.dual_auth import require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class KeyListResponse(BaseModel):
    items: list[KeyResponse]


@router.get("", response_model=KeyListResponse)
async def list_keys(
    state: AppState = Depends(get_state),
    _: str = Depends(require_admin_session),
    algorithm: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> KeyListResponse:
    items: list[KeyResponse] = []
    for kid in await state.key_storage.list_ids():
        record = await state.key_storage.load(kid)
        if algorithm is not None and record.algorithm != algorithm:
            continue
        if status_filter is not None and record.status != status_filter:
            continue
        items.append(KeyResponse.from_record(record))
    # 按 created_at 倒序
    items.sort(key=lambda k: k.created_at, reverse=True)
    return KeyListResponse(items=items)
