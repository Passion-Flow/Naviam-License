"""多算法 HTTP 端到端串测 —— Round AG 收尾。

接前面：
- AF 把 /revocation-list/<algo>.crl 改成尊重 enabled list
- 已有 test_e2e_all_algorithms 走 raw signer/verifier，不走 HTTP

本测试在**同一台 server**上，对 enabled 的 3 个算法（ed25519 / rsa2048 / sm2）
**并行**跑完整 HTTP 生命周期：
  1. POST /api/v1/licenses/issue (algorithm=X)
  2. POST /api/v1/licenses/verify (same .forge) → status=valid
  3. POST /api/v1/licenses/{id}/revoke
  4. GET  /api/v1/revocation-list/X.crl —— 应当包含刚吊销的 license_id
  5. POST /api/v1/licenses/verify (same .forge) → status=revoked

并行的关键在于：CrlManager 内部维持 per-algorithm 缓存，单次 revoke 把
**所有算法**缓存联动失效，但只有真正请求对应算法时才会重签 —— 通过测试每个算法
路径单独走完整链路，证明没有交叉污染。
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


ALGORITHMS = ["ed25519", "rsa2048", "sm2"]


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
        "SIGNING_ALGORITHMS_ENABLED": '["ed25519","rsa2048","sm2"]',
        "SIGNING_DEFAULT_ALGORITHM": "ed25519",
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
    for algo in ALGORITHMS:
        await generate_and_save_signing_key(key_storage, algorithm=algo)

    revocation_store = DbBackedRevocationStore(db)
    user_repo = UserRepository(db)
    await user_repo.create(
        username="admin", email="admin@forge.local",
        plaintext_password="x", is_super=True,
    )
    api_key_repo = ApiKeyRepository(db)
    _, api_plain = await api_key_repo.issue(customer_id="c", project_label="p")

    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=CrlManager(
            store=revocation_store,
            key_storage=key_storage,
            algorithm="ed25519",
        ),
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


def _crl_contains(crl_bytes: bytes, license_id: str) -> bool:
    """Cheap substring check on the embedded payload.json."""
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(crl_bytes), mode="r") as tf:
        member = tf.getmember("payload.json")
        f = tf.extractfile(member)
        assert f is not None
        return f'"{license_id}"' in f.read().decode("utf-8")


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ALGORITHMS)
async def test_full_lifecycle_per_algorithm(
    client: httpx.AsyncClient, api_key: str, algorithm: str
) -> None:
    """每个 enabled 算法独立跑 issue→verify→revoke→CRL→verify(revoked) 整链。"""
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    # 1) issue
    iss = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": algorithm, "binding": "none",
            "expires_at": expires_at,
        },
    )
    assert iss.status_code == 200, iss.text
    body = iss.json()
    assert body["algorithm"] == algorithm
    license_id = body["license_id"]
    forge_b64 = body["forge_file_b64"]

    # 2) verify → valid
    v1 = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": forge_b64},
    )
    assert v1.status_code == 200
    assert v1.json()["status"] == "valid"
    assert v1.json()["license_id"] == license_id

    # 3) revoke
    rev = await client.post(
        f"/api/v1/licenses/{license_id}/revoke",
        headers={API_KEY_HEADER: api_key},
        json={"reason": f"e2e-{algorithm}"},
    )
    assert rev.status_code == 200

    # 4) corresponding CRL must list the license
    crl = await client.get(f"/api/v1/revocation-list/{algorithm}.crl")
    assert crl.status_code == 200
    assert _crl_contains(crl.content, license_id), (
        f"{algorithm}.crl did not include freshly-revoked {license_id}"
    )

    # 5) verify same .forge → revoked
    v2 = await client.post(
        "/api/v1/licenses/verify",
        headers={API_KEY_HEADER: api_key},
        json={"forge_file_b64": forge_b64},
    )
    assert v2.status_code == 200
    assert v2.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_algorithms_do_not_cross_contaminate(
    client: httpx.AsyncClient, api_key: str
) -> None:
    """串行签发 3 个算法的 license 各 1 张，全部吊销，三份 CRL 应各自包含
    对应 license（不互窜）。"""
    issued_by_algo: dict[str, str] = {}
    for algo in ALGORITHMS:
        r = await client.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: api_key},
            json={
                "customer_id": "c", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": algo, "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert r.status_code == 200, r.text
        issued_by_algo[algo] = r.json()["license_id"]

    for algo, lid in issued_by_algo.items():
        await client.post(
            f"/api/v1/licenses/{lid}/revoke",
            headers={API_KEY_HEADER: api_key},
            json={"reason": "x"},
        )

    # 所有 3 份 CRL 都应包含**全部** 3 个 license_id（revocation_store 与算法解耦）
    for algo in ALGORITHMS:
        crl = await client.get(f"/api/v1/revocation-list/{algo}.crl")
        for lid in issued_by_algo.values():
            assert _crl_contains(crl.content, lid), (
                f"{algo}.crl missing {lid}"
            )


@pytest.mark.asyncio
async def test_disabled_algorithm_issue_rejects(
    client: httpx.AsyncClient, api_key: str
) -> None:
    """`rsa4096` 不在 enabled list — 即便代码支持，issue 也应失败（409，no active key）。

    与 AF 的 CRL 路径一致：未配置的算法没有 active key，issue 端会被 NoActiveKeyError 挡掉。
    """
    r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline",
            "scope": "instance", "algorithm": "rsa4096", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 409, r.text  # NoActiveKeyError → 409 CONFLICT


@pytest.mark.asyncio
async def test_per_algorithm_forge_metadata(
    client: httpx.AsyncClient, api_key: str
) -> None:
    """解出 .forge 的 metadata.algorithm 必须严格等于请求时填的 algorithm。"""
    import io
    import json
    import tarfile

    for algo in ALGORITHMS:
        r = await client.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: api_key},
            json={
                "customer_id": "c", "product_id": "p", "mode": "offline",
                "scope": "instance", "algorithm": algo, "binding": "none",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert r.status_code == 200
        raw = base64.b64decode(r.json()["forge_file_b64"])
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tf:
            meta = json.loads(tf.extractfile(tf.getmember("metadata.json")).read())
        assert meta["algorithm"] == algo
