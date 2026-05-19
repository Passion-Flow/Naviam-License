"""License 到期预警 —— 每天 00:15 UTC 扫一遍 (now, now+N) 区间的 license。

行为：
- 命中即写一条 audit_log `license.expiry_warning`（带 days_remaining + customer_id）
- 实际外发（邮件 / webhook）由客户在 audit 上做 sink；本任务只负责扫和记录
- 幂等：同一 license 在窗口里每日都会写一条 audit，admin UI 用最新一条做角标
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.adapters.database import get_database
from app.repositories.audit import AuditLogRepository
from app.repositories.licenses import LicenseRepository
from app.settings import get_settings
from app.workers.app import celery_app
from app.workers.tasks._runner import run_async

logger = structlog.get_logger("forge.workers.license_expiry_scan")

ACTION_LICENSE_EXPIRY_WARNING = "license.expiry_warning"
ACTOR_SYSTEM = "system"


async def _scan() -> int:
    settings = get_settings()
    if settings.license_expiry_warn_days <= 0:
        logger.info("license_expiry_scan.skipped", reason="warn_days_zero")
        return 0
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=settings.license_expiry_warn_days)
    db = get_database()
    try:
        licenses_repo = LicenseRepository(db)
        audit_repo = AuditLogRepository(db)
        rows = await licenses_repo.list_expiring_between(after=now, before=horizon)
        from app.core.webhooks import emit_event
        for row in rows:
            days_remaining = max(0, (row.expires_at - now).days)
            event_payload = {
                "customer_id": row.customer_id,
                "product_id": row.product_id,
                "expires_at": row.expires_at.isoformat(),
                "days_remaining": days_remaining,
            }
            await audit_repo.record(
                actor_type=ACTOR_SYSTEM,
                actor_id="scheduler",
                action=ACTION_LICENSE_EXPIRY_WARNING,
                target_type="license",
                target_id=row.license_id,
                payload=event_payload,
            )
            await emit_event(
                "license.expiring",
                {"license_id": row.license_id, **event_payload},
            )
        logger.info(
            "license_expiry_scan.done",
            horizon_days=settings.license_expiry_warn_days,
            warned=len(rows),
        )
        return len(rows)
    finally:
        await db.disconnect()


@celery_app.task(name="app.workers.tasks.license_expiry_scan.scan_expiring_licenses")
def scan_expiring_licenses() -> int:
    return run_async(_scan)
