"""bootstrap_admin —— 首次部署创建默认超管账号（幂等）。

调用方式：
- 容器入口：`python -m app.cli.bootstrap_admin`
- compose one-shot：`forge-bootstrap` service 启动一次后退出
- Helm：作为 pre-install/pre-upgrade Job 跑

行为：
1. 用 `bootstrap_admin_username` 在 users 表查；找到则**返回 reused**，不改密
2. 找不到则按 (username / email / password / is_super=True) 创建，返回 created
3. 多次调用同样幂等（受 username 唯一索引保护）

退出码：0 表示成功（created 或 reused 都算成功）；非 0 是真实错误。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Literal

from app.adapters.database import get_database
from app.adapters.database.interface.protocol import Database
from app.repositories.users import UserRepository
from app.settings import get_settings


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    status: Literal["created", "reused"]
    user_id: str
    username: str


async def bootstrap_admin(
    *,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
    db: Database | None = None,
) -> BootstrapResult:
    """主流程，可被 CLI 或测试直接调用。

    入参全部 optional —— None 时从 settings 读默认。
    `db` 可由测试显式注入（SQLite/in-memory），生产/CLI 走 `get_database()`。
    """
    settings = get_settings()
    final_username = username or settings.bootstrap_admin_username
    final_email = email or settings.bootstrap_admin_email
    final_password = password or settings.bootstrap_admin_password

    owns_db = db is None
    if db is None:
        db = get_database()
        await db.connect()
    try:
        repo = UserRepository(db)
        existing = await repo.get_by_username(final_username)
        if existing is not None:
            return BootstrapResult(
                status="reused", user_id=existing.id, username=existing.username,
            )
        created = await repo.create(
            username=final_username,
            email=final_email,
            plaintext_password=final_password,
            is_super=True,
        )
        return BootstrapResult(status="created", user_id=created.id, username=created.username)
    finally:
        if owns_db:
            await db.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge-bootstrap-admin")
    parser.add_argument("--username", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human text")
    args = parser.parse_args(argv)

    try:
        result = asyncio.run(
            bootstrap_admin(
                username=args.username,
                email=args.email,
                password=args.password,
            )
        )
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"[bootstrap-admin] ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({
            "ok": True,
            "status": result.status,
            "user_id": result.user_id,
            "username": result.username,
        }))
    else:
        verb = "created" if result.status == "created" else "already exists"
        print(f"[bootstrap-admin] {verb}: {result.username} (id={result.user_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
