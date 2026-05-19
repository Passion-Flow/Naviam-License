"""算法分发：根据 metadata.algorithm 找对应 verifier。"""
from __future__ import annotations

from typing import Callable

# (public_key, payload, signature) -> bool
AlgorithmVerifier = Callable[[bytes, bytes, bytes], bool]


def get_algorithm_verifier(algorithm: str) -> AlgorithmVerifier:
    if algorithm == "ed25519":
        from forge_verifier.algorithms.ed25519.verifier import verify as ed_verify
        return ed_verify
    if algorithm in {"rsa2048", "rsa4096"}:
        from forge_verifier.algorithms.rsa.verifier import verify as rsa_verify
        return rsa_verify
    if algorithm == "sm2":
        from forge_verifier.algorithms.sm2.verifier import verify as sm2_verify
        return sm2_verify
    raise ValueError(f"Unsupported algorithm: {algorithm!r}")


__all__ = ["AlgorithmVerifier", "get_algorithm_verifier"]
