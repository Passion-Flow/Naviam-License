"""Database 适配器统一接口。

业务代码 / ORM session factory 都通过本 Protocol 与底层数据库交互。
4 个 provider（postgres / mysql / oracle / tidb）必须**全部**实现此接口。
"""
from __future__ import annotations

from typing import Any, AsyncContextManager, Protocol


class DatabaseQueryResult(Protocol):
    """统一查询结果接口（行集合 + 元信息）。具体 driver 自行包装。"""

    @property
    def rows(self) -> list[dict[str, Any]]: ...

    @property
    def rowcount(self) -> int: ...


class Database(Protocol):
    """Database 适配器统一接口。

    设计原则：
    - 业务代码不直接拿 driver 连接；通过 `session()` 上下文获取
    - 不暴露 driver 原生异常（在适配器层封装成项目自定义异常）
    - 不暴露 SQL 方言差异（SQL 由 ORM / migration 处理；本层只走 ORM session）
    """

    # 生命周期
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health_check(self) -> bool: ...

    # ORM session（业务层主要入口）
    def session(self) -> AsyncContextManager[Any]: ...

    # 元信息
    @property
    def provider_name(self) -> str:
        """返回 'postgres' / 'mysql' / 'oracle' / 'tidb'。"""
        ...
