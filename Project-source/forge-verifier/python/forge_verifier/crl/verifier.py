"""CRL 验签 + 过期检查。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from forge_verifier.algorithms import get_algorithm_verifier
from forge_verifier.crl.parsing import CrlFile, CrlFileError, unpack_crl


class CrlVerificationError(Exception):
    """CRL 验证失败基类。"""


class CrlInvalid(CrlVerificationError):
    """签名不通过 / 算法不支持 / 格式错。"""


class CrlExpired(CrlVerificationError):
    """CRL 已超 next_update_at —— LA 早该发新一份了，老 CRL 不再可信。"""


def verify_and_load_crl(
    *,
    crl_bytes: bytes,
    public_key: bytes,
    now: datetime | None = None,
) -> CrlFile:
    """解包 + 验签 + 过期检查。任何失败抛 CrlVerificationError 派生类。"""
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        crl = unpack_crl(crl_bytes)
    except CrlFileError as exc:
        raise CrlInvalid(f"unpack failed: {exc}") from exc

    try:
        algo_verify = get_algorithm_verifier(crl.metadata.algorithm)
    except ValueError as exc:
        raise CrlInvalid(str(exc)) from exc

    if not algo_verify(public_key, crl.payload_canonical_bytes, crl.signature):
        raise CrlInvalid("CRL signature verification failed")

    if crl.payload.next_update_at.astimezone(timezone.utc) < now_utc:
        raise CrlExpired(
            f"CRL stale: next_update_at={crl.payload.next_update_at.isoformat()} now={now_utc.isoformat()}"
        )

    return crl


def load_crl_from_disk(
    *,
    path: str | Path,
    public_key: bytes,
    now: datetime | None = None,
) -> CrlFile:
    return verify_and_load_crl(
        crl_bytes=Path(path).read_bytes(),
        public_key=public_key,
        now=now,
    )
