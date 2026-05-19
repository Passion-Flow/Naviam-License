"""Celery app 构造 —— 单进程单 app 实例。

无硬编码：所有连接信息从 settings 取（同 forge-api）。
"""
from __future__ import annotations

from urllib.parse import quote_plus

from celery import Celery

from app.settings import get_settings


def _redis_url(*, db_index: int) -> str:
    """组装 redis:// URL —— 不写 broker / result 任何字段进 settings 里。"""
    s = get_settings()
    auth = ""
    if s.cache_password:
        # 用户名可选；Redis 6+ 支持 ACL 用户名
        user = quote_plus(s.cache_username) if s.cache_username else ""
        pwd = quote_plus(s.cache_password)
        auth = f"{user}:{pwd}@" if user else f":{pwd}@"
    return f"redis://{auth}{s.cache_host}:{s.cache_port}/{db_index}"


def build_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "forge",
        broker=_redis_url(db_index=settings.cache_db_celery_broker),
        backend=_redis_url(db_index=settings.cache_db_celery_result),
        include=[
            "app.workers.tasks.audit_retention",
            "app.workers.tasks.license_expiry_scan",
            "app.workers.tasks.heartbeat_archive",
            "app.workers.tasks.license_auto_renew",
        ],
    )
    # Beat 调度由 app.workers.scheduler.schedule 负责
    from app.workers.scheduler.schedule import beat_schedule

    app.conf.update(
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        result_expires=3600,
        beat_schedule=beat_schedule(),
    )
    return app


celery_app = build_celery_app()
