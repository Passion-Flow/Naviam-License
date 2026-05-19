"""SM2 验签（国密）。

依赖：gmssl（纯 Python）

公钥格式：128 hex 字符（X || Y 拼接，ASCII 编码后落到 .forge 的 signature/key 字节流）
签名格式：hex 字符串（gmssl `sign_with_sm3` 输出）
"""
from __future__ import annotations

from gmssl import sm2


def verify(public_key: bytes, payload: bytes, signature: bytes) -> bool:
    try:
        pub_hex = public_key.decode("ascii")
        sig_hex = signature.decode("ascii")
    except UnicodeDecodeError:
        return False

    # 公钥 / 签名长度初步校验
    if len(pub_hex) != 128:
        return False
    if not sig_hex:
        return False

    try:
        # 验签不需要私钥；用占位 32 字节零作为 private_key
        verifier = sm2.CryptSM2(private_key="00" * 32, public_key=pub_hex)
        return bool(verifier.verify_with_sm3(sig_hex, payload))
    except Exception:
        # gmssl 在某些畸形输入下会抛 ValueError / IndexError
        return False
