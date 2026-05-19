"""Alembic env.py — 运行时从 Pydantic Settings 取连接信息。

绝不写死 DATABASE_URL；从 app.settings 注入。
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _build_url() -> str:
    """根据 settings.database_type 构造 SQLAlchemy URL。

    password 必须 URL-encode —— `Postgres@!QAZxsw2.` 这种凭证里的 `@` 会被解析成
    user/host 分隔符，必须转义。
    """
    s = get_settings()
    creds = (
        f"{quote_plus(s.database_username)}:{quote_plus(s.database_password)}"
        f"@{s.database_host}:{s.database_port}/{s.database_database}"
    )
    match s.database_type:
        case "postgres":
            return f"postgresql+asyncpg://{creds}"
        case "mysql":
            return f"mysql+aiomysql://{creds}"
        case "oracle":
            return f"oracle+oracledb_async://{creds}"
        case "tidb":
            return f"mysql+aiomysql://{creds}"  # TiDB 走 MySQL 协议
        case _ as t:
            raise ValueError(f"Unsupported database type for migrations: {t}")


target_metadata = None  # TODO: 待 app/models/* 完成后 import 进来聚合 Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_build_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _build_url()
    connectable = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
