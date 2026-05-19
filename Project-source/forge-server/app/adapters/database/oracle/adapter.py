"""Oracle 适配器（oracledb async driver）。

SQLAlchemy 2.0+ 通过 `oracle+oracledb_async` dialect 走 oracledb 异步接口。
连接串使用 `host:port/service_name` 形式（service_name = database 字段）。

镜像注意：oracledb 是 thin 模式（纯 Python）即可工作，不强求 Oracle Instant Client。
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.adapters.database._sqlalchemy_base import SqlAlchemyDatabase


class OracleDatabase(SqlAlchemyDatabase):
    provider_name = "oracle"

    def _build_url(self) -> str:
        return (
            f"oracle+oracledb_async://"
            f"{quote_plus(self._username)}:{quote_plus(self._password)}@"
            f"{self._host}:{self._port}/?service_name={self._database}"
        )
