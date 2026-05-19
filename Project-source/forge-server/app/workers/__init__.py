"""Celery 入口 —— `celery -A app.workers worker` / `... beat` 都指向本模块。

约束：
- Broker / result backend 走 Redis；db 索引复用 settings.cache_db_celery_*
- 任务发现走 `include`（显式列出），不自动 autodiscover —— 防止误 import 副作用
- 私有化部署里 worker / scheduler 必须能独立启动（不依赖 forge-api 进程）
"""
from __future__ import annotations

from app.workers.app import celery_app

__all__ = ["celery_app"]
