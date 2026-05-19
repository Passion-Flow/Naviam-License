"""Heartbeat 响应 Schema —— admin only。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.heartbeat import HeartbeatLogModel
from app.repositories.heartbeat_query import LicenseHeartbeatSummary


class HeartbeatEntry(BaseModel):
    id: int
    license_id: str
    fingerprint: str
    received_at: datetime
    reported_at: datetime
    nonce: str
    api_key_id: str | None
    verifier_version: str

    @classmethod
    def from_model(cls, m: HeartbeatLogModel) -> "HeartbeatEntry":
        return cls(
            id=m.id,
            license_id=m.license_id,
            fingerprint=m.fingerprint,
            received_at=m.received_at,
            reported_at=m.reported_at,
            nonce=m.nonce,
            api_key_id=m.api_key_id,
            verifier_version=m.verifier_version,
        )


class HeartbeatSummaryEntry(BaseModel):
    license_id: str
    total_count: int
    distinct_fingerprint_count: int
    last_seen_at: datetime
    last_fingerprint: str

    @classmethod
    def from_dataclass(cls, s: LicenseHeartbeatSummary) -> "HeartbeatSummaryEntry":
        return cls(
            license_id=s.license_id,
            total_count=s.total_count,
            distinct_fingerprint_count=s.distinct_fingerprint_count,
            last_seen_at=s.last_seen_at,
            last_fingerprint=s.last_fingerprint,
        )
