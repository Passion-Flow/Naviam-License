"""binding=soft — 首次启动记录指纹，后续验证未变化；变化时记录但**不**直接拒绝。

设计要点（攻防权衡）：
- 容器编排 / 重建机器 / 容灾切换都会改变 machine-id → hard binding 在这些场景会误杀
- soft 走"首次绑定 + 后续比对 + 异常上报"，把判定权交给 LA 端（hybrid mode 通过心跳判定）

状态文件防篡改：
- 路径：<state_dir>/<license_id>.binding
- 内容：JSON { fingerprint, recorded_at, hmac }
- HMAC key = SHA256(license_signature)  ← 把 .forge 签名当 key
  - 攻击者要伪造状态文件，必须先拿到 .forge 文件本身
  - 直接 hard 编辑 fingerprint 不通过 hmac 校验，verifier 当作"首次"重新记录
- 这不能挡 root 攻击者（root 永远可以做任何事），但能挡轻量复制+脚本批量启动场景
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from forge_verifier.binding.policy import BindingCheckResult
from forge_verifier.fingerprint import collect_fingerprint
from forge_verifier.parsing import ForgeFile

STATE_FILE_SUFFIX = ".binding"
STATE_HMAC_KEY_VERSION = 1  # 算法版本，未来若改 HMAC 算法走升迁


@dataclass(frozen=True, slots=True)
class _BindingState:
    fingerprint: str
    recorded_at: datetime
    key_version: int

    def to_signed_bytes(self, hmac_key: bytes) -> bytes:
        body = {
            "fingerprint": self.fingerprint,
            "recorded_at": self.recorded_at.astimezone(timezone.utc).isoformat(),
            "key_version": self.key_version,
        }
        body_bytes = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hmac.new(hmac_key, body_bytes, hashlib.sha256).hexdigest()
        signed = {"body": body, "hmac": digest}
        return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_signed_bytes(cls, data: bytes, hmac_key: bytes) -> "_BindingState | None":
        """读已签名状态。HMAC 不通过 → 当作"无状态"返回 None，让上层重新记录。"""
        try:
            obj = json.loads(data.decode("utf-8"))
            body = obj["body"]
            received_hmac = obj["hmac"]
            body_bytes = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            expected = hmac.new(hmac_key, body_bytes, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(received_hmac, expected):
                return None
            return cls(
                fingerprint=body["fingerprint"],
                recorded_at=datetime.fromisoformat(body["recorded_at"]),
                key_version=int(body.get("key_version", STATE_HMAC_KEY_VERSION)),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError):
            return None


class SoftBindingPolicy:
    name = "soft"

    def check(
        self,
        *,
        forge: ForgeFile,
        state_dir: Path,
        fingerprint_override: str | None = None,
    ) -> BindingCheckResult:
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / f"{forge.payload.license_id}{STATE_FILE_SUFFIX}"
        hmac_key = self._derive_hmac_key(forge)

        current = collect_fingerprint(override=fingerprint_override)
        prior = self._load_state(state_path, hmac_key)

        if prior is None:
            # 首次启动 / 状态文件被篡改 → 记录当前指纹
            self._write_state(
                state_path,
                _BindingState(
                    fingerprint=current,
                    recorded_at=datetime.now(timezone.utc),
                    key_version=STATE_HMAC_KEY_VERSION,
                ),
                hmac_key,
            )
            return BindingCheckResult(
                passed=True,
                current_fingerprint=current,
                expected_fingerprint=current,
                reason="first-run; fingerprint recorded",
            )

        if hmac.compare_digest(prior.fingerprint, current):
            return BindingCheckResult(
                passed=True,
                current_fingerprint=current,
                expected_fingerprint=prior.fingerprint,
            )

        # 已绑定但指纹变化 — soft 不直接拒绝，标记异常供 LA 心跳上报判定
        return BindingCheckResult(
            passed=True,
            current_fingerprint=current,
            expected_fingerprint=prior.fingerprint,
            reason=(
                "fingerprint changed since first run; reporting anomaly "
                "(soft binding does not block locally — LA decides)"
            ),
        )

    @staticmethod
    def _derive_hmac_key(forge: ForgeFile) -> bytes:
        """HMAC key = SHA256(license_signature)，离散到本 license。"""
        return hashlib.sha256(forge.signature).digest()

    @staticmethod
    def _load_state(state_path: Path, hmac_key: bytes) -> _BindingState | None:
        if not state_path.exists():
            return None
        try:
            data = state_path.read_bytes()
        except OSError:
            return None
        return _BindingState.from_signed_bytes(data, hmac_key)

    @staticmethod
    def _write_state(state_path: Path, state: _BindingState, hmac_key: bytes) -> None:
        tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        tmp.write_bytes(state.to_signed_bytes(hmac_key))
        tmp.replace(state_path)  # 原子替换
        try:
            state_path.chmod(0o600)  # 限制读权限（仅当前用户）
        except OSError:
            pass  # 非 POSIX 平台忽略
