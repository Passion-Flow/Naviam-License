"""4 个 Database provider 真实现 —— URL 生成 + factory 路由 + 共享基类继承。

注意：本测试**不连真 DB**（mysql/oracle/tidb 没有现成的轻量 in-memory backend）。
仅验证：
- 各 provider 都实现了 SqlAlchemyDatabase 基类
- _build_url() 输出正确（driver scheme + 凭证 URL-quote + 端口）
- factory `get_database()` 按 settings.database_type 正确路由
- from_settings 能装配
"""
from __future__ import annotations

import os

import pytest

from app.adapters.database import get_database
from app.adapters.database._sqlalchemy_base import SqlAlchemyDatabase
from app.adapters.database.mysql.adapter import MysqlDatabase
from app.adapters.database.oracle.adapter import OracleDatabase
from app.adapters.database.postgres.adapter import PostgresDatabase
from app.adapters.database.tidb.adapter import TidbDatabase


PROVIDER_CLASSES = {
    "postgres": PostgresDatabase,
    "mysql": MysqlDatabase,
    "oracle": OracleDatabase,
    "tidb": TidbDatabase,
}


@pytest.mark.parametrize("provider_name,cls", list(PROVIDER_CLASSES.items()))
def test_all_providers_inherit_shared_base(provider_name: str, cls: type) -> None:
    assert issubclass(cls, SqlAlchemyDatabase)
    assert cls.provider_name == provider_name


@pytest.mark.parametrize("provider_name,cls", list(PROVIDER_CLASSES.items()))
def test_each_provider_builds_url(provider_name: str, cls: type[SqlAlchemyDatabase]) -> None:
    db = cls(
        host="db.example.com",
        port=5432,
        username="forge_app",
        password="Postgres@!QAZxsw2.",  # 含 @ ! 等需 URL-quote 的字符
        database="forge_main",
        pool_size=5,
        ssl_mode="disable",
    )
    url = db._build_url()
    assert "db.example.com" in url
    assert "5432" in url
    assert "forge_main" in url
    # 密码里的 @ 必须被 URL-quote 否则解析失败
    assert "%40" in url
    assert "!" in url or "%21" in url


def test_postgres_url_uses_asyncpg() -> None:
    db = PostgresDatabase(
        host="h", port=5432, username="u", password="p",
        database="d", pool_size=5, ssl_mode="disable",
    )
    assert db._build_url().startswith("postgresql+asyncpg://")


def test_mysql_url_uses_aiomysql() -> None:
    db = MysqlDatabase(
        host="h", port=3306, username="u", password="p",
        database="d", pool_size=5, ssl_mode="disable",
    )
    url = db._build_url()
    assert url.startswith("mysql+aiomysql://")
    assert "charset=utf8mb4" in url


def test_oracle_url_uses_oracledb_async_with_service_name() -> None:
    db = OracleDatabase(
        host="h", port=1521, username="u", password="p",
        database="FORGEPDB1", pool_size=5, ssl_mode="disable",
    )
    url = db._build_url()
    assert url.startswith("oracle+oracledb_async://")
    assert "service_name=FORGEPDB1" in url


def test_tidb_url_uses_aiomysql_protocol() -> None:
    db = TidbDatabase(
        host="h", port=4000, username="u", password="p",
        database="d", pool_size=5, ssl_mode="disable",
    )
    url = db._build_url()
    # TiDB 走 MySQL 协议，driver = aiomysql
    assert url.startswith("mysql+aiomysql://")


@pytest.mark.parametrize("db_type", ["postgres", "mysql", "oracle", "tidb"])
def test_factory_routes_by_settings(db_type: str, tmp_path) -> None:
    """get_database() 根据 DATABASE_TYPE env 路由到对应 class。"""
    env = {
        "DATABASE_TYPE": db_type,
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DATABASE_USERNAME": "u",
        "DATABASE_PASSWORD": "p",
        "DATABASE_DATABASE": "d",
        "CACHE_HOST": "localhost", "CACHE_PORT": "6379", "CACHE_PASSWORD": "p",
        "KEY_STORAGE_BACKEND": "local_file",
        "KEY_STORAGE_LOCAL_PATH": str(tmp_path),
        "KEY_MASTER_PASSPHRASE": "x",
        "AUTH_SESSION_SECRET": "x",
        "OBJECT_STORAGE_TYPE": "local",
    }
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    # 清掉 settings 缓存
    from app.settings import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        db = get_database()
        assert isinstance(db, PROVIDER_CLASSES[db_type])
        assert db.provider_name == db_type
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()  # type: ignore[attr-defined]


def test_all_providers_share_session_lifecycle_methods() -> None:
    """共享基类保证 4 provider 都有 connect/disconnect/health_check/session。"""
    for cls in PROVIDER_CLASSES.values():
        for attr in ("connect", "disconnect", "health_check", "session", "from_settings", "from_engine"):
            assert hasattr(cls, attr), f"{cls.__name__} missing {attr}"
