"""AuditLogRepository —— 审计事件读写。

只暴露：record（追加）/ list（按条件查询）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import delete, desc, select

from app.adapters.database.interface.protocol import Database
from app.models.audit import AuditLogModel


class AuditLogRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLogModel:
        entry = AuditLogModel(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload or {},
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        async with self._db.session() as sess:
            sess.add(entry)
        return entry

    async def list(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AuditLogModel]:
        async with self._db.session() as sess:
            stmt = select(AuditLogModel)
            if actor_id is not None:
                stmt = stmt.where(AuditLogModel.actor_id == actor_id)
            if action is not None:
                stmt = stmt.where(AuditLogModel.action == action)
            if target_type is not None:
                stmt = stmt.where(AuditLogModel.target_type == target_type)
            if target_id is not None:
                stmt = stmt.where(AuditLogModel.target_id == target_id)
            if since is not None:
                stmt = stmt.where(AuditLogModel.occurred_at >= since)
            if until is not None:
                stmt = stmt.where(AuditLogModel.occurred_at <= until)
            stmt = stmt.order_by(desc(AuditLogModel.occurred_at)).limit(limit).offset(offset)
            result = await sess.execute(stmt)
            return result.scalars().all()

    async def purge_older_than(self, cutoff: datetime) -> int:
        """删除 occurred_at < cutoff 的记录。返回删除条数。

        合规策略：调用方决定 cutoff（如 now - retention_days），本方法只做无脑删除。
        """
        async with self._db.session() as sess:
            stmt = delete(AuditLogModel).where(AuditLogModel.occurred_at < cutoff)
            result = await sess.execute(stmt)
            return int(result.rowcount or 0)
