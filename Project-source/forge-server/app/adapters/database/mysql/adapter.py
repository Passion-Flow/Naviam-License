"""MySQL 适配器（aiomysql driver）。

字符集统一 utf8mb4；私有化客户场景常用。
SSL 通过 connect_args（待 settings.database_ssl_ca / cert 字段补全后启用）。
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.adapters.database._sqlalchemy_base import SqlAlchemyDatabase


class MysqlDatabase(SqlAlchemyDatabase):
    provider_name = "mysql"

    def _build_url(self) -> str:
        return (
            f"mysql+aiomysql://"
            f"{quote_plus(self._username)}:{quote_plus(self._password)}@"
            f"{self._host}:{self._port}/{self._database}"
            f"?charset=utf8mb4"
        )
