"""Database 适配层 — 用到 Database 分类则 4 provider 必须全部实现（HARD RULE）。

业务代码只 import `Database` Protocol 与 `get_database()` 工厂，**不**直接 import 具体 provider。
具体 provider 由启动期根据 `settings.database_type` 决定激活。
"""
from __future__ import annotations

from app.adapters.database.interface.protocol import Database, DatabaseQueryResult


def get_database() -> Database:
    """根据 settings.database_type 返回激活的适配器实例。"""
    from app.settings import get_settings

    settings = get_settings()
    match settings.database_type:
        case "postgres":
            from app.adapters.database.postgres.adapter import PostgresDatabase
            return PostgresDatabase.from_settings(settings)
        case "mysql":
            from app.adapters.database.mysql.adapter import MysqlDatabase
            return MysqlDatabase.from_settings(settings)
        case "oracle":
            from app.adapters.database.oracle.adapter import OracleDatabase
            return OracleDatabase.from_settings(settings)
        case "tidb":
            from app.adapters.database.tidb.adapter import TidbDatabase
            return TidbDatabase.from_settings(settings)
        case _ as t:
            raise ValueError(f"Unsupported database type: {t}")


__all__ = ["Database", "DatabaseQueryResult", "get_database"]
