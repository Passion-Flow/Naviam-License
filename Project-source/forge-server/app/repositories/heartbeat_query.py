"""HeartbeatQueryRepository —— admin 监控面板用的只读查询。

写路径走 DbBackedHeartbeatCollector；这里专门服务"看"的需求：
- 最近的心跳列表（过滤 license_id / 时间窗）
- 每个 license 的概览：last_seen / 不同指纹数 / 总心跳数
- 单 license 的详细心跳清单
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import desc, func, select

from app.adapters.database.interface.protocol import Database
from app.models.heartbeat import HeartbeatLogModel


@dataclass(frozen=True, slots=True)
class LicenseHeartbeatSummary:
    license_id: str
    total_count: int
    distinct_fingerprint_count: int
    last_seen_at: datetime
    last_fingerprint: str


class HeartbeatQueryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_recent(
        self,
        *,
        license_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[HeartbeatLogModel]:
        async with self._db.session() as sess:
            stmt = select(HeartbeatLogModel)
            if license_id is not None:
                stmt = stmt.where(HeartbeatLogModel.license_id == license_id)
            if since is not None:
                stmt = stmt.where(HeartbeatLogModel.received_at >= since)
            if until is not None:
                stmt = stmt.where(HeartbeatLogModel.received_at <= until)
            stmt = stmt.order_by(desc(HeartbeatLogModel.received_at)).limit(limit).offset(offset)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def summary_per_license(
        self,
        *,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[LicenseHeartbeatSummary]:
        """按 license 聚合：每个 license 总数、独立指纹数、最近 last_seen / fingerprint。"""
        async with self._db.session() as sess:
            base = select(
                HeartbeatLogModel.license_id,
                func.count(HeartbeatLogModel.id).label("total"),
                func.count(func.distinct(HeartbeatLogModel.fingerprint)).label("distinct_fp"),
                func.max(HeartbeatLogModel.received_at).label("last_seen"),
            ).group_by(HeartbeatLogModel.license_id)
            if since is not None:
                base = base.where(HeartbeatLogModel.received_at >= since)
            base = base.order_by(desc("last_seen")).limit(limit)
            rows = (await sess.execute(base)).all()

            # 二次查询：每个 license 的最后一条 fingerprint
            license_ids = [r.license_id for r in rows]
            last_fp_by_lic: dict[str, str] = {}
            if license_ids:
                # 子查询：每个 license 最大 received_at 对应的 fingerprint
                subq = (
                    select(
                        HeartbeatLogModel.license_id,
                        func.max(HeartbeatLogModel.received_at).label("max_rcv"),
                    )
                    .where(HeartbeatLogModel.license_id.in_(license_ids))
                    .group_by(HeartbeatLogModel.license_id)
                    .subquery()
                )
                stmt = (
                    select(HeartbeatLogModel.license_id, HeartbeatLogModel.fingerprint)
                    .join(
                        subq,
                        (HeartbeatLogModel.license_id == subq.c.license_id)
                        & (HeartbeatLogModel.received_at == subq.c.max_rcv),
                    )
                )
                for lic, fp in (await sess.execute(stmt)).all():
                    last_fp_by_lic.setdefault(lic, fp)

        return [
            LicenseHeartbeatSummary(
                license_id=r.license_id,
                total_count=int(r.total),
                distinct_fingerprint_count=int(r.distinct_fp),
                last_seen_at=r.last_seen,
                last_fingerprint=last_fp_by_lic.get(r.license_id, ""),
            )
            for r in rows
        ]

    async def fingerprints_seen(
        self,
        license_id: str,
        *,
        since: datetime | None = None,
    ) -> list[tuple[str, datetime]]:
        """返回 (fingerprint, 该指纹最早一次出现时间) 列表。"""
        async with self._db.session() as sess:
            stmt = select(
                HeartbeatLogModel.fingerprint,
                func.min(HeartbeatLogModel.received_at).label("first_seen"),
            ).where(HeartbeatLogModel.license_id == license_id)
            if since is not None:
                stmt = stmt.where(HeartbeatLogModel.received_at >= since)
            stmt = stmt.group_by(HeartbeatLogModel.fingerprint).order_by(desc("first_seen"))
            rows = (await sess.execute(stmt)).all()
        return [(r.fingerprint, r.first_seen) for r in rows]
