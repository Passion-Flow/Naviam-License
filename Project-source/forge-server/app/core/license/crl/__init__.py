"""CRL（吊销列表）—— 离线/在线两用的 license 撤销机制。

数据流：
1. LA admin 把某 license 加入 CRL（带 reason + revoked_at）
2. LA Manager 周期性（或触发）生成新 CRL 文件，用当前 active 签名密钥签
3. CRL 分发：
   - online 模式：Verifier 拉 GET /api/v1/revocation-list/<algorithm>.crl
   - offline 模式：客户接收 signed CRL 文件，拷到 Verifier 状态目录
4. Verifier 在 verify_blocking 时检查 license_id 是否在已加载 CRL 中

CRL 文件即"小型 .forge"：tar 包，payload 是 RevocationListPayload，签名同样用 LA 的签名引擎。
"""
from app.core.license.crl.format import (
    CRL_FORMAT_VERSION,
    CrlFile,
    CrlFileError,
    RevocationEntry,
    RevocationListPayload,
    pack_crl,
    unpack_crl,
)
from app.core.license.crl.manager import (
    CrlManager,
    InMemoryRevocationStore,
    RevocationStore,
)

__all__ = [
    "CRL_FORMAT_VERSION",
    "CrlFile",
    "CrlFileError",
    "CrlManager",
    "InMemoryRevocationStore",
    "RevocationEntry",
    "RevocationListPayload",
    "RevocationStore",
    "pack_crl",
    "unpack_crl",
]
