"""最终端到端：forge-verifier ⇄ forge-server 完整 HTTP 闭环。

剧本：
1. server 启动（in-memory backends，预生成密钥 + 预置 API Key）
2. 通过 HTTP POST /issue 签发一份 license
3. Verifier 用 httpx ASGITransport 当 base_url，跑 verify():
   - 拉 CRL（空 list） → 写本地缓存
   - 验签 → pass
   - binding=soft 首次记录
   - 发心跳 → server 返回 valid + anomaly=False
   - 整体 status=valid
4. server 端 revoke 该 license → 重发 CRL
5. Verifier 再 verify() → 拉到新 CRL → status=revoked
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.crl import CrlManager, InMemoryRevocationStore
from app.core.license.heartbeat import InMemoryHeartbeatCollector, MultiEnvDetector
from app.main import create_app
from app.middleware.api_key_auth import API_KEY_HEADER, hash_api_key
from app.settings import Settings
from app.state import ApiKeyInfo, AppState

# verifier 侧
from forge_verifier import Verifier, VerificationFailed


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
        "AUTH_SESSION_SECRET": "test-secret-xxxxxxx",
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
async def server(settings, tmp_path: Path):
    """启动 server 并返回 (app, state, api_key_plaintext, public_key)。"""
    key_storage = LocalFileKeyStorage(
        root=Path(settings.key_storage_local_path),
        passphrase=settings.key_master_passphrase,
    )
    record = await generate_and_save_signing_key(key_storage, algorithm="ed25519")
    revocation_store = InMemoryRevocationStore()
    state = AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=CrlManager(store=revocation_store, key_storage=key_storage, algorithm="ed25519"),
        heartbeat_collector=InMemoryHeartbeatCollector(),
        multi_env_detector=MultiEnvDetector(window=timedelta(hours=24), threshold=1),
        api_keys={},
    )
    api_key = "verifier-api-key-e2e"
    state.api_keys[hash_api_key(api_key)] = ApiKeyInfo(
        key_id="ak-1",
        key_hash=hash_api_key(api_key),
        customer_id="cust-e2e",
        project_label="e2e",
    )
    app = create_app(state_builder=lambda: state)
    return app, state, api_key, record.public_key


@pytest.mark.asyncio
async def test_full_e2e_loop(server, tmp_path: Path) -> None:
    app, state, api_key, public_key = server

    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://forge-test") as http:
        # ── 1. 签发 license ──
        r = await http.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: api_key},
            json={
                "customer_id": "cust-e2e",
                "product_id": "prod-x",
                "mode": "hybrid",
                "scope": "instance",
                "algorithm": "ed25519",
                "binding": "soft",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "features": {"sso": True},
                "limits": {"max_users": 10},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        license_id = body["license_id"]
        forge_bytes = base64.b64decode(body["forge_file_b64"])

        # 写本地
        license_path = tmp_path / "license.forge"
        license_path.write_bytes(forge_bytes)

        # ── 2. 构造 Verifier（hybrid，base_url 走 ASGI transport）──
        verifier = Verifier(
            license_file_path=license_path,
            public_key=public_key,
            mode="hybrid",
            heartbeat_base_url="http://forge-test",
            api_key=api_key,
            state_dir=tmp_path / "verifier-state",
            fingerprint_override="customer-A-machine",
        )
        # 让 Verifier 内部用我们这个 AsgiTransport（注入到 fetcher/client）
        # 简便起见：直接 patch httpx.AsyncClient 全局 — 但更整洁的是给 Verifier 加 transport 参数。
        # 这里走 monkeypatch 思路：把 httpx.AsyncClient 替换为带 transport 的工厂
        import httpx as httpx_mod
        original_async_client = httpx_mod.AsyncClient

        def _factory(*args, **kwargs):
            kwargs.setdefault("transport", transport)
            return original_async_client(*args, **kwargs)
        httpx_mod.AsyncClient = _factory
        try:
            result = await verifier.verify()
        finally:
            httpx_mod.AsyncClient = original_async_client

        assert result.status == "valid", result
        assert result.license_id == license_id

        # CRL 缓存应被写入
        crl_cache = tmp_path / "verifier-state" / "crl" / "ed25519.crl"
        assert crl_cache.exists()

        # ── 3. server revoke license ──
        await state.crl_manager.revoke(license_id, reason="leaked in e2e")

        # ── 4. Verifier 再次 verify → 应拉到新 CRL → status=revoked ──
        httpx_mod.AsyncClient = _factory
        try:
            with pytest.raises(VerificationFailed) as exc:
                await verifier.verify()
        finally:
            httpx_mod.AsyncClient = original_async_client
        assert exc.value.status == "revoked"


@pytest.mark.asyncio
async def test_e2e_anomaly_on_clone(server, tmp_path: Path) -> None:
    """完整克隆检测：客户 A 心跳一次 → 客户 B 拷贝 license + 不同指纹 → 第二次 verify 拿到 anomaly。"""
    app, state, api_key, public_key = server
    transport = ASGITransport(app=app)

    import httpx as httpx_mod
    original = httpx_mod.AsyncClient

    def _factory(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return original(*args, **kwargs)

    async with httpx.AsyncClient(transport=transport, base_url="http://forge-test") as http:
        r = await http.post(
            "/api/v1/licenses/issue",
            headers={API_KEY_HEADER: api_key},
            json={
                "customer_id": "cust", "product_id": "p", "mode": "hybrid",
                "scope": "instance", "algorithm": "ed25519", "binding": "soft",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        body = r.json()
        forge_bytes = base64.b64decode(body["forge_file_b64"])

        license_path = tmp_path / "license.forge"
        license_path.write_bytes(forge_bytes)

        def make_verifier(fp: str, state_subdir: str) -> Verifier:
            return Verifier(
                license_file_path=license_path,
                public_key=public_key,
                mode="hybrid",
                heartbeat_base_url="http://forge-test",
                api_key=api_key,
                state_dir=tmp_path / state_subdir,
                fingerprint_override=fp,
            )

        # 客户 A
        httpx_mod.AsyncClient = _factory
        try:
            res_a = await make_verifier("customer-A", "state-a").verify()
            assert res_a.status == "valid"

            # 客户 B 用同一 license 文件
            res_b = await make_verifier("customer-B", "state-b").verify()
            # server 通过心跳判定多环境 anomaly
            assert res_b.status == "binding_anomaly"
            assert "multi-environment" in (res_b.reason or "")
        finally:
            httpx_mod.AsyncClient = original
