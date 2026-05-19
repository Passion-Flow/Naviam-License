"""ApiKey ORM model —— Verifier 用 API Key（只存哈希）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApiKeyModel(Base, TimestampMixin):
    __tablename__ = "api_keys"

    # 内部 ID（snowflake 风格的 short uuid）
    key_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # 明文 sha256，不存明文 api key
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # 明文前缀（前 8 字符），便于 admin 在 UI 里识别"是哪把 key"
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_label: Mapped[str] = mapped_column(String(128), nullable=False)

    # active | revoked
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # NULL = 永不过期（保留向后兼容）。非 NULL 时由鉴权层在每次校验时比对当前时间。
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_api_keys_customer_id", "customer_id"),
        Index("ix_api_keys_status", "status"),
    )
