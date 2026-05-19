"""Heartbeat 持久化模型。

两张表：
- heartbeat_logs：每条心跳的详细记录（用于审计 + 多环境检测）
- heartbeat_nonces：短期 nonce 去重（防重放）

为什么 nonce 也走 DB：
- 没 Redis 时仍能用（私有化客户极简部署场景）
- 有 Redis 时，业务层应优先用 RedisCache.exists() 做去重，DB 表作为审计冷归档
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class HeartbeatLogModel(Base):
    __tablename__ = "heartbeat_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    license_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_heartbeat_logs_license_received", "license_id", "received_at"),
    )


class HeartbeatNonceModel(Base):
    """短 TTL nonce 去重表。"""

    __tablename__ = "heartbeat_nonces"

    license_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_heartbeat_nonces_seen_at", "seen_at"),
    )
