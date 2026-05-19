"""CrlFetcher 端到端：mock LA `/revocation-list/{algo}.crl` 响应。"""
from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from forge_verifier.crl import CrlFetcher


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _build_crl(
    *,
    sk: Ed25519PrivateKey,
    sequence: int = 1,
    revoked: list[str] | None = None,
    next_update_offset_seconds: int = 86400,
) -> bytes:
    now = datetime.now(timezone.utc)
    revoked = revoked or []
    entries = [{"license_id": lid, "revoked_at": now.isoformat(), "reason": "test"} for lid in revoked]
    payload = {
        "crl_version": "1.0",
        "sequence": sequence,
        "issued_at": now.isoformat(),
        "next_update_at": (now + timedelta(seconds=next_update_offset_seconds)).isoformat(),
        "entries": sorted(entries, key=lambda e: e["license_id"]),
    }
    payload_bytes = _canonical(payload)
    sig = sk.sign(payload_bytes)
    metadata = {
        "magic": "crl",
        "crl_format_version": "1.0",
        "algorithm": "ed25519",
        "key_id": "ed25519-test",
        "signed_at": now.isoformat(),
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in [
            ("payload.json", payload_bytes),
            ("signature.bin", sig),
            ("metadata.json", _canonical(metadata)),
        ]:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_fetch_writes_cache(tmp_path: Path) -> None:
    sk = Ed25519PrivateKey.generate()
    crl_bytes = _build_crl(sk=sk, sequence=1, revoked=["lic-abc"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=crl_bytes, headers={"content-type": "application/octet-stream"})

    transport = httpx.MockTransport(handler)
    fetcher = CrlFetcher(
        base_url="https://la.example.com",
        algorithm="ed25519",
        public_key=sk.public_key().public_bytes_raw(),
        cache_dir=tmp_path,
    )
    async with httpx.AsyncClient(transport=transport) as c:
        result = await fetcher.fetch(client=c)

    assert result.fetched_new is True
    assert result.crl_path is not None and result.crl_path.exists()
    assert result.crl_path.read_bytes() == crl_bytes
    assert result.sequence == 1


@pytest.mark.asyncio
async def test_fetch_refuses_sequence_rollback(tmp_path: Path) -> None:
    """攻击者重放旧 CRL（小 sequence）→ 拒绝覆盖缓存。"""
    sk = Ed25519PrivateKey.generate()
    new_crl = _build_crl(sk=sk, sequence=5, revoked=["lic-abc"])

    # 先用 sequence=5 填缓存
    def handler_v5(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=new_crl)
    transport = httpx.MockTransport(handler_v5)
    fetcher = CrlFetcher(
        base_url="https://la.example.com",
        algorithm="ed25519",
        public_key=sk.public_key().public_bytes_raw(),
        cache_dir=tmp_path,
    )
    async with httpx.AsyncClient(transport=transport) as c:
        r1 = await fetcher.fetch(client=c)
        assert r1.sequence == 5

    # 然后服务端返回 sequence=1 的旧 CRL — fetcher 应拒绝
    old_crl = _build_crl(sk=sk, sequence=1, revoked=[])

    def handler_v1(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=old_crl)
    transport_v1 = httpx.MockTransport(handler_v1)
    async with httpx.AsyncClient(transport=transport_v1) as c:
        r2 = await fetcher.fetch(client=c)

    assert r2.fetched_new is False
    assert r2.sequence == 5
    assert "refusing to roll back" in (r2.reason or "")
    # 缓存内容未变
    cache_path = tmp_path / "crl" / "ed25519.crl"
    assert cache_path.read_bytes() == new_crl


@pytest.mark.asyncio
async def test_fetch_rejects_bad_signature(tmp_path: Path) -> None:
    """LA 公钥与签 CRL 的私钥不匹配 → 拒绝写入。"""
    la_sk = Ed25519PrivateKey.generate()
    attacker_sk = Ed25519PrivateKey.generate()
    fake_crl = _build_crl(sk=attacker_sk, sequence=1)

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fake_crl)

    transport = httpx.MockTransport(handler)
    fetcher = CrlFetcher(
        base_url="https://la.example.com",
        algorithm="ed25519",
        public_key=la_sk.public_key().public_bytes_raw(),  # 用 LA 公钥
        cache_dir=tmp_path,
    )
    async with httpx.AsyncClient(transport=transport) as c:
        result = await fetcher.fetch(client=c)
    assert result.fetched_new is False
    assert "invalid crl" in (result.reason or "")
    # 不该写缓存
    cache_path = tmp_path / "crl" / "ed25519.crl"
    assert not cache_path.exists()


@pytest.mark.asyncio
async def test_fetch_network_error_returns_cached(tmp_path: Path) -> None:
    """先成功拉一次，再模拟网络错 → 仍返回缓存路径。"""
    sk = Ed25519PrivateKey.generate()
    crl_bytes = _build_crl(sk=sk, sequence=1)

    def good_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=crl_bytes)

    fetcher = CrlFetcher(
        base_url="https://la.example.com",
        algorithm="ed25519",
        public_key=sk.public_key().public_bytes_raw(),
        cache_dir=tmp_path,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(good_handler)) as c:
        await fetcher.fetch(client=c)

    def bad_handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated")

    async with httpx.AsyncClient(transport=httpx.MockTransport(bad_handler)) as c:
        result = await fetcher.fetch(client=c)
    assert result.fetched_new is False
    assert result.crl_path is not None and result.crl_path.exists()
    assert result.sequence == 1
    assert "network error" in (result.reason or "")
