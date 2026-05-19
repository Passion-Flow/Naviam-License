"""审计日志保留 —— 每天 00:00 UTC 清理超期记录。

合规策略：
- settings.audit_retention_days = 0 表示永不清理（部分合规要求"永久保留"）
- cutoff = now - retention_days；occurred_at < cutoff 的记录被删除
- 删除条数写回任务返回值，便于 Flower / 监控
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.adapters.database import get_database
from app.repositories.audit import AuditLogRepository
from app.settings import get_settings
from app.workers.app import celery_app
from app.workers.tasks._runner import run_async

logger = structlog.get_logger("forge.workers.audit_retention")


async def _purge() -> int:
    settings = get_settings()
    if settings.audit_retention_days == 0:
        logger.info("audit_retention.skipped", reason="retention_disabled")
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days)
    db = get_database()
    try:
        repo = AuditLogRepository(db)
        deleted = await repo.purge_older_than(cutoff)
        logger.info(
            "audit_retention.purged",
            cutoff=cutoff.isoformat(),
            retention_days=settings.audit_retention_days,
            deleted=deleted,
        )
        return deleted
    finally:
        await db.disconnect()


@celery_app.task(name="app.workers.tasks.audit_retention.purge_expired_audit_logs")
def purge_expired_audit_logs() -> int:
    return run_async(_purge)
