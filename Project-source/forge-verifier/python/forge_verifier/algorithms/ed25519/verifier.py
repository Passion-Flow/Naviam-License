"""Ed25519 验签（Verifier 侧）。"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verify(public_key: bytes, payload: bytes, signature: bytes) -> bool:
    try:
        pk = Ed25519PublicKey.from_public_bytes(public_key)
        pk.verify(signature, payload)
        return True
    except (InvalidSignature, ValueError):
        return False
