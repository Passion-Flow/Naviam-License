"""跨语言互操作测试向量验证（Python 实现）。

读 `forge-verifier/spec/test-vectors/NNN-*/` 下生成的样本，用 Verifier 跑一遍，
确保 Python 实现与 spec 一致。TS / Go 实现以后也按本目录的向量校验。
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from forge_verifier import Verifier

# spec 目录相对位置
VECTORS_ROOT = Path(__file__).resolve().parent.parent.parent / "spec" / "test-vectors"


def _list_vectors() -> list[Path]:
    if not VECTORS_ROOT.exists():
        return []
    return sorted(p for p in VECTORS_ROOT.iterdir() if p.is_dir() and (p / "expected.forge").exists())


@pytest.mark.parametrize("vector_dir", _list_vectors(), ids=lambda p: p.name)
def test_vector_verifies(vector_dir: Path, tmp_path: Path) -> None:
    expected_verify = json.loads((vector_dir / "expected-verify.json").read_text())
    keypair = json.loads((vector_dir / "keypair.json").read_text())

    license_path = tmp_path / "license.forge"
    license_path.write_bytes((vector_dir / "expected.forge").read_bytes())

    public_key = base64.b64decode(keypair["public_key_b64"])

    # 测试向量 003 是 hard binding，需要让 fingerprint_override 算出与 payload.bound_fingerprint 一致
    # 因为 hard binding 的 fingerprint 是 SHA-256(override=<value>)，没有简单 override 能凑出
    # "aaaa...aaaa"（64 a），所以 hard binding 向量不在此测试中跑 verify 通过路径，只检查 verify 不崩
    if expected_verify.get("binding") == "hard":
        # 故意给一个不匹配的 fingerprint，验证 verifier 报 binding_mismatch
        from forge_verifier import VerificationFailed
        verifier = Verifier(
            license_file_path=license_path,
            public_key=public_key,
            mode="offline",
            state_dir=tmp_path / "state",
            fingerprint_override="will-not-match",
        )
        with pytest.raises(VerificationFailed) as exc:
            verifier.verify_blocking()
        assert exc.value.status == "binding_mismatch"
        return

    # offline / hybrid / soft 路径都能直接 valid
    verifier = Verifier(
        license_file_path=license_path,
        public_key=public_key,
        mode="offline",
        state_dir=tmp_path / "state",
        fingerprint_override="test-machine",
    )
    result = verifier.verify_blocking()
    assert result.status == "valid"
    assert result.license_id == expected_verify["license_id"]
