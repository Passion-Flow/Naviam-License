"""HTTP API 端到端 —— FastAPI + httpx AsyncClient。

覆盖：
- /health 不鉴权
- /licenses/issue 鉴权 + 签发 → 返回 base64 .forge
- /public-keys/{key_id} 取公钥
- /revocation-list/{algo}.crl 拉 CRL
- /licenses/{id}/heartbeat HMAC 鉴权 + 多环境检测
- 完整克隆检测剧本：客户 A 心跳 → 客户 B 拷贝心跳 → anomaly=True
"""
from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.heartbeat import HeartbeatRequest, compute_signature
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER, hash_api_key
from app.settings import Settings
from app.state import ApiKeyInfo, AppState, build_state


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Pydantic Settings instance with all required env-style fields."""
    # 用 environ 直接构造 Settings（绕过 .env 文件依赖）
    import os
    env = {
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DATABASE_USERNAME": "test",
        "DATABASE_PASSWORD": "test",
        "DATABASE_DATABASE": "test",
        "CACHE_HOST": "localhost",
        "CACHE_PORT": "6379",
        "CACHE_PASSWORD": "test",
        "KEY_STORAGE_BACKEND": "local_file",
        "KEY_STORAGE_LOCAL_PATH": str(tmp_path / "keys"),
        "KEY_MASTER_PASSPHRASE": "test-passphrase",
        "AUTH_SESSION_SECRET": "test-session-secret-aaaaa",
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
async def app_with_state(settings: Settings):
    """构造装好 state 的 FastAPI app（不走 lifespan 默认装配，避免读全局 settings）。"""
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )

    # 预生成一把 active 签名密钥（不然 /issue 拿不到 active key）
    await generate_and_save_signing_key(key_storage, algorithm="ed25519")

    # 装配一份 AppState，把 key_storage 替换为本地版（避免 settings 全局读）
    from app.core.license.crl import CrlManager, InMemoryRevocationStore
    from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector

    revocation_store = InMemoryRevocationStore()
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
    )

    # 预置一份 API Key 供测试用（明文 "test-api-key"）
    plaintext = "test-api-key-xxx"
    state.api_keys[hash_api_key(plaintext)] = ApiKeyInfo(
        key_id="ak-test-1",
        key_hash=hash_api_key(plaintext),
        customer_id="cust-test",
        project_label="forge-test",
    )

    app = create_app(state_builder=lambda: state)
    return app, plaintext


@pytest.fixture
async def client(app_with_state):
    app, _ = app_with_state
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def api_key(app_with_state) -> str:
    return app_with_state[1]


# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_issue_requires_api_key(client: AsyncClient) -> None:
    r = await client.post("/api/v1/licenses/issue", json={
        "customer_id": "c", "product_id": "p", "mode": "offline", "scope": "instance",
        "algorithm": "ed25519", "binding": "none",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_issue_license_full_flow(client: AsyncClient, api_key: str) -> None:
    r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "cust-1",
            "product_id": "prod-naviam",
            "mode": "offline",
            "scope": "customer_x_product",
            "algorithm": "ed25519",
            "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "features": {"sso": True},
            "limits": {"max_users": 10},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["algorithm"] == "ed25519"
    forge_bytes = base64.b64decode(body["forge_file_b64"])
    assert len(forge_bytes) > 100

    # 验签链路：取公钥 → 用 Verifier 验签
    pub_resp = await client.get(f"/api/v1/public-keys/{body['signing_key_id']}")
    assert pub_resp.status_code == 200
    public_key = base64.b64decode(pub_resp.json()["public_key_b64"])

    from forge_verifier.algorithms.ed25519.verifier import verify as ed_verify
    from forge_verifier.parsing import unpack
    forge = unpack(forge_bytes)
    assert ed_verify(public_key, forge.payload_canonical_bytes, forge.signature)


@pytest.mark.asyncio
async def test_public_key_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/v1/public-keys/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_revocation_list_endpoint(client: AsyncClient, api_key: str, app_with_state) -> None:
    """签发一份 license，吊销它，CRL endpoint 返回的 .crl 含该 license_id。"""
    app, _ = app_with_state
    state: AppState = app.state.forge_state

    # 先签
    issue_r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "offline", "scope": "instance",
            "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    license_id = issue_r.json()["license_id"]

    # 吊销
    await state.crl_manager.revoke(license_id, reason="leaked in test")

    # 拉 CRL
    crl_resp = await client.get("/api/v1/revocation-list/ed25519.crl")
    assert crl_resp.status_code == 200
    assert crl_resp.headers["content-type"] == "application/octet-stream"

    from forge_verifier.crl import unpack_crl
    crl = unpack_crl(crl_resp.content)
    assert crl.payload.contains(license_id) is not None


@pytest.mark.asyncio
async def test_revocation_list_unsupported_algorithm_404(client: AsyncClient) -> None:
    r = await client.get("/api/v1/revocation-list/rsa4096.crl")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_full_flow(client: AsyncClient, api_key: str) -> None:
    """完整心跳：签发 → 上报 → 服务端响应 valid + non-anomaly。"""
    issue_r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "hybrid", "scope": "instance",
            "algorithm": "ed25519", "binding": "soft",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    license_id = issue_r.json()["license_id"]

    # 构造合法心跳
    unsigned = HeartbeatRequest(
        license_id=license_id,
        fingerprint="fp-customer-A",
        reported_at=datetime.now(timezone.utc),
        nonce=secrets.token_hex(16),
        signature="placeholder",
    )
    sig = compute_signature(unsigned, api_key=api_key)
    body = unsigned.model_dump(mode="json")
    body["signature"] = sig

    r = await client.post(
        f"/api/v1/licenses/{license_id}/heartbeat",
        headers={API_KEY_HEADER: api_key},
        json=body,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["license_status"] == "valid"
    assert payload["multi_env_anomaly"] is False


@pytest.mark.asyncio
async def test_heartbeat_detects_clone(client: AsyncClient, api_key: str) -> None:
    """两个不同指纹用同一 license_id 心跳 → 第二次响应 anomaly=True。"""
    issue_r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "hybrid", "scope": "instance",
            "algorithm": "ed25519", "binding": "soft",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    license_id = issue_r.json()["license_id"]

    async def send_heartbeat(fingerprint: str) -> dict:
        unsigned = HeartbeatRequest(
            license_id=license_id,
            fingerprint=fingerprint,
            reported_at=datetime.now(timezone.utc),
            nonce=secrets.token_hex(16),
            signature="placeholder",
        )
        sig = compute_signature(unsigned, api_key=api_key)
        body = unsigned.model_dump(mode="json")
        body["signature"] = sig
        r = await client.post(
            f"/api/v1/licenses/{license_id}/heartbeat",
            headers={API_KEY_HEADER: api_key},
            json=body,
        )
        assert r.status_code == 200, r.text
        return r.json()

    # 客户 A 心跳：clean
    resp_a = await send_heartbeat("fp-A")
    assert resp_a["multi_env_anomaly"] is False

    # 客户 B 拷贝 license 后心跳：anomaly
    resp_b = await send_heartbeat("fp-B")
    assert resp_b["multi_env_anomaly"] is True


@pytest.mark.asyncio
async def test_heartbeat_rejects_wrong_hmac(client: AsyncClient, api_key: str) -> None:
    issue_r = await client.post(
        "/api/v1/licenses/issue",
        headers={API_KEY_HEADER: api_key},
        json={
            "customer_id": "c", "product_id": "p", "mode": "hybrid", "scope": "instance",
            "algorithm": "ed25519", "binding": "none",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    license_id = issue_r.json()["license_id"]

    body = {
        "license_id": license_id,
        "fingerprint": "fp",
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "verifier_version": "test",
        "signature": "deadbeef",  # 错的 signature
    }
    r = await client.post(
        f"/api/v1/licenses/{license_id}/heartbeat",
        headers={API_KEY_HEADER: api_key},
        json=body,
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_heartbeat_path_body_mismatch(client: AsyncClient, api_key: str) -> None:
    unsigned = HeartbeatRequest(
        license_id="lic-from-body",
        fingerprint="fp",
        reported_at=datetime.now(timezone.utc),
        nonce=secrets.token_hex(16),
        signature="placeholder",
    )
    body = unsigned.model_dump(mode="json")
    body["signature"] = compute_signature(unsigned, api_key=api_key)
    r = await client.post(
        "/api/v1/licenses/lic-from-path/heartbeat",
        headers={API_KEY_HEADER: api_key},
        json=body,
    )
    assert r.status_code == 400
