"""POST /api/v1/keys/generate —— 新建签名密钥（admin only）。

调用方常见两种场景：
- 首次部署初始化某算法
- 平行启用一把新密钥，先不 activate，给将来的轮换做准备
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.v1.keys._schema import KeyResponse
from app.core.audit import ACTION_KEY_GENERATED, ACTOR_USER, record_audit
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.middleware.dual_auth import require_admin_session
from app.state import AppState, get_state

router = APIRouter()


class GenerateKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["ed25519", "rsa2048", "rsa4096", "sm2"]
    activate: bool = True


@router.post("/generate", response_model=KeyResponse, status_code=status.HTTP_201_CREATED)
async def generate_key(
    body: GenerateKeyBody,
    request: Request,
    state: AppState = Depends(get_state),
    actor_id: str = Depends(require_admin_session),
) -> KeyResponse:
    try:
        record = await generate_and_save_signing_key(
            state.key_storage,
            algorithm=body.algorithm,
            activate=body.activate,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    await record_audit(
        state,
        request,
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        action=ACTION_KEY_GENERATED,
        target_type="signing_key",
        target_id=record.key_id,
        payload={"algorithm": record.algorithm, "activate": body.activate},
    )
    return KeyResponse.from_record(record)
