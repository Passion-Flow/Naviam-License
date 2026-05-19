"""Verifier 侧 RSA + SM2 验签 —— 用 server 端等价算法生成签名 + verifier 验。

不 import server 代码；用各 backend 库重做一遍签名（保证"两边独立实现"）。
"""
from __future__ import annotations

import secrets

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from gmssl import sm2

from forge_verifier.algorithms import get_algorithm_verifier
from forge_verifier.algorithms.rsa.verifier import verify as rsa_verify
from forge_verifier.algorithms.sm2.verifier import verify as sm2_verify


# ────────────────────────────────────────────────────────────
# RSA
# ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key_size", [2048, 4096])
def test_rsa_verify_accepts_valid_signature(key_size: int) -> None:
    sk = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    public_pem = sk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    payload = b"a license payload"
    sig = sk.sign(
        payload,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    assert rsa_verify(public_pem, payload, sig) is True


def test_rsa_verify_rejects_tampered_payload() -> None:
    sk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = sk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    sig = sk.sign(
        b"original",
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    assert rsa_verify(public_pem, b"tampered", sig) is False


def test_rsa_verify_rejects_non_rsa_public_key() -> None:
    """传入 Ed25519 公钥应安全返回 False，不抛异常。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    ed = Ed25519PrivateKey.generate()
    pem = ed.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert rsa_verify(pem, b"x", b"x") is False


def test_rsa_verify_rejects_malformed_key() -> None:
    assert rsa_verify(b"not-a-pem", b"x", b"x") is False


# ────────────────────────────────────────────────────────────
# SM2
# ────────────────────────────────────────────────────────────


SM2_CURVE_ORDER = int(
    "FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16
)


def _gen_sm2_keypair_hex() -> tuple[str, str]:
    d = secrets.randbelow(SM2_CURVE_ORDER - 1) + 1
    priv_hex = format(d, "064x")
    helper = sm2.CryptSM2(private_key=priv_hex, public_key="00" * 64)
    pub_hex = helper._kg(d, sm2.default_ecc_table["g"])
    return priv_hex, pub_hex


def test_sm2_verify_accepts_valid_signature() -> None:
    priv_hex, pub_hex = _gen_sm2_keypair_hex()
    signer = sm2.CryptSM2(private_key=priv_hex, public_key=pub_hex)
    payload = b"sm2 license payload"
    sig_hex = signer.sign_with_sm3(payload, random_hex_str=None)
    assert sm2_verify(pub_hex.encode("ascii"), payload, sig_hex.encode("ascii")) is True


def test_sm2_verify_rejects_tampered_payload() -> None:
    priv_hex, pub_hex = _gen_sm2_keypair_hex()
    signer = sm2.CryptSM2(private_key=priv_hex, public_key=pub_hex)
    sig_hex = signer.sign_with_sm3(b"original", random_hex_str=None)
    assert sm2_verify(pub_hex.encode("ascii"), b"tampered", sig_hex.encode("ascii")) is False


def test_sm2_verify_rejects_wrong_key() -> None:
    priv_a, pub_a = _gen_sm2_keypair_hex()
    _, pub_b = _gen_sm2_keypair_hex()
    signer = sm2.CryptSM2(private_key=priv_a, public_key=pub_a)
    sig_hex = signer.sign_with_sm3(b"payload", random_hex_str=None)
    # 用 B 的公钥验 A 的签 → False
    assert sm2_verify(pub_b.encode("ascii"), b"payload", sig_hex.encode("ascii")) is False


def test_sm2_verify_rejects_malformed_inputs() -> None:
    assert sm2_verify(b"\xff\xfe", b"x", b"x") is False  # 非 ASCII 公钥
    assert sm2_verify(b"00" * 32, b"x", b"") is False  # 公钥长度不对


# ────────────────────────────────────────────────────────────
# Dispatch
# ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("algorithm", ["ed25519", "rsa2048", "rsa4096", "sm2"])
def test_get_algorithm_verifier_returns_callable(algorithm: str) -> None:
    """工厂能为所有 3 算法（rsa 二档同函数）返回可调用 verifier。"""
    fn = get_algorithm_verifier(algorithm)
    assert callable(fn)
