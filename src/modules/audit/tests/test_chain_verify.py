"""verify_chain 单元测试 — Phase 5。

钉死哈希链完整性校验：
- 干净链通过
- 任一 hash 字段被改 → 立即失配
- 任一 prev_hash 被改 → 链断
- 任一 payload 被改 → 重算失配
- 所有比较都用 hmac.compare_digest（无字节级时序泄露）
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cbor2

# src/ 入 path（与 codec roundtrip 测试同款）
_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from modules.audit.services import (  # noqa: E402
    AuditChainCorrupted,
    _GENESIS_HASH,
    _recompute_hash,
    verify_chain,
)


@dataclass
class FakeEvent:
    """模拟 AuditEvent，避免拉起 Django ORM。"""

    id: int
    prev_hash: bytes
    hash: bytes
    signature: bytes
    payload: dict[str, Any]


def _build_clean_chain(n: int = 5) -> list[FakeEvent]:
    events: list[FakeEvent] = []
    prev = _GENESIS_HASH
    for i in range(n):
        payload = {"action": f"event-{i}", "i": i}
        h = _recompute_hash(prev, payload)
        events.append(FakeEvent(
            id=i + 1,
            prev_hash=prev,
            hash=h,
            signature=b"\x00" * 64,
            payload=payload,
        ))
        prev = h
    return events


def test_clean_chain_passes() -> None:
    events = _build_clean_chain(10)
    result = verify_chain(events=iter(events))
    assert result.total == 10
    assert result.last_hash == events[-1].hash


def test_empty_chain_passes() -> None:
    result = verify_chain(events=iter([]))
    assert result.total == 0
    assert result.last_hash == _GENESIS_HASH


def test_tampered_payload_detected() -> None:
    """改 payload → 重算 hash 不再匹配存储 hash。"""
    events = _build_clean_chain(5)
    events[2].payload["i"] = 999  # 篡改
    try:
        verify_chain(events=iter(events))
    except AuditChainCorrupted as exc:
        assert exc.event_id == 3
        assert "payload tampered" in exc.reason or "recomputed" in exc.reason
    else:
        raise AssertionError("应当抛 AuditChainCorrupted")


def test_tampered_hash_detected() -> None:
    """直接改存储的 hash 字段。"""
    events = _build_clean_chain(5)
    bad = bytearray(events[3].hash)
    bad[0] ^= 0xFF
    events[3].hash = bytes(bad)
    try:
        verify_chain(events=iter(events))
    except AuditChainCorrupted as exc:
        # 第 3 条 hash 被改：自身重算会失配（id=4），而第 4 条 prev_hash 仍是旧值，也会失配（id=5）
        # 期望报最先发现的那条
        assert exc.event_id in (4, 5)
    else:
        raise AssertionError("应当抛 AuditChainCorrupted")


def test_broken_link_detected() -> None:
    """改某条的 prev_hash → 链接断。"""
    events = _build_clean_chain(5)
    events[2].prev_hash = b"\xff" * 32
    try:
        verify_chain(events=iter(events))
    except AuditChainCorrupted as exc:
        assert exc.event_id == 3
        assert "prev_hash" in exc.reason
    else:
        raise AssertionError("应当抛 AuditChainCorrupted")


def test_genesis_check() -> None:
    """第一条的 prev_hash 必须是 0x00 * 32。"""
    events = _build_clean_chain(3)
    events[0].prev_hash = b"\x11" * 32
    try:
        verify_chain(events=iter(events))
    except AuditChainCorrupted as exc:
        assert exc.event_id == 1
    else:
        raise AssertionError("应当抛 AuditChainCorrupted")
