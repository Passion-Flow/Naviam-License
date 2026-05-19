"""Celery 任务跑 async 代码的胶水。

Celery worker 是同步多进程；我们的 repository 都是 async。每个任务函数：
1. 用 `asyncio.run(...)` 起一个独立事件循环
2. 内部用 `get_database()` 现造一份 Database 适配器（worker 内不共享 forge-api 的 AppState）
3. 跑完关连接 —— Celery 任务彼此独立
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def run_async(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """同步入口跑 async：`return run_async(lambda: do_thing())`。"""
    return asyncio.run(coro_factory())
