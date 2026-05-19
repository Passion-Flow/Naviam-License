"""多环境占用检测 —— "不可复刻"承诺的运行时层。

业务问题：
- 客户 A 把 license 文件拷给客户 B
- 两个客户的 verifier 上报心跳，指纹不同
- LA 看到同一 license 在 N 个不同指纹上活跃 → 异常

判定策略（保守、可调）：
- 在最近 `window` 时间内出现 > `threshold` 个不同 fingerprint → anomaly
- 默认 window=24h、threshold=1（同一 license 应该只在一个指纹上）
- 容器场景（重建 = 新指纹）会触发；客户应选 binding=none + 把 threshold 调高 / 启 grace_count

后续动作（不在本模块决定，由 admin / 配置触发）：
- 邮件 / Webhook 通知厂商 admin
- 自动加入 CRL（强模式）
- 仅记审计（宽容模式）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.license.heartbeat.collector import HeartbeatCollector


@dataclass(frozen=True, slots=True)
class DetectionVerdict:
    """检测结论。"""

    license_id: str
    anomaly: bool
    distinct_fingerprint_count: int
    threshold: int
    window_seconds: int
    reason: str | None = None


class MultiEnvDetector:
    """配置化的多环境占用检测器。"""

    def __init__(
        self,
        *,
        window: timedelta = timedelta(hours=24),
        threshold: int = 1,
        grace_count: int = 0,
    ) -> None:
        """
        Args:
            window: 检测窗口
            threshold: 允许的不同指纹数上限（含）
            grace_count: 超过 threshold 后的"宽容次数"——常用于容器场景，
                         允许偶尔重建容器；同一窗口内累计超 grace_count 才算 anomaly
        """
        if window <= timedelta(0):
            raise ValueError("window must be positive")
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        if grace_count < 0:
            raise ValueError("grace_count must be >= 0")
        self._window = window
        self._threshold = threshold
        self._grace_count = grace_count

    async def evaluate(
        self,
        license_id: str,
        *,
        collector: HeartbeatCollector,
        now: datetime | None = None,
    ) -> DetectionVerdict:
        fingerprints = await collector.recent_fingerprints(license_id, window=self._window, now=now)
        n = len(fingerprints)
        allowed = self._threshold + self._grace_count
        if n > allowed:
            return DetectionVerdict(
                license_id=license_id,
                anomaly=True,
                distinct_fingerprint_count=n,
                threshold=self._threshold,
                window_seconds=int(self._window.total_seconds()),
                reason=(
                    f"observed {n} distinct fingerprints in last {self._window} "
                    f"(allowed {allowed}, threshold={self._threshold}, grace={self._grace_count})"
                ),
            )
        return DetectionVerdict(
            license_id=license_id,
            anomaly=False,
            distinct_fingerprint_count=n,
            threshold=self._threshold,
            window_seconds=int(self._window.total_seconds()),
        )
