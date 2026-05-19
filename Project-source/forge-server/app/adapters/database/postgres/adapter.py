"""Postgres 适配器（asyncpg driver）。"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.adapters.database._sqlalchemy_base import SqlAlchemyDatabase


class PostgresDatabase(SqlAlchemyDatabase):
    provider_name = "postgres"

    def _build_url(self) -> str:
        # asyncpg 不直接读 sslmode 参数；客户需 SSL 时通过 connect_args 注入 ssl context（后续扩展）
        return (
            f"postgresql+asyncpg://"
            f"{quote_plus(self._username)}:{quote_plus(self._password)}@"
            f"{self._host}:{self._port}/{self._database}"
        )
