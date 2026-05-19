"""心跳归档 —— 每天 00:30 UTC 把超期心跳冷转到 object_storage，再从主表删除。

策略：
- cutoff = now - heartbeat_retention_days
- 把 received_at < cutoff 的 heartbeat_logs 序列化为 JSONL 写到 bucket_audit 下
- 写入成功后从 DB 删除；写失败则不删（下次再试）
- 顺手清掉 heartbeat_nonces 里 seen_at 超 TTL 的行（防表无限增长）

object_storage bucket = settings.object_storage_bucket_audit；空则跳过上传只做删除
（私有化客户没开 object_storage_audit bucket 时退化为纯保留期清理）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog

from app.adapters.database import get_database
from app.adapters.object_storage import get_object_storage
from app.repositories.heartbeat import DbBackedHeartbeatCollector
from app.settings import get_settings
from app.workers.app import celery_app
from app.workers.tasks._runner import run_async

logger = structlog.get_logger("forge.workers.heartbeat_archive")


def _serialize(log) -> dict:
    return {
        "license_id": log.license_id,
        "fingerprint": log.fingerprint,
        "received_at": log.received_at.isoformat(),
        "reported_at": log.reported_at.isoformat() if log.reported_at else None,
        "nonce": log.nonce,
        "api_key_id": log.api_key_id,
        "verifier_version": log.verifier_version,
    }


async def _archive() -> dict[str, int]:
    settings = get_settings()
    if settings.heartbeat_retention_days <= 0:
        logger.info("heartbeat_archive.skipped", reason="retention_disabled")
        return {"archived": 0, "deleted_logs": 0, "deleted_nonces": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.heartbeat_retention_days)
    db = get_database()
    try:
        repo = DbBackedHeartbeatCollector(db)
        rows = await repo.list_logs_older_than(cutoff)
        archived = 0
        if rows and settings.object_storage_bucket_audit:
            storage = get_object_storage()
            try:
                await storage.connect()
                payload = "\n".join(json.dumps(_serialize(r)) for r in rows).encode("utf-8")
                key = f"heartbeats/{cutoff.strftime('%Y/%m/%d')}/before-{cutoff.isoformat()}.jsonl"
                await storage.put(
                    settings.object_storage_bucket_audit,
                    key,
                    payload,
                    content_type="application/x-ndjson",
                )
                archived = len(rows)
                logger.info(
                    "heartbeat_archive.uploaded",
                    bucket=settings.object_storage_bucket_audit,
                    key=key,
                    rows=archived,
                )
            finally:
                await storage.disconnect()

        deleted_logs = await repo.delete_logs_older_than(cutoff)
        deleted_nonces = await repo.delete_expired_nonces()
        logger.info(
            "heartbeat_archive.done",
            cutoff=cutoff.isoformat(),
            archived=archived,
            deleted_logs=deleted_logs,
            deleted_nonces=deleted_nonces,
        )
        return {"archived": archived, "deleted_logs": deleted_logs, "deleted_nonces": deleted_nonces}
    finally:
        await db.disconnect()


@celery_app.task(name="app.workers.tasks.heartbeat_archive.archive_old_heartbeats")
def archive_old_heartbeats() -> dict[str, int]:
    return run_async(_archive)
