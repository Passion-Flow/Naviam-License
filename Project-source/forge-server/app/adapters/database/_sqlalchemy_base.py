"""SQLAlchemy 2 async 共享基类 —— 4 个 Database provider 复用 connect/session/health 逻辑。

每个具体 provider 子类只需要实现 `_build_url(self) -> str`，其余继承。
这不违反"重复优于错误抽象"——它本质是 SQLAlchemy 已经提供的多 dialect 抽象的薄包装，
不是业务抽象，所以可以也应该共享。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.database.interface.protocol import Database
from app.settings import Settings


class SqlAlchemyDatabase(Database):
    """SQLAlchemy 2 async 适配器基类。子类提供 driver-specific URL。"""

    provider_name: str = "<override>"

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        pool_size: int,
        ssl_mode: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._pool_size = pool_size
        self._ssl_mode = ssl_mode
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def from_settings(cls, settings: Settings):
        return cls(
            host=settings.database_host,
            port=settings.database_port,
            username=settings.database_username,
            password=settings.database_password,
            database=settings.database_database,
            pool_size=settings.database_pool_size,
            ssl_mode=settings.database_ssl_mode,
        )

    @classmethod
    def from_engine(cls, engine: AsyncEngine):
        """测试用：直接注入已建好的 engine（如 SQLite in-memory）。"""
        instance = cls.__new__(cls)
        instance._host = ""
        instance._port = 0
        instance._username = ""
        instance._password = ""
        instance._database = ""
        instance._pool_size = 0
        instance._ssl_mode = ""
        instance._engine = engine
        instance._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return instance

    def _build_url(self) -> str:
        raise NotImplementedError

    async def connect(self) -> None:
        if self._engine is not None:
            return
        engine = create_async_engine(
            self._build_url(),
            pool_size=self._pool_size,
            pool_pre_ping=True,
        )
        self._engine = engine
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def disconnect(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def health_check(self) -> bool:
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception:
            return False

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._session_factory is None:
            await self.connect()
        assert self._session_factory is not None
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise
