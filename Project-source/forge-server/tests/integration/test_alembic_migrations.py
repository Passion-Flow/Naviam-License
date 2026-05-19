"""Alembic 9 个 migration 端到端：
从空 SQLite db 跑 upgrade → 表全部创建 → 跑 downgrade → 表全部清空。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


EXPECTED_TABLES = {
    "users",
    "customers",
    "products",
    "licenses",
    "signing_keys",
    "api_keys",
    "revocation_entries",
    "heartbeat_logs",
    "heartbeat_nonces",
    "audit_logs",
    "alembic_version",  # alembic 自带的元表
}


def _make_config(db_path: Path) -> Config:
    """构造 Alembic Config，指向项目 migrations 目录 + 临时 SQLite db。"""
    project_root = Path(__file__).resolve().parents[2]
    cfg = Config()
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    # 注意：env.py 默认从 settings 取 URL；这里直接给 sqlalchemy.url 简化测试
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_full_upgrade_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "forge.db"
    cfg = _make_config(db_path)

    # 不用 env.py（它依赖 app.settings）；直接 op 用配置 URL
    # 此测试需要绕过 env.py 的 settings 依赖，最稳妥是用 EnvContext
    # 简化：直接用 alembic.script + EnvironmentContext 跑 versions/*

    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(f"sqlite:///{db_path}")

    def upgrade(rev, context):
        return script._upgrade_revs("head", rev)

    with engine.begin() as connection:
        with EnvironmentContext(cfg, script, fn=upgrade, as_sql=False, destination_rev="head"):
            from alembic import context
            context.configure(connection=connection, target_metadata=None)
            context.run_migrations()

    # 验证
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables after upgrade: {missing}"


def test_each_migration_round_trip(tmp_path: Path) -> None:
    """run upgrade 到 head → run downgrade 到 base → 表应被清空。"""
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory

    db_path = tmp_path / "forge_rt.db"
    cfg = _make_config(db_path)
    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(f"sqlite:///{db_path}")

    def run(direction: str, dest: str) -> None:
        def fn(rev, _context):
            if direction == "up":
                return script._upgrade_revs(dest, rev)
            return script._downgrade_revs(dest, rev)

        with engine.begin() as connection:
            with EnvironmentContext(cfg, script, fn=fn, as_sql=False, destination_rev=dest):
                from alembic import context
                context.configure(connection=connection, target_metadata=None)
                context.run_migrations()

    # upgrade
    run("up", "head")
    inspector = inspect(engine)
    assert "licenses" in inspector.get_table_names()

    # downgrade 到 base
    run("down", "base")
    inspector = inspect(engine)
    remaining = set(inspector.get_table_names())
    # 只剩 alembic_version
    assert remaining <= {"alembic_version"}, f"leftover tables after downgrade: {remaining}"


def test_head_schema_matches_base_metadata(tmp_path: Path) -> None:
    """alembic head 的 schema 必须与 Base.metadata 一致（B2 守护）。

    场景：开发者改了 model 但忘加 alembic revision —— 测试就要红。
    手段：跑 head 到临时 DB，反射 schema 后逐表逐列与 Base.metadata diff。
    SQLite 反射只能可靠还原表名 + 列名，故只校验这两层（强信号、零误报）。
    """
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import MetaData

    from app.models import Base  # 触发所有 Model 注册

    db_path = tmp_path / "forge_consistency.db"
    cfg = _make_config(db_path)
    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(f"sqlite:///{db_path}")

    def upgrade(rev, _context):
        return script._upgrade_revs("head", rev)

    with engine.begin() as connection:
        with EnvironmentContext(cfg, script, fn=upgrade, as_sql=False, destination_rev="head"):
            from alembic import context
            context.configure(connection=connection, target_metadata=None)
            context.run_migrations()

    reflected = MetaData()
    reflected.reflect(bind=engine)
    reflected_tables = {t for t in reflected.tables if t != "alembic_version"}
    model_tables = set(Base.metadata.tables)

    only_in_migrations = reflected_tables - model_tables
    only_in_models = model_tables - reflected_tables
    assert not only_in_migrations, (
        f"tables in migrations but missing from models: {only_in_migrations}"
    )
    assert not only_in_models, (
        f"models defined but no migration creates them: {only_in_models} — "
        f"forgot to add an alembic revision?"
    )

    mismatches: list[str] = []
    for name in sorted(model_tables):
        migrated_cols = {c.name for c in reflected.tables[name].columns}
        model_cols = {c.name for c in Base.metadata.tables[name].columns}
        only_mig = migrated_cols - model_cols
        only_mod = model_cols - migrated_cols
        if only_mig or only_mod:
            mismatches.append(
                f"  {name}: only_in_migration={sorted(only_mig) or '∅'}  "
                f"only_in_model={sorted(only_mod) or '∅'}"
            )
    assert not mismatches, (
        "alembic head ↔ Base.metadata column drift detected:\n" + "\n".join(mismatches)
    )
