"""Verifier 主入口。"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from forge_verifier.algorithms import get_algorithm_verifier
from forge_verifier.binding import get_binding_policy
from forge_verifier.crl import CrlFile, CrlFetcher, CrlVerificationError, verify_and_load_crl
from forge_verifier.exceptions import VerificationFailed
from forge_verifier.heartbeat import HeartbeatClient, HeartbeatClientError, HeartbeatResult
from forge_verifier.parsing import ForgeFile, ForgeFileError, unpack
from forge_verifier.types import Mode, VerificationResult, VerificationStatus

DEFAULT_STATE_DIR = Path("~/.forge-verifier/state").expanduser()


class Verifier:
    def __init__(
        self,
        *,
        license_file_path: str | Path,
        public_key: bytes,
        mode: Mode = "hybrid",
        heartbeat_base_url: str | None = None,
        api_key: str | None = None,
        recheck_interval_seconds: int = 300,
        grace_period_seconds: int = 0,
        state_dir: str | Path | None = None,
        fingerprint_override: str | None = None,
        crl_path: str | Path | None = None,
        crl_required: bool = False,
        crl_algorithm: str = "ed25519",
        online_required: bool = False,
    ) -> None:
        """
        Args:
            mode: offline / hybrid / online
            heartbeat_base_url: LA 服务根（如 https://forge.your-company.com）；hybrid/online 必填
            api_key: 项目级 API Key 明文；用于心跳鉴权 + HMAC
            crl_path: 离线 CRL 文件路径（若不走 fetch 则需提供）
            crl_required: 严格模式 — 没 CRL / CRL 无效一律拒
            crl_algorithm: CRL 用哪种签名算法（取决于 LA 的 signing_default_algorithm）
            online_required: online 模式下，回连失败是否拒启动（默认 False = 走缓存）
        """
        self._license_file_path = Path(license_file_path)
        self._public_key = public_key
        self._mode = mode
        self._heartbeat_base_url = heartbeat_base_url
        self._api_key = api_key
        self._recheck_interval = recheck_interval_seconds
        self._grace_period = grace_period_seconds
        self._state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self._fingerprint_override = fingerprint_override
        self._crl_path = Path(crl_path) if crl_path else None
        self._crl_required = crl_required
        self._crl_algorithm = crl_algorithm
        self._online_required = online_required

        self._stop_event = threading.Event()
        self._recheck_thread: threading.Thread | None = None

    # ─────────────────────────────────────────────────────────
    # 同步入口（业务层启动时调；内部跑事件循环跑 hybrid/online 异步逻辑）
    # ─────────────────────────────────────────────────────────
    def verify_blocking(self, *, now: datetime | None = None) -> VerificationResult:
        try:
            return asyncio.run(self.verify(now=now))
        except RuntimeError as exc:
            # 已在事件循环里（嵌入 async 框架时）—— 调用方应直接 await self.verify()
            raise RuntimeError(
                "verify_blocking() must be called from sync context; use `await verifier.verify()` from async"
            ) from exc

    # ─────────────────────────────────────────────────────────
    # 异步主流程
    # ─────────────────────────────────────────────────────────
    async def verify(self, *, now: datetime | None = None) -> VerificationResult:
        """异步版本，hybrid/online 真正跑 HTTP。"""
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

        # 1. 读 + 解包
        try:
            raw = self._license_file_path.read_bytes()
        except OSError as exc:
            raise VerificationFailed("malformed", f"cannot read license file: {exc}") from exc

        try:
            forge = unpack(raw)
        except ForgeFileError as exc:
            raise VerificationFailed("malformed", str(exc)) from exc

        # 2. 算法分发 + 验签
        try:
            algo_verify = get_algorithm_verifier(forge.metadata.algorithm)
        except ValueError as exc:
            raise VerificationFailed("malformed", str(exc)) from exc

        if not algo_verify(self._public_key, forge.payload_canonical_bytes, forge.signature):
            raise VerificationFailed("signature_invalid", "signature verification failed")

        # 2.5. hybrid / online：先尝试从 LA 拉新 CRL（拉成功就覆盖本地缓存）
        if self._mode != "offline" and self._heartbeat_base_url:
            await self._try_fetch_crl(now=now_utc)

        # 3. CRL 检查
        self._check_crl(forge=forge, now=now_utc)

        # 4. 过期检查
        expires_at = forge.payload.expires_at.astimezone(timezone.utc)
        if expires_at < now_utc:
            if self._grace_period > 0:
                grace_until_ts = expires_at.timestamp() + self._grace_period
                if now_utc.timestamp() <= grace_until_ts:
                    return self._make_result(
                        forge=forge,
                        status="grace_period",
                        valid_until=expires_at,
                        fingerprint=None,
                        reason="in grace period",
                    )
            raise VerificationFailed("expired", f"license expired at {expires_at.isoformat()}")

        # 5. binding 检查
        try:
            policy = get_binding_policy(forge.payload.binding)
        except ValueError as exc:
            raise VerificationFailed("malformed", str(exc)) from exc

        binding_result = policy.check(
            forge=forge,
            state_dir=self._state_dir,
            fingerprint_override=self._fingerprint_override,
        )

        if not binding_result.passed:
            raise VerificationFailed("binding_mismatch", binding_result.reason or "fingerprint mismatch")

        if binding_result.reason and "anomaly" in binding_result.reason:
            return self._make_result(
                forge=forge,
                status="binding_anomaly",
                valid_until=expires_at,
                fingerprint=binding_result.current_fingerprint,
                reason=binding_result.reason,
            )

        # 6. hybrid / online：上报心跳（hybrid 失败不阻断；online 按 online_required 决定）
        heartbeat_result: HeartbeatResult | None = None
        if self._mode != "offline" and self._heartbeat_base_url and self._api_key:
            heartbeat_result = await self._try_heartbeat(
                license_id=forge.payload.license_id,
                fingerprint=binding_result.current_fingerprint,
                now=now_utc,
            )

        # online 模式下，心跳明确告知 revoked 或 anomaly → 服务端权威，按结果处理
        if heartbeat_result is not None:
            if heartbeat_result.license_status == "revoked":
                raise VerificationFailed("revoked", "LA heartbeat reports license revoked")
            if heartbeat_result.multi_env_anomaly:
                return self._make_result(
                    forge=forge,
                    status="binding_anomaly",
                    valid_until=expires_at,
                    fingerprint=binding_result.current_fingerprint,
                    reason="LA detected multi-environment usage",
                )

        return self._make_result(
            forge=forge,
            status="valid",
            valid_until=expires_at,
            fingerprint=binding_result.current_fingerprint,
            reason=binding_result.reason,
        )

    # ─────────────────────────────────────────────────────────
    # HTTP 子流程
    # ─────────────────────────────────────────────────────────
    async def _try_fetch_crl(self, *, now: datetime) -> None:
        """hybrid/online：拉新 CRL 写入本地缓存。

        - 拉成功 → 把 crl_path 指向缓存文件，后续 _check_crl 用新 CRL
        - 拉失败但有本地缓存 → 继续用旧
        - 拉失败且无缓存 → 行为按 crl_required 决定
        """
        if self._heartbeat_base_url is None:
            return
        fetcher = CrlFetcher(
            base_url=self._heartbeat_base_url,
            algorithm=self._crl_algorithm,
            public_key=self._public_key,
            cache_dir=self._state_dir,
        )
        result = await fetcher.fetch(now=now)
        if result.crl_path is not None:
            self._crl_path = result.crl_path

    async def _try_heartbeat(
        self,
        *,
        license_id: str,
        fingerprint: str,
        now: datetime,
    ) -> HeartbeatResult | None:
        """上报心跳。失败行为：
        - hybrid：忽略，按 offline 继续（返回 None）
        - online + online_required=True：抛 VerificationFailed("network_error")
        - online + online_required=False：忽略
        """
        if self._heartbeat_base_url is None or self._api_key is None:
            return None
        client = HeartbeatClient(base_url=self._heartbeat_base_url, api_key=self._api_key)
        try:
            return await client.send(license_id=license_id, fingerprint=fingerprint, now=now)
        except HeartbeatClientError as exc:
            if self._mode == "online" and self._online_required:
                raise VerificationFailed("network_error", f"heartbeat failed: {exc}") from exc
            return None

    # ─────────────────────────────────────────────────────────
    # CRL 本地文件检查（hybrid/online 拉完写入后，最终都走这一处）
    # ─────────────────────────────────────────────────────────
    def _check_crl(self, *, forge: ForgeFile, now: datetime) -> None:
        if self._crl_path is None:
            if self._crl_required:
                raise VerificationFailed(
                    "revoked",
                    "CRL is required by configuration but no CRL file provided",
                )
            return

        try:
            crl_bytes = self._crl_path.read_bytes()
        except OSError as exc:
            if self._crl_required:
                raise VerificationFailed("revoked", f"cannot read CRL: {exc}") from exc
            return

        try:
            crl: CrlFile = verify_and_load_crl(
                crl_bytes=crl_bytes,
                public_key=self._public_key,
                now=now,
            )
        except CrlVerificationError as exc:
            if self._crl_required:
                raise VerificationFailed("revoked", f"CRL invalid: {exc}") from exc
            return

        entry = crl.payload.contains(forge.payload.license_id)
        if entry is not None:
            raise VerificationFailed(
                "revoked",
                f"license revoked at {entry.revoked_at.isoformat()}: {entry.reason or 'no reason'}",
            )

    @staticmethod
    def _make_result(
        *,
        forge: ForgeFile,
        status: VerificationStatus,
        valid_until: datetime | None,
        fingerprint: str | None,
        reason: str | None = None,
    ) -> VerificationResult:
        return VerificationResult(
            status=status,
            license_id=forge.payload.license_id,
            valid_until=valid_until,
            features=forge.payload.features,
            limits=forge.payload.limits,
            fingerprint=fingerprint,
            reason=reason,
        )

    # ─────────────────────────────────────────────────────────
    # 后台周期复查
    # ─────────────────────────────────────────────────────────
    def start_periodic_recheck(
        self,
        *,
        on_invalid: Callable[[VerificationResult | VerificationFailed], None],
    ) -> None:
        """启动后台线程，每隔 recheck_interval_seconds 调一次 verify()。

        license 由有效变为无效时调用 on_invalid 回调。业务层据此进入只读 / 部分禁用 / 计划下线。
        """
        if self._recheck_thread is not None:
            return  # 已在跑

        def _loop() -> None:
            while not self._stop_event.is_set():
                # 等到下次复查时间或被 stop
                if self._stop_event.wait(timeout=self._recheck_interval):
                    return
                try:
                    result = asyncio.run(self.verify())
                except VerificationFailed as exc:
                    on_invalid(exc)
                    continue
                # 非 valid 状态也通知业务层
                if result.status != "valid":
                    on_invalid(result)

        thread = threading.Thread(target=_loop, name="forge-verifier-recheck", daemon=True)
        thread.start()
        self._recheck_thread = thread

    def stop(self) -> None:
        self._stop_event.set()
        if self._recheck_thread is not None:
            self._recheck_thread.join(timeout=5.0)
            self._recheck_thread = None
