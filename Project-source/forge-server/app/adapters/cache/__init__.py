"""Cache 适配层 — 用到 Cache 分类则该分类下全部 provider 必须实现（当前仅 Redis）。"""
from __future__ import annotations

from app.adapters.cache.interface.protocol import Cache


def get_cache(*, db: int = 0) -> Cache:
    """根据 settings.cache_type 返回激活的适配器实例。

    Args:
        db: Redis db 编号（与 .agent.md 内 db 切分约定一致）
            - 0: app 缓存
            - 1: session
            - 2: celery broker
            - 3: celery result
    """
    from app.settings import get_settings

    settings = get_settings()
    match settings.cache_type:
        case "redis":
            from app.adapters.cache.redis.adapter import RedisCache
            return RedisCache.from_settings(settings, db=db)
        case _ as t:
            raise ValueError(f"Unsupported cache type: {t}")


__all__ = ["Cache", "get_cache"]
