"""高级签发 helper —— 把 issue_license 接上 KeyStorage。

调用方一行就能签发：
    issued = await issue_license_with_storage(
        storage=get_key_storage(),
        req=IssueLicenseRequest(...),
    )

KeyStorage 选哪把密钥的策略：
- 默认：找该 algorithm 下 status==active 的最新一把
- 也可以传 key_id 显式指定（如签发"补刀"老 license）
"""
from __future__ import annotations

from app.core.key_storage import KeyStorage
from app.core.license.issuer.issue import IssuedLicense, IssueLicenseRequest, issue_license


class NoActiveKeyError(Exception):
    """无可用 active 密钥时抛。运维需要先 generate_and_save_signing_key。"""


async def find_active_key_id(storage: KeyStorage, algorithm: str) -> str:
    """挑选当前算法的 active 密钥。若有多把 active，挑 created_at 最新一把。"""
    candidates = []
    for key_id in await storage.list_ids():
        rec = await storage.load(key_id)
        if rec.algorithm == algorithm and rec.status == "active":
            candidates.append(rec)
    if not candidates:
        raise NoActiveKeyError(f"no active key for algorithm={algorithm}")
    candidates.sort(key=lambda r: r.created_at, reverse=True)
    return candidates[0].key_id


async def issue_license_with_storage(
    *,
    storage: KeyStorage,
    req: IssueLicenseRequest,
    key_id: str | None = None,
) -> IssuedLicense:
    """从 KeyStorage 取（解密后的）私钥，签发 license。

    私钥仅在本函数栈内短暂存在，**不外泄**。
    """
    chosen_key_id = key_id or await find_active_key_id(storage, req.algorithm)
    record = await storage.load(chosen_key_id)
    if record.status == "revoked":
        raise NoActiveKeyError(f"key {chosen_key_id} is revoked; refuse to sign")

    return issue_license(
        req,
        private_key=record.private_key,
        key_id=record.key_id,
    )
