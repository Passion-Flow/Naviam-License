"""DbBackedHeartbeatCollector —— 替换 InMemoryHeartbeatCollector。

数据落 heartbeat_logs + heartbeat_nonces 两表；跨服务重启可持续工作。

nonce 防重放策略：
- mark_nonce_seen 写 heartbeat_nonces；冲突主键即视为重放
- is_nonce_seen 仅检查表中是否存在且 seen_at 在 TTL 内
- 后续应起定时任务清理 seen_at 老于 TTL 的行（建议 Celery 周期任务）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.adapters.database.interface.protocol import Database
from app.core.license.heartbeat.collector import HeartbeatCollector, HeartbeatRecord
from app.core.license.heartbeat.schema import NONCE_TTL_SECONDS
from app.models.heartbeat import HeartbeatLogModel, HeartbeatNonceModel


class DbBackedHeartbeatCollector(HeartbeatCollector):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(self, record: HeartbeatRecord) -> None:
        async with self._db.session() as sess:
            sess.add(HeartbeatLogModel(
                license_id=record.license_id,
                fingerprint=record.fingerprint,
                received_at=record.received_at,
                reported_at=record.reported_at,
                nonce=record.nonce,
                api_key_id=record.api_key_id,
                verifier_version=record.verifier_version,
            ))

    async def recent_fingerprints(
        self,
        license_id: str,
        *,
        window: timedelta,
        now: datetime | None = None,
    ) -> set[str]:
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = now_utc - window
        async with self._db.session() as sess:
            stmt = (
                select(HeartbeatLogModel.fingerprint)
                .where(HeartbeatLogModel.license_id == license_id)
                .where(HeartbeatLogModel.received_at >= cutoff)
                .distinct()
            )
            result = await sess.execute(stmt)
            return {row[0] for row in result.all()}

    async def is_nonce_seen(self, license_id: str, nonce: str) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=NONCE_TTL_SECONDS)
        async with self._db.session() as sess:
            stmt = (
                select(HeartbeatNonceModel.seen_at)
                .where(HeartbeatNonceModel.license_id == license_id)
                .where(HeartbeatNonceModel.nonce == nonce)
                .where(HeartbeatNonceModel.seen_at >= cutoff)
                .limit(1)
            )
            result = await sess.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def mark_nonce_seen(self, license_id: str, nonce: str) -> None:
        async with self._db.session() as sess:
            try:
                sess.add(HeartbeatNonceModel(license_id=license_id, nonce=nonce))
                await sess.flush()
            except IntegrityError:
                # 已存在（已被 mark）—— 静默忽略；is_nonce_seen 接下来会判定为重放
                await sess.rollback()

    async def list_logs_older_than(self, cutoff: datetime) -> Sequence[HeartbeatLogModel]:
        async with self._db.session() as sess:
            stmt = select(HeartbeatLogModel).where(HeartbeatLogModel.received_at < cutoff)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def delete_logs_older_than(self, cutoff: datetime) -> int:
        async with self._db.session() as sess:
            stmt = delete(HeartbeatLogModel).where(HeartbeatLogModel.received_at < cutoff)
            result = await sess.execute(stmt)
            return int(result.rowcount or 0)

    async def delete_expired_nonces(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=NONCE_TTL_SECONDS)
        async with self._db.session() as sess:
            stmt = delete(HeartbeatNonceModel).where(HeartbeatNonceModel.seen_at < cutoff)
            result = await sess.execute(stmt)
            return int(result.rowcount or 0)
