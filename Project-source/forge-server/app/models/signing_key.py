"""SigningKey ORM model —— 签名密钥**元数据**。

私钥本体由 key_storage 后端（local_file / object_storage / kms）持有，
本表只存：算法 + 公钥 + 后端定位串 + 状态。

提供这层元数据的好处：
- 不依赖磁盘扫描即可在 admin UI 列出所有 key
- 状态机（active / rotated / revoked）持久化到 DB，跨实例一致
- 审计可关联到 user_id（谁创建的 key）
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SigningKeyModel(Base):
    __tablename__ = "signing_keys"

    key_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_locator: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_signing_keys_algorithm_status", "algorithm", "status"),
    )
