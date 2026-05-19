"""SigningKeyRepository —— 签名密钥元数据读写。

密钥本体在 `key_storage` 后端（local_file / object_storage / kms）；
本仓库只存表中的元数据：key_id / algorithm / public_key / storage_backend /
storage_locator / status + 时间戳。

为什么需要这层：
- admin UI 不依赖磁盘扫描即可列出 keys
- 状态机（active / rotated / revoked）跨实例一致
- 审计可关联 created_by_user_id
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update

from app.adapters.database.interface.protocol import Database
from app.models.signing_key import SigningKeyModel


class SigningKeyRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        *,
        key_id: str,
        algorithm: str,
        public_key: bytes,
        storage_backend: str,
        storage_locator: str,
        created_by_user_id: str | None = None,
        activate: bool = True,
    ) -> SigningKeyModel:
        now = datetime.now(timezone.utc)
        model = SigningKeyModel(
            key_id=key_id,
            algorithm=algorithm,
            public_key=public_key,
            storage_backend=storage_backend,
            storage_locator=storage_locator,
            status="active" if activate else "staged",
            created_at=now,
            activated_at=now if activate else None,
            created_by_user_id=created_by_user_id,
        )
        async with self._db.session() as sess:
            sess.add(model)
        return model

    async def get(self, key_id: str) -> SigningKeyModel | None:
        async with self._db.session() as sess:
            return await sess.get(SigningKeyModel, key_id)

    async def list(
        self,
        *,
        algorithm: str | None = None,
        status: str | None = None,
    ) -> Sequence[SigningKeyModel]:
        async with self._db.session() as sess:
            stmt = select(SigningKeyModel)
            if algorithm is not None:
                stmt = stmt.where(SigningKeyModel.algorithm == algorithm)
            if status is not None:
                stmt = stmt.where(SigningKeyModel.status == status)
            stmt = stmt.order_by(SigningKeyModel.created_at.desc())
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def find_active(self, algorithm: str) -> SigningKeyModel | None:
        """活跃 key（status=active 中创建最晚的一把）。"""
        async with self._db.session() as sess:
            stmt = (
                select(SigningKeyModel)
                .where(SigningKeyModel.algorithm == algorithm)
                .where(SigningKeyModel.status == "active")
                .order_by(SigningKeyModel.created_at.desc())
                .limit(1)
            )
            result = await sess.execute(stmt)
            return result.scalar_one_or_none()

    async def mark_rotated(self, key_id: str) -> None:
        await self._set_status(key_id, status="rotated", time_field="rotated_at")

    async def mark_revoked(self, key_id: str) -> None:
        await self._set_status(key_id, status="revoked", time_field="revoked_at")

    async def _set_status(self, key_id: str, *, status: str, time_field: str) -> None:
        async with self._db.session() as sess:
            stmt = (
                update(SigningKeyModel)
                .where(SigningKeyModel.key_id == key_id)
                .values({"status": status, time_field: datetime.now(timezone.utc)})
            )
            await sess.execute(stmt)

    async def hard_delete(self, key_id: str) -> dict[str, int] | None:
        """硬删除签名密钥 + 级联删除被该密钥签名的全部 license / 心跳 / 吊销条目。

        私钥材料存储在 key_storage 后端（本地文件/对象存储/KMS），调用方在路由层
        额外做 storage 层删除；本方法只负责 DB 行。
        """
        from sqlalchemy import delete

        from app.models.heartbeat import HeartbeatLogModel, HeartbeatNonceModel
        from app.models.license import LicenseModel
        from app.models.revocation import RevocationEntryModel

        async with self._db.session() as sess:
            model = await sess.get(SigningKeyModel, key_id)
            if model is None:
                return None
            license_ids = (
                await sess.execute(
                    select(LicenseModel.license_id).where(LicenseModel.signing_key_id == key_id)
                )
            ).scalars().all()
            cascaded = {"signing_key": 0, "license": 0,
                        "heartbeat_log": 0, "heartbeat_nonce": 0, "revocation": 0}
            if license_ids:
                cascaded["heartbeat_log"] = (await sess.execute(
                    delete(HeartbeatLogModel).where(HeartbeatLogModel.license_id.in_(license_ids))
                )).rowcount or 0
                cascaded["heartbeat_nonce"] = (await sess.execute(
                    delete(HeartbeatNonceModel).where(HeartbeatNonceModel.license_id.in_(license_ids))
                )).rowcount or 0
                cascaded["revocation"] = (await sess.execute(
                    delete(RevocationEntryModel).where(RevocationEntryModel.license_id.in_(license_ids))
                )).rowcount or 0
                cascaded["license"] = (await sess.execute(
                    delete(LicenseModel).where(LicenseModel.license_id.in_(license_ids))
                )).rowcount or 0
            await sess.delete(model)
            cascaded["signing_key"] = 1
        return cascaded
