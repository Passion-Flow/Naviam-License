"""HTTP API + DB-backed 持久化端到端：

剧本：
1. 装好 SQLite-backed AppState（包含 LicenseRepository / DbBackedApiKeyAuth / DbBackedRevocationStore）
2. POST /api/v1/licenses/issue → 自动持久化到 DB
3. 直查 DB 验证 license 已落盘
4. 服务端调 CrlManager.revoke 把它加入 CRL
5. GET /api/v1/revocation-list/ed25519.crl → 拉到含该 license 的 CRL
6. 重启 AppState（模拟服务重启）→ 用同一 DB → license 仍可查到
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.database.postgres.adapter import PostgresDatabase
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER
from app.models import Base
from app.repositories import (
    ApiKeyRepository,
    DbBackedApiKeyAuth,
    DbBackedRevocationStore,
    LicenseRepository,
)
from app.settings import Settings
from app.state import AppState


@pytest.fixture
def settings(tmp_path: Path):
    import os
    env = {
        "DATABASE_HOST": "localhost", "DATABASE_PORT": "5432",
        "DATABASE_USERNAME": "test", "DATABASE_PASSWORD": "test", "DATABASE_DATABASE": "test",
        "CACHE_HOST": "localhost", "CACHE_PORT": "6379", "CACHE_PASSWORD": "test",
        "KEY_STORAGE_BACKEND": "local_file",
        "KEY_STORAGE_LOCAL_PATH": str(tmp_path / "keys"),
        "KEY_MASTER_PASSPHRASE": "test-pass",
        "AUTH_SESSION_SECRET": "test-secret-xxxxx",
        "OBJECT_STORAGE_TYPE": "local",
    }
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield Settings()  # type: ignore[call-arg]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture
async def db():
    """共享 SQLite in-memory DB（fixture 作用域内）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield PostgresDatabase.from_engine(engine)
    await engine.dispose()


def _build_state(settings: Settings, db, key_storage, api_plaintext: str | None = None) -> AppState:
    revocation_store = DbBackedRevocationStore(db)
    api_key_repo = ApiKeyRepository(db)
    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=CrlManager(store=revocation_store, key_storage=key_storage, algorithm="ed25519"),
        heartbeat_collector=InMemoryHeartbeatCollector(),
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
        database=db,
        license_repository=LicenseRepository(db),
        api_key_auth=DbBackedApiKeyAuth(api_key_repo),
    )
    return state


@pytest.mark.asyncio
async def test_issue_persists_to_db_and_revocation_propagates(settings, db, tmp_path: Path) -> None:
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")

    # 在 DB 里建一把 API Key
    api_key_repo = ApiKeyRepository(db)
    _, api_plaintext = await api_key_repo.issue(customer_id="cust-DB", project_label="proj")

    state = _build_state(settings, db, key_storage)
    app = create_app(state_builder=lambda: state)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        # 1. 签发
        r = await http.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: api_plaintext},
            json={
                "customer_id": "cust-DB",
                "product_id": "prod-DB",
                "mode": "offline",
                "scope": "instance",
                "algorithm": "ed25519",
                "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert r.status_code == 200, r.text
        license_id = r.json()["license_id"]

        # 2. 验证 license 已落 DB
        license_repo: LicenseRepository = state.license_repository  # type: ignore[assignment]
        fetched = await license_repo.get(license_id)
        assert fetched is not None
        assert fetched.customer_id == "cust-DB"

        # 3. 服务端 revoke
        await state.crl_manager.revoke(license_id, reason="test-revoke")

        # 4. CRL endpoint 应包含该 license_id
        crl_resp = await http.get("/api/v1/revocation-list/ed25519.crl")
        assert crl_resp.status_code == 200

        from forge_verifier.crl import unpack_crl
        crl = unpack_crl(crl_resp.content)
        assert crl.payload.contains(license_id) is not None


@pytest.mark.asyncio
async def test_persistence_survives_app_restart(settings, db, tmp_path: Path) -> None:
    """同 DB，重建 AppState/app（模拟重启）后 license 仍可查到。"""
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")

    api_key_repo = ApiKeyRepository(db)
    _, api_plaintext = await api_key_repo.issue(customer_id="cust", project_label="p")

    # 第一次启动：签发
    state1 = _build_state(settings, db, key_storage)
    app1 = create_app(state_builder=lambda: state1)
    async with httpx.AsyncClient(transport=ASGITransport(app=app1), base_url="http://t") as http:
        r = await http.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: api_plaintext},
            json={
                "customer_id": "cust", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": "ed25519", "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        license_id = r.json()["license_id"]

    # "重启"：新 AppState、新 app；同一 DB
    state2 = _build_state(settings, db, key_storage)
    app2 = create_app(state_builder=lambda: state2)
    license_repo2: LicenseRepository = state2.license_repository  # type: ignore[assignment]
    fetched = await license_repo2.get(license_id)
    assert fetched is not None
    assert fetched.customer_id == "cust"
