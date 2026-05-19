"""License 自动续期 —— 每天 00:45 UTC 扫一遍。

入选条件：
- `features._auto_renew.enabled == True`
- `expires_at` 在 (now, now + `_auto_renew.window_days`] 内
- 未被吊销

对每条入选 license：
1. 再签发一份新的 license（mode/scope/binding/algorithm/features/limits 全部复用；
   `expires_at = now + (老 license 的有效期长度)`）。新 license_id 由 LA 生成。
2. 写一条 audit `license.auto_renewed` 关联老 license_id → 新 license_id。
3. 推 webhook 业务事件，方便客户的下游系统更新缓存 / 通知用户。

为什么不修改原 license 的 expires_at：
- License 是不可变签名物；改字段等于让旧签名失效，下游 verifier 不会重新拉 license 文件
- 行业惯例（AWS / GCP / DigiCert）也是发新 cert/license，旧的自然到期失效
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.adapters.database import get_database
from app.core.key_storage import get_key_storage
from app.core.license.issuer.issue import IssueLicenseRequest
from app.core.license.issuer.issue_with_storage import issue_license_with_storage
from app.repositories.audit import AuditLogRepository
from app.repositories.licenses import LicenseRepository
from app.workers.app import celery_app
from app.workers.tasks._runner import run_async

logger = structlog.get_logger("forge.workers.license_auto_renew")

ACTION_LICENSE_AUTO_RENEWED = "license.auto_renewed"
ACTOR_SYSTEM = "system"


def _auto_renew_config(features: dict) -> tuple[bool, int]:
    """从 features._auto_renew 提取 (enabled, window_days)。"""
    cfg = features.get("_auto_renew") if isinstance(features, dict) else None
    if not isinstance(cfg, dict):
        return False, 0
    enabled = bool(cfg.get("enabled"))
    window = int(cfg.get("window_days") or 7)
    return enabled, max(1, window)


async def _scan_and_renew() -> dict[str, int]:
    db = get_database()
    try:
        licenses = LicenseRepository(db)
        audit = AuditLogRepository(db)
        now = datetime.now(timezone.utc)

        # 拉出未来 30 天内到期的 license 集合（超过 30 天的 _auto_renew window 不合理，跳过）
        horizon = now + timedelta(days=30)
        rows = await licenses.list_expiring_between(after=now, before=horizon)
        renewed = 0
        skipped = 0

        from app.core.webhooks import emit_event

        for row in rows:
            enabled, window_days = _auto_renew_config(row.features or {})
            if not enabled:
                skipped += 1
                continue
            cutoff = now + timedelta(days=window_days)
            if row.expires_at > cutoff:
                skipped += 1  # 还没到 renew 窗口
                continue

            # 再签发：保持业务参数；新 expires_at = now + 老 license 的原始有效期长度
            lifetime = row.expires_at - row.issued_at
            new_expires = now + lifetime
            request = IssueLicenseRequest(
                customer_id=row.customer_id,
                product_id=row.product_id,
                mode=row.mode,  # type: ignore[arg-type]
                scope=row.scope,  # type: ignore[arg-type]
                algorithm=row.algorithm,  # type: ignore[arg-type]
                binding=row.binding,  # type: ignore[arg-type]
                bound_fingerprint=row.bound_fingerprint,
                expires_at=new_expires,
                features=dict(row.features or {}),
                limits=dict(row.limits or {}),
            )
            try:
                issued = await issue_license_with_storage(
                    storage=get_key_storage(),
                    req=request,
                )
                await licenses.add_issued(issued)
                await audit.record(
                    actor_type=ACTOR_SYSTEM,
                    actor_id="scheduler",
                    action=ACTION_LICENSE_AUTO_RENEWED,
                    target_type="license",
                    target_id=issued.license_id,
                    payload={
                        "previous_license_id": row.license_id,
                        "customer_id": row.customer_id,
                        "product_id": row.product_id,
                        "expires_at": new_expires.isoformat(),
                        "lifetime_days": lifetime.days,
                    },
                )
                await emit_event(
                    "license.auto_renewed",
                    {
                        "license_id": issued.license_id,
                        "previous_license_id": row.license_id,
                        "customer_id": row.customer_id,
                        "expires_at": new_expires.isoformat(),
                    },
                )
                renewed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "license_auto_renew.failed",
                    license_id=row.license_id,
                    error=str(exc),
                )

        logger.info("license_auto_renew.done", renewed=renewed, skipped=skipped)
        return {"renewed": renewed, "skipped": skipped}
    finally:
        await db.disconnect()


@celery_app.task(name="app.workers.tasks.license_auto_renew.scan_and_renew")
def scan_and_renew() -> dict[str, int]:
    return run_async(_scan_and_renew)
