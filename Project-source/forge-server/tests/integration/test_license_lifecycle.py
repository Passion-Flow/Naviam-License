"""License lifecycle 端到端：download / verify / renew。

- download：返回原签发字节；未鉴权 401；不存在 404；签发未存档 410
- verify：base64 .forge → status=valid / expired / revoked / signature_invalid / malformed
- renew：签新 license，含原 customer/product；老 license 默认进 CRL
- renew 不存在 license → 404；renew + revoke_old=false 时老 license 不进 CRL
- 续期后老 license 调 verify → status=revoked，新 license → status=valid
- 全部审计落地：renew 写 license.issued + license.revoked 两条
"""
from __future__ import annotations

import base64
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
    yield PostgresDatabase.from_engine(engine)
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
    await user_repo.create(
        username="admin",
        email="admin@forge.local",
        plaintext_password="correct-horse-battery-staple",
        is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plain = await api_key_repo.issue(customer_id="c", project_label="p")

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
        api_key_repository=api_key_repo,
        user_repository=user_repo,
        session_store=SessionStore(cache, max_age_seconds=3600),
        audit_log_repository=AuditLogRepository(db),
    )
    return state, api_plain


@pytest.fixture
async def client(app_state):
    state, _ = app_state
    app = create_app(state_builder=lambda: state)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


@pytest.fixture
def api_key(app_state) -> str:
    return app_state[1]


async def _issue(client: httpx.AsyncClient, api_key: str, *, days: int = 30) -> dict:
    r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "acme", "product_id": "naviam", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
            "features": {"hd": True},
            "limits": {"max_users": 10},
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200


# ─────────────── download ───────────────


@pytest.mark.asyncio
async def test_download_requires_auth(client: httpx.AsyncClient, api_key: str) -> None:
    issued = await _issue(client, api_key)
    r = await client.get(f"/api/v1/licenses/{issued['license_id']}/download")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_download_returns_original_bytes(client: httpx.AsyncClient, api_key: str) -> None:
    issued = await _issue(client, api_key)
    expected = base64.b64decode(issued["forge_file_b64"])

    r = await client.get(
        f"/api/v1/licenses/{issued['license_id']}/download",
        headers={API_KEY_HEADER: api_key},
    )
    assert r.status_code == 200
    assert r.content == expected
    assert r.headers["content-type"] == "application/octet-stream"
    assert issued["license_id"] in r.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_unknown_license_404(client: httpx.AsyncClient, api_key: str) -> None:
    r = await client.get(
        "/api/v1/licenses/no-such-id/download",
        headers={API_KEY_HEADER: api_key},
    )
    assert r.status_code == 404


# ─────────────── verify ───────────────


@pytest.mark.asyncio
async def test_verify_requires_auth(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/licenses/verify",
        json={"forge_file_b64": "abcd"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_verify_valid_license(client: httpx.AsyncClient, api_key: str) -> None:
    issued = await _issue(client, api_key)
    r = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": issued["forge_file_b64"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "valid"
    assert body["license_id"] == issued["license_id"]
    assert body["reason"] is None


@pytest.mark.asyncio
async def test_verify_revoked_license(client: httpx.AsyncClient, api_key: str) -> None:
    issued = await _issue(client, api_key)
    await client.post(
        f"/api/v1/licenses/{issued['license_id']}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": "test"},
    )
    r = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": issued["forge_file_b64"]},
    )
    assert r.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_verify_expired_license(client: httpx.AsyncClient, api_key: str) -> None:
    # 用 negative days 签一个已过期 license
    r_iss = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    )
    issued = r_iss.json()
    r = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": issued["forge_file_b64"]},
    )
    assert r.json()["status"] == "expired"


@pytest.mark.asyncio
async def test_verify_signature_invalid(client: httpx.AsyncClient, api_key: str) -> None:
    """篡改 payload 内字符串 → 签名失败。"""
    issued = await _issue(client, api_key)
    raw = base64.b64decode(issued["forge_file_b64"])
    # 篡改 customer_id（出现在 payload.json 中）
    tampered = raw.replace(b'"acme"', b'"evil"', 1)
    assert tampered != raw, "payload modification should produce a different byte sequence"
    r = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": base64.b64encode(tampered).decode("ascii")},
    )
    assert r.json()["status"] == "signature_invalid"


@pytest.mark.asyncio
async def test_verify_malformed_input(client: httpx.AsyncClient, api_key: str) -> None:
    r = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": base64.b64encode(b"definitely-not-a-tar").decode("ascii")},
    )
    assert r.json()["status"] == "malformed"


@pytest.mark.asyncio
async def test_verify_rejects_bad_base64(client: httpx.AsyncClient, api_key: str) -> None:
    r = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": "!!!not-base64!!!"},
    )
    assert r.status_code == 400


# ─────────────── renew ───────────────


@pytest.mark.asyncio
async def test_renew_requires_auth(client: httpx.AsyncClient, api_key: str) -> None:
    issued = await _issue(client, api_key)
    r = await client.post(
        f"/api/v1/licenses/{issued['license_id']}/renew",
        json={"expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_renew_unknown_404(client: httpx.AsyncClient, api_key: str) -> None:
    r = await client.post(
        "/api/v1/licenses/no-such-id/renew",
        headers={API_KEY_HEADER: api_key},
        json={"expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_renew_issues_new_revokes_old(
    client: httpx.AsyncClient, api_key: str
) -> None:
    issued = await _issue(client, api_key)
    new_expiry = datetime.now(timezone.utc) + timedelta(days=365)

    r = await client.post(
        f"/api/v1/licenses/{issued['license_id']}/renew",
        headers={API_KEY_HEADER: api_key},
        json={"expires_at": new_expiry.isoformat()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old_license_id"] == issued["license_id"]
    assert body["new_license_id"] != issued["license_id"]
    assert body["old_revoked"] is True

    # 老 license 验证 → revoked
    v_old = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": issued["forge_file_b64"]},
    )
    assert v_old.json()["status"] == "revoked"

    # 新 license 验证 → valid
    v_new = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": body["forge_file_b64"]},
    )
    assert v_new.json()["status"] == "valid"
    assert v_new.json()["license_id"] == body["new_license_id"]


@pytest.mark.asyncio
async def test_renew_keep_old_alive(
    client: httpx.AsyncClient, api_key: str
) -> None:
    issued = await _issue(client, api_key)
    r = await client.post(
        f"/api/v1/licenses/{issued['license_id']}/renew",
        headers={API_KEY_HEADER: api_key},
        json={
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            "revoke_old": False,
        },
    )
    assert r.json()["old_revoked"] is False

    # 老 license 仍 valid
    v_old = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": issued["forge_file_b64"]},
    )
    assert v_old.json()["status"] == "valid"


@pytest.mark.asyncio
async def test_renew_preserves_customer_and_product(
    client: httpx.AsyncClient, api_key: str
) -> None:
    issued = await _issue(client, api_key)
    r = await client.post(
        f"/api/v1/licenses/{issued['license_id']}/renew",
        headers={API_KEY_HEADER: api_key},
        json={"expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()},
    )
    new_b64 = r.json()["forge_file_b64"]

    # 解包新 license 看 payload
    from app.core.license.forge_file import unpack
    forge = unpack(base64.b64decode(new_b64))
    assert forge.payload.customer_id == "acme"
    assert forge.payload.product_id == "naviam"
    assert forge.payload.mode == "offline"
    assert forge.payload.features == {"hd": True}  # 默认继承
    assert forge.payload.limits == {"max_users": 10}


@pytest.mark.asyncio
async def test_renew_can_override_features_and_limits(
    client: httpx.AsyncClient, api_key: str
) -> None:
    issued = await _issue(client, api_key)
    r = await client.post(
        f"/api/v1/licenses/{issued['license_id']}/renew",
        headers={API_KEY_HEADER: api_key},
        json={
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "features": {"hd": True, "4k": True},
            "limits": {"max_users": 50},
        },
    )
    from app.core.license.forge_file import unpack
    forge = unpack(base64.b64decode(r.json()["forge_file_b64"]))
    assert forge.payload.features == {"hd": True, "4k": True}
    assert forge.payload.limits == {"max_users": 50}


@pytest.mark.asyncio
async def test_renew_writes_audit(
    client: httpx.AsyncClient, api_key: str, app_state
) -> None:
    state, _ = app_state
    issued = await _issue(client, api_key)
    await client.post(
        f"/api/v1/licenses/{issued['license_id']}/renew",
        headers={API_KEY_HEADER: api_key},
        json={"expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()},
    )

    repo = state.audit_log_repository
    issued_events = await repo.list(action="license.issued")
    revoked_events = await repo.list(action="license.revoked")
    # 一条来自首签，一条来自 renew —— issue.routes 也写一条，加 renew 再一条
    assert len(issued_events) >= 2
    # 找到带 renewed_from 字段的那条
    renew_issue = [e for e in issued_events if e.payload.get("renewed_from") == issued["license_id"]]
    assert len(renew_issue) == 1
    # revoke 事件应当包含 renewed_into 字段
    renew_revoke = [e for e in revoked_events if e.payload.get("renewed_into")]
    assert len(renew_revoke) == 1
    assert renew_revoke[0].target_id == issued["license_id"]
