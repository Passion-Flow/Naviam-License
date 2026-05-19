"""DbBackedRevocationStore —— 替换 InMemoryRevocationStore。

序号策略：每次 next_sequence() 查 revocation_entries 最大值 + 1。
（生产高并发场景可改为独立 sequences 表 + UPDATE...RETURNING；当前规模足够。）
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.adapters.database.interface.protocol import Database
from app.core.license.crl.format import RevocationEntry
from app.core.license.crl.manager import RevocationStore
from app.models.revocation import RevocationEntryModel


class DbBackedRevocationStore(RevocationStore):
    """SQLAlchemy 实现。"""

    def __init__(self, db: Database) -> None:
        self._db = db
        # 序号从 DB 现存最大值或 0 开始；用本地计数避免每次查 DB
        self._sequence_initialized = False
        self._sequence_counter = 0

    async def add(
        self,
        license_id: str,
        *,
        reason: str = "",
        revoked_by: str | None = None,
        now: datetime | None = None,
    ) -> None:
        ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        async with self._db.session() as sess:
            existing = await sess.get(RevocationEntryModel, license_id)
            if existing is None:
                sess.add(
                    RevocationEntryModel(
                        license_id=license_id,
                        reason=reason,
                        revoked_at=ts,
                        revoked_by_user_id=revoked_by,
                    )
                )
            else:
                existing.reason = reason
                existing.revoked_at = ts
                if revoked_by is not None:
                    existing.revoked_by_user_id = revoked_by

    async def remove(self, license_id: str) -> None:
        async with self._db.session() as sess:
            await sess.execute(delete(RevocationEntryModel).where(
                RevocationEntryModel.license_id == license_id,
            ))

    async def exists(self, license_id: str) -> bool:
        async with self._db.session() as sess:
            entry = await sess.get(RevocationEntryModel, license_id)
            return entry is not None

    async def list_entries(self) -> list[RevocationEntry]:
        async with self._db.session() as sess:
            stmt = select(RevocationEntryModel).order_by(RevocationEntryModel.license_id)
            result = await sess.execute(stmt)
            models = result.scalars().all()
        return [
            RevocationEntry(license_id=m.license_id, revoked_at=m.revoked_at, reason=m.reason or "")
            for m in models
        ]

    async def next_sequence(self) -> int:
        if not self._sequence_initialized:
            # 本进程首次：用当前条数作为起点（够强的单调），避免冷启回退
            async with self._db.session() as sess:
                count = await sess.scalar(select(func.count(RevocationEntryModel.license_id)))
                self._sequence_counter = int(count or 0)
            self._sequence_initialized = True
        self._sequence_counter += 1
        return self._sequence_counter
