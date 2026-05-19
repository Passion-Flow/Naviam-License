"""签名引擎 — 3 算法（Ed25519 / RSA / SM2）统一接口。

业务代码 import Signer Protocol；具体算法实现由 settings.signing_default_algorithm 决定。
"""
from __future__ import annotations

from typing import Literal

from app.core.signing.interface import KeyPair, Signature, Signer

Algorithm = Literal["ed25519", "rsa2048", "rsa4096", "sm2"]


def get_signer(algorithm: Algorithm) -> Signer:
    match algorithm:
        case "ed25519":
            from app.core.signing.ed25519.signer import Ed25519Signer
            return Ed25519Signer()
        case "rsa2048" | "rsa4096":
            from app.core.signing.rsa.signer import RsaSigner
            return RsaSigner(key_size=2048 if algorithm == "rsa2048" else 4096)
        case "sm2":
            from app.core.signing.sm2.signer import Sm2Signer
            return Sm2Signer()
        case _ as a:
            raise ValueError(f"Unsupported signing algorithm: {a}")


__all__ = ["Algorithm", "KeyPair", "Signature", "Signer", "get_signer"]
