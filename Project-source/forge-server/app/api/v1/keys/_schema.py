"""签名密钥响应 Schema —— 私钥永远不返回。"""
from __future__ import annotations

import base64
from datetime import datetime

from pydantic import BaseModel

from app.core.key_storage.interface import KeyRecord


class KeyResponse(BaseModel):
    """密钥元数据 + 公钥（不含私钥）。"""

    key_id: str
    algorithm: str
    status: str
    created_at: datetime
    activated_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None
    public_key_b64: str

    @classmethod
    def from_record(cls, r: KeyRecord) -> "KeyResponse":
        return cls(
            key_id=r.key_id,
            algorithm=r.algorithm,
            status=r.status,
            created_at=r.created_at,
            activated_at=r.activated_at,
            rotated_at=r.rotated_at,
            revoked_at=r.revoked_at,
            public_key_b64=base64.b64encode(r.public_key).decode("ascii"),
        )
