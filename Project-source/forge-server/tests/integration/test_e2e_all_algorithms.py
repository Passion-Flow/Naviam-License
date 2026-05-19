"""所有 3 算法（4 个 alg id）跑完整 .forge 签发 → 解包 → 跨实现验签。

剧本（每个 algorithm 独立跑）：
1. server 端 issuer 用 key_storage 中的 active 密钥签 license → 打包 .forge
2. forge-verifier 解 .forge + 用对应公钥验签
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.key_storage.local_file.backend import LocalFileKeyStorage
from app.core.key_storage.rotation import generate_and_save_signing_key
from app.core.license.issuer import IssueLicenseRequest, issue_license_with_storage

# verifier 侧
from forge_verifier.algorithms import get_algorithm_verifier
from forge_verifier.parsing import unpack


ALGORITHMS = ["ed25519", "rsa2048", "rsa4096", "sm2"]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.asyncio
async def test_full_issue_then_verifier_can_verify(algorithm: str, tmp_path: Path) -> None:
    storage = LocalFileKeyStorage(root=tmp_path, passphrase="pw")
    record = await generate_and_save_signing_key(storage, algorithm=algorithm)

    req = IssueLicenseRequest(
        customer_id="c",
        product_id="p",
        mode="offline",
        scope="customer_x_product",
        algorithm=algorithm,
        binding="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        features={},
        limits={},
    )
    issued = await issue_license_with_storage(storage=storage, req=req)
    assert issued.metadata.algorithm == algorithm

    # verifier 端：解包 + 拿 server 落盘的公钥验签
    forge = unpack(issued.forge_file)
    assert forge.metadata.algorithm == algorithm

    verifier_fn = get_algorithm_verifier(algorithm)
    assert verifier_fn(record.public_key, forge.payload_canonical_bytes, forge.signature) is True

    # 篡改 payload → 验签失败
    tampered = forge.payload_canonical_bytes.replace(b'"product_id":"p"', b'"product_id":"X"')
    if tampered != forge.payload_canonical_bytes:
        assert verifier_fn(record.public_key, tampered, forge.signature) is False
