"""LicenseRepository —— 签发记录持久化。"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select

from app.adapters.database.interface.protocol import Database
from app.core.license.issuer.issue import IssuedLicense
from app.models.license import LicenseModel


class LicenseRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_issued(self, issued: IssuedLicense, *, store_forge_file: bool = True) -> None:
        payload_hash = hashlib.sha256(issued.payload.canonical_bytes()).hexdigest()
        model = LicenseModel(
            license_id=issued.license_id,
            customer_id=issued.payload.customer_id,
            product_id=issued.payload.product_id,
            mode=issued.payload.mode,
            scope=issued.payload.scope,
            binding=issued.payload.binding,
            bound_fingerprint=issued.payload.bound_fingerprint,
            algorithm=issued.metadata.algorithm,
            signing_key_id=issued.metadata.key_id,
            issued_at=issued.payload.issued_at,
            expires_at=issued.payload.expires_at,
            features=dict(issued.payload.features),
            limits=dict(issued.payload.limits),
            forge_file=issued.forge_file if store_forge_file else None,
            payload_hash=payload_hash,
        )
        async with self._db.session() as sess:
            sess.add(model)

    async def get(self, license_id: str) -> LicenseModel | None:
        async with self._db.session() as sess:
            return await sess.get(LicenseModel, license_id)

    async def list_for_customer(self, customer_id: str) -> Sequence[LicenseModel]:
        async with self._db.session() as sess:
            stmt = select(LicenseModel).where(LicenseModel.customer_id == customer_id)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def list(
        self,
        *,
        customer_id: str | None = None,
        product_id: str | None = None,
        mode: str | None = None,
        algorithm: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LicenseModel]:
        async with self._db.session() as sess:
            stmt = select(LicenseModel)
            if customer_id is not None:
                stmt = stmt.where(LicenseModel.customer_id == customer_id)
            if product_id is not None:
                stmt = stmt.where(LicenseModel.product_id == product_id)
            if mode is not None:
                stmt = stmt.where(LicenseModel.mode == mode)
            if algorithm is not None:
                stmt = stmt.where(LicenseModel.algorithm == algorithm)
            if q:
                # license_id 前缀匹配；用 LIKE 而非全文，与 SQLite/PG/MySQL 都兼容
                pattern = f"%{q}%"
                stmt = stmt.where(LicenseModel.license_id.ilike(pattern))
            stmt = stmt.order_by(LicenseModel.issued_at.desc()).limit(limit).offset(offset)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def get_forge_file(self, license_id: str) -> bytes | None:
        async with self._db.session() as sess:
            stmt = select(LicenseModel.forge_file).where(LicenseModel.license_id == license_id)
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def list_expiring_between(
        self, *, after: datetime, before: datetime
    ) -> Sequence[LicenseModel]:
        """List licenses with expires_at in (after, before]. 用于到期前预警扫描。"""
        async with self._db.session() as sess:
            stmt = (
                select(LicenseModel)
                .where(LicenseModel.expires_at > after)
                .where(LicenseModel.expires_at <= before)
                .order_by(LicenseModel.expires_at.asc())
            )
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def hard_delete(self, license_id: str) -> dict[str, int] | None:
        """硬删除 —— 真删 license + 级联删除心跳 / nonce / revocation。"""
        from sqlalchemy import delete

        from app.models.heartbeat import HeartbeatLogModel, HeartbeatNonceModel
        from app.models.revocation import RevocationEntryModel

        async with self._db.session() as sess:
            model = await sess.get(LicenseModel, license_id)
            if model is None:
                return None
            cascaded = {"license": 0, "heartbeat_log": 0, "heartbeat_nonce": 0, "revocation": 0}
            cascaded["heartbeat_log"] = (await sess.execute(
                delete(HeartbeatLogModel).where(HeartbeatLogModel.license_id == license_id)
            )).rowcount or 0
            cascaded["heartbeat_nonce"] = (await sess.execute(
                delete(HeartbeatNonceModel).where(HeartbeatNonceModel.license_id == license_id)
            )).rowcount or 0
            cascaded["revocation"] = (await sess.execute(
                delete(RevocationEntryModel).where(RevocationEntryModel.license_id == license_id)
            )).rowcount or 0
            await sess.delete(model)
            cascaded["license"] = 1
        return cascaded
