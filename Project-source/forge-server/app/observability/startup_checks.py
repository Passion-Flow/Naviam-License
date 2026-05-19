"""启动期自检 —— DB / Cache / KeyStorage 全部可达 + 可读才放行。

设计：
- 每个 check 独立返回 (name, ok, detail)
- run_startup_checks 聚合所有失败成一条 StartupCheckError
- settings.startup_strict 决定 main.py 是 sys.exit(1) 还是 warning
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.state import AppState

logger = structlog.get_logger("forge.startup.checks")


class StartupCheckError(Exception):
    pass


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


async def run_startup_checks(state: AppState) -> None:
    results: list[CheckResult] = []
    results.append(await _check_database(state))
    results.append(await _check_cache(state))
    results.append(await _check_key_storage(state))
    for r in results:
        logger.info("startup_check", check=r.name, ok=r.ok, detail=r.detail or "")
    failures = [r for r in results if not r.ok]
    if failures:
        raise StartupCheckError(
            "; ".join(f"{r.name}: {r.detail or 'failed'}" for r in failures)
        )


async def _check_database(state: AppState) -> CheckResult:
    if state.database is None:
        return CheckResult("database", True, "skipped (no DB configured)")
    try:
        ok = await state.database.health_check()  # type: ignore[union-attr]
        return CheckResult("database", bool(ok), "" if ok else "health_check() returned False")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("database", False, str(exc))


async def _check_cache(state: AppState) -> CheckResult:
    cache = getattr(state.session_store, "_cache", None)
    if cache is None:
        return CheckResult("cache", True, "skipped (no cache configured)")
    try:
        # 写入 + 读取 + 删除 一个 probe key
        probe = "__forge_startup_probe__"
        await cache.set(probe, "ok", ttl_seconds=5)
        v = await cache.get(probe)
        await cache.delete(probe)
        return CheckResult("cache", v == b"ok" or v == "ok", "" if v else "probe key missing")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("cache", False, str(exc))


async def _check_key_storage(state: AppState) -> CheckResult:
    storage = state.key_storage
    try:
        # list_ids 是 KeyStorage Protocol 必有方法；不一定有 key（首次部署）
        ids = await storage.list_ids() if hasattr(storage, "list_ids") else []
        return CheckResult(
            "key_storage",
            True,
            f"{len(ids) if ids else 0} key(s) on backend={getattr(storage, 'backend_name', '?')}",
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult("key_storage", False, str(exc))
