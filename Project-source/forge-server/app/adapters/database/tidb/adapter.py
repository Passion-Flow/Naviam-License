"""TiDB 适配器（MySQL 协议兼容，aiomysql driver）。

注意 TiDB 与原生 MySQL 在某些 DDL / 事务行为上有差异，migration 测试需独立验证：
- `AUTO_RANDOM` 与 MySQL 的 `AUTO_INCREMENT` 行为不同
- 缺少 `FOREIGN KEY` 强制（声明可保留，但不会强检）
- 长事务 / 大批量 DML 走 TiDB 自己的 conflict resolution
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.adapters.database._sqlalchemy_base import SqlAlchemyDatabase


class TidbDatabase(SqlAlchemyDatabase):
    provider_name = "tidb"

    def _build_url(self) -> str:
        # TiDB 兼容 MySQL 协议；driver 走 aiomysql
        return (
            f"mysql+aiomysql://"
            f"{quote_plus(self._username)}:{quote_plus(self._password)}@"
            f"{self._host}:{self._port}/{self._database}"
            f"?charset=utf8mb4"
        )
