"""License ORM model —— 已签发 license 元数据 + .forge 文件存档。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LicenseModel(Base, TimestampMixin):
    __tablename__ = "licenses"

    license_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)

    mode: Mapped[str] = mapped_column(String(16), nullable=False)        # offline | hybrid | online
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    binding: Mapped[str] = mapped_column(String(16), nullable=False)     # none | soft | hard
    bound_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(64), nullable=False)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # .forge 文件原始字节（可选；只在需要重新下载时存）
    forge_file: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # payload SHA-256（防重复签发 / 审计追溯）
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # 备注
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_licenses_customer_id", "customer_id"),
        Index("ix_licenses_product_id", "product_id"),
        Index("ix_licenses_expires_at", "expires_at"),
    )
