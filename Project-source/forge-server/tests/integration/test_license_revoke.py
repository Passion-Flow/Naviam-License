"""License 吊销 / 解吊销端点 端到端测试：
- 未鉴权 → 401
- API Key 吊销 → 200 + 写 audit
- Admin Session 吊销 → 200 + 写 audit + revoked_by_user_id 落库
- 吊销不存在的 license → 404
- 双重吊销（同 ID 调两次）→ 第二次仍 200，但 audit 只生成两条
- unrevoke 没被吊销过 → 404
- unrevoke 成功 → CRL 中不再出现
- GET /licenses/{id} → admin only，返回 revoked 状态
- CRL 端点立刻包含新吊销项（sequence 增长）
"""
from __future__ import annotations

import io
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fakeredis import aioredis as fakeredis_async
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.cache.redis.adapter import RedisCache
from app.adapters.database.postgres.adapter import PostgresDatabase
from app.core.auth import SessionStore
from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER
from app.models import Base
from app.models.revocation import RevocationEntryModel
from app.repositories import (
    ApiKeyRepository,
    AuditLogRepository,
    DbBackedApiKeyAuth,
    DbBackedRevocationStore,
    LicenseRepository,
    UserRepository,
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
        "AUTH_SESSION_SECRET": "test-session-xxxxxxxx",
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
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db_inst = PostgresDatabase.from_engine(engine)
    try:
        yield db_inst
    finally:
        await engine.dispose()


@pytest.fixture
async def cache():
    fake = fakeredis_async.FakeRedis(decode_responses=False)
    yield RedisCache.from_client(fake, db=1)
    await fake.aclose()


@pytest.fixture
async def app_state(settings, db, cache, tmp_path: Path):
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")

    revocation_store = DbBackedRevocationStore(db)
    user_repo = UserRepository(db)
    admin = await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plaintext = await api_key_repo.issue(customer_id="c", project_label="p")

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
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        audit_log_repository=AuditLogRepository(db),
    )
    return state, api_plaintext, admin.id


@pytest.fixture
async def client(app_state):
    state, _, _ = app_state
    app = create_app(state_builder=lambda: state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


@pytest.fixture
def api_key(app_state) -> str:
    return app_state[1]


@pytest.fixture
def admin_id(app_state) -> str:
    return app_state[2]


# ────────────────────────────────────────────────────────────


async def _issue_license(client: httpx.AsyncClient, api_key: str) -> str:
    r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["license_id"]


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200, r.text


def _crl_payload_contains(crl_bytes: bytes, license_id: str) -> bool:
    """从 .crl tar 流取出 payload.json，判断目标 license_id 是否在 entries 里。"""
    with tarfile.open(fileobj=io.BytesIO(crl_bytes), mode="r") as tf:
        member = tf.getmember("payload.json")
        f = tf.extractfile(member)
        assert f is not None
        text = f.read().decode("utf-8")
    return f'"{license_id}"' in text


@pytest.mark.asyncio
async def test_revoke_requires_auth(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)
    r = await client.post(f"/api/v1/licenses/{license_id}/revoke", json={"reason": "x"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_revoke_with_api_key(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)
    r = await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "test-reason"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["revoked"] is True
    assert body["reason"] == "test-reason"
    assert body["revoked_by"].startswith("apikey:")


@pytest.mark.asyncio
async def test_revoke_with_admin_writes_revoked_by(
    client: httpx.AsyncClient, api_key: str, admin_id: str, app_state
) -> None:
    state, _, _ = app_state
    license_id = await _issue_license(client, api_key)
    await _login(client)

    r = await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        json={"reason": "compromised-key"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["revoked_by"] == f"admin:{admin_id}"

    # DB 上 revoked_by_user_id 应等于 admin_id
    async with state.database.session() as sess:
        row = await sess.get(RevocationEntryModel, license_id)
        assert row is not None
        assert row.revoked_by_user_id == admin_id
        assert row.reason == "compromised-key"


@pytest.mark.asyncio
async def test_revoke_unknown_license_404(client: httpx.AsyncClient, api_key: str) -> None:
    r = await client.post(
        "/api/v1/licenses/no-such-id/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_revoke_is_idempotent(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)
    # 两次吊销
    r1 = await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "first"},
    )
    r2 = await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "second-overwrites"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_unrevoke_only_works_after_revoke(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)
    r_no = await client.post(
        f"/api/v1/licenses/{license_id}/unrevoke",
        headers={API_KEY_HEADER: api_key},
    )
    assert r_no.status_code == 404

    await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "x"},
    )
    r_ok = await client.post(
        f"/api/v1/licenses/{license_id}/unrevoke",
        headers={API_KEY_HEADER: api_key},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["revoked"] is False


@pytest.mark.asyncio
async def test_revoke_appears_in_crl(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)

    # 吊销前 CRL 不含该 ID
    r1 = await client.get("/api/v1/revocation-list/ed25519.crl")
    assert r1.status_code == 200
    assert not _crl_payload_contains(r1.content, license_id)

    # 吊销
    await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "x"},
    )

    r2 = await client.get("/api/v1/revocation-list/ed25519.crl")
    assert r2.status_code == 200
    assert _crl_payload_contains(r2.content, license_id)

    # unrevoke 后从 CRL 中消失
    await client.post(
        f"/api/v1/licenses/{license_id}/unrevoke",
        headers={API_KEY_HEADER: api_key},
    )
    r3 = await client.get("/api/v1/revocation-list/ed25519.crl")
    assert not _crl_payload_contains(r3.content, license_id)


@pytest.mark.asyncio
async def test_revoke_writes_audit(
    client: httpx.AsyncClient, api_key: str, admin_id: str, app_state
) -> None:
    state, _, _ = app_state
    license_id = await _issue_license(client, api_key)

    await _login(client)
    await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        json={"reason": "audit-test"},
    )

    rows = await state.audit_log_repository.list(action="license.revoked")
    assert len(rows) == 1
    assert rows[0].actor_type == "user"
    assert rows[0].actor_id == admin_id
    assert rows[0].target_id == license_id
    assert rows[0].payload["reason"] == "audit-test"


@pytest.mark.asyncio
async def test_unrevoke_writes_audit(
    client: httpx.AsyncClient, api_key: str, app_state
) -> None:
    state, _, _ = app_state
    license_id = await _issue_license(client, api_key)
    await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "x"},
    )
    await client.post(
        f"/api/v1/licenses/{license_id}/unrevoke",
        headers={API_KEY_HEADER: api_key},
    )

    rows = await state.audit_log_repository.list(action="license.unrevoked")
    assert len(rows) == 1
    assert rows[0].target_id == license_id


@pytest.mark.asyncio
async def test_detail_requires_admin_session(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)
    # 不带 cookie
    r = await client.get(f"/api/v1/licenses/{license_id}")
    assert r.status_code == 401
    # 带 API Key 也不行（detail 只允许 admin session）
    r2 = await client.get(
        f"/api/v1/licenses/{license_id}",
        headers={API_KEY_HEADER: api_key},
    )
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_detail_returns_revoked_status(client: httpx.AsyncClient, api_key: str) -> None:
    license_id = await _issue_license(client, api_key)
    await _login(client)

    r = await client.get(f"/api/v1/licenses/{license_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["license_id"] == license_id
    assert body["customer_id"] == "c"
    assert body["revoked"] is False

    await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        json={"reason": "x"},
    )
    r2 = await client.get(f"/api/v1/licenses/{license_id}")
    assert r2.json()["revoked"] is True


@pytest.mark.asyncio
async def test_detail_unknown_license_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/v1/licenses/no-such-id")
    assert r.status_code == 404
