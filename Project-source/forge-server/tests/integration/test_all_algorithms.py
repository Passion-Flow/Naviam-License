"""3 套签名算法（Ed25519 / RSA-2048 / RSA-4096 / SM2）端到端：
- 生成密钥对
- 签 payload
- 验签通过
- 篡改后验签失败
- 跨密钥对（A 公钥验 B 签名）失败
"""
from __future__ import annotations

import pytest

from app.core.signing import get_signer


ALGORITHMS = ["ed25519", "rsa2048", "rsa4096", "sm2"]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_sign_verify_roundtrip(algorithm: str) -> None:
    signer = get_signer(algorithm)
    kp = signer.generate_keypair()
    assert kp.algorithm == algorithm
    assert kp.public_key and kp.private_key

    payload = b"hello, forge license"
    sig = signer.sign(private_key=kp.private_key, key_id=kp.key_id, payload=payload)
    assert sig.algorithm == algorithm
    assert sig.signature

    assert signer.verify(public_key=kp.public_key, payload=payload, signature=sig.signature)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_verify_rejects_tampered_payload(algorithm: str) -> None:
    signer = get_signer(algorithm)
    kp = signer.generate_keypair()
    payload = b"original payload"
    sig = signer.sign(private_key=kp.private_key, key_id=kp.key_id, payload=payload)
    assert not signer.verify(
        public_key=kp.public_key,
        payload=b"tampered payload",
        signature=sig.signature,
    )


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_verify_rejects_wrong_key(algorithm: str) -> None:
    signer = get_signer(algorithm)
    kp_a = signer.generate_keypair()
    kp_b = signer.generate_keypair()
    payload = b"payload"
    sig = signer.sign(private_key=kp_a.private_key, key_id=kp_a.key_id, payload=payload)
    # 用 B 的公钥验 A 的签名 → False
    assert not signer.verify(public_key=kp_b.public_key, payload=payload, signature=sig.signature)


def test_each_algorithm_produces_different_signatures() -> None:
    """同一 payload 用不同算法签，签名格式不同。"""
    payload = b"same payload"
    signatures: dict[str, bytes] = {}
    for algo in ALGORITHMS:
        s = get_signer(algo)
        kp = s.generate_keypair()
        sig = s.sign(private_key=kp.private_key, key_id=kp.key_id, payload=payload)
        signatures[algo] = sig.signature
    # 所有 4 个签名两两不等
    assert len(set(signatures.values())) == len(signatures)


def test_signature_lengths_by_algorithm() -> None:
    """各算法签名长度符合预期（regression detection）。"""
    payload = b"x"
    for algo, expected_min_len in [
        ("ed25519", 64),   # 固定 64 字节
        ("rsa2048", 250),  # ~256 字节（PSS 含 padding，但 <= 256）
        ("rsa4096", 500),  # ~512 字节
        ("sm2", 100),      # 70-72 字节 hex 编码 = 140+ 字符
    ]:
        s = get_signer(algo)
        kp = s.generate_keypair()
        sig = s.sign(private_key=kp.private_key, key_id=kp.key_id, payload=payload)
        assert len(sig.signature) >= expected_min_len, f"{algo} sig too short: {len(sig.signature)}"
