"""Beat schedule 集中点 —— 显式注册而不是 autodiscover。

时机选择：
- 0 点 UTC = 客户大多在白天看 admin，凌晨跑批不抢资源
- 错峰：retention 0:00 / license 扫 0:15 / 心跳归档 0:30
"""
from __future__ import annotations

from celery.schedules import crontab


def beat_schedule() -> dict[str, dict]:
    return {
        "audit_retention_daily": {
            "task": "app.workers.tasks.audit_retention.purge_expired_audit_logs",
            "schedule": crontab(minute=0, hour=0),
        },
        "license_expiry_scan_daily": {
            "task": "app.workers.tasks.license_expiry_scan.scan_expiring_licenses",
            "schedule": crontab(minute=15, hour=0),
        },
        "heartbeat_archive_daily": {
            "task": "app.workers.tasks.heartbeat_archive.archive_old_heartbeats",
            "schedule": crontab(minute=30, hour=0),
        },
        "license_auto_renew_daily": {
            "task": "app.workers.tasks.license_auto_renew.scan_and_renew",
            "schedule": crontab(minute=45, hour=0),
        },
    }
