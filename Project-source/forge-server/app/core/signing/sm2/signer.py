"""SM2 签名实现（国密，信创场景）。

依赖：gmssl（纯 Python，无编译依赖；私有化交付友好）

密钥编码（自定义紧凑格式）：
- 私钥：64 hex 字符 = 32 字节（curve order 内整数的 hex）
- 公钥：128 hex 字符 = 64 字节（X || Y 拼接，未压缩）

签名：
- 调 `sign_with_sm3`：库内部先用 SM2 用户身份信息 (ZA) + 消息 计算 SM3 摘要，再签
- 默认用户 ID = "1234567812345678"（GB/T 32918 推荐缺省值）
- 输出 hex 签名字符串

二进制序列化：本签名引擎把 hex 字符串 encode 为 ASCII bytes 落到 .forge signature.bin。
"""
from __future__ import annotations

import secrets
import uuid

from gmssl import sm2

from app.core.signing.interface import KeyPair, Signature

# SM2 椭圆曲线阶 n（gmssl 默认）
SM2_CURVE_ORDER = int(
    "FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16
)


def _generate_keypair_hex() -> tuple[str, str]:
    """返回 (private_hex_64, public_hex_128)。

    实现细节：私钥 = 随机整数 ∈ [1, n-1]；公钥 = privateKey * G。
    用 gmssl 库的 `_kg`（标量乘法）；这是它对外稳定的内部方法。
    """
    # 随机私钥
    d = secrets.randbelow(SM2_CURVE_ORDER - 1) + 1
    priv_hex = format(d, "064x")
    # 用一份临时 instance 借调 _kg 做 k*G
    helper = sm2.CryptSM2(private_key=priv_hex, public_key="00" * 64)
    pub_hex = helper._kg(d, sm2.default_ecc_table["g"])
    if len(pub_hex) != 128:
        raise RuntimeError(f"unexpected SM2 public key length: {len(pub_hex)}")
    return priv_hex, pub_hex


class Sm2Signer:
    algorithm = "sm2"

    def generate_keypair(self) -> KeyPair:
        priv_hex, pub_hex = _generate_keypair_hex()
        return KeyPair(
            algorithm=self.algorithm,
            key_id=self._new_key_id(),
            public_key=pub_hex.encode("ascii"),
            private_key=priv_hex.encode("ascii"),
        )

    def sign(self, *, private_key: bytes, key_id: str, payload: bytes) -> Signature:
        priv_hex = private_key.decode("ascii")
        # 推导公钥（避免持久化两份；签名只用私钥）
        d = int(priv_hex, 16)
        helper = sm2.CryptSM2(private_key=priv_hex, public_key="00" * 64)
        pub_hex = helper._kg(d, sm2.default_ecc_table["g"])
        signer = sm2.CryptSM2(private_key=priv_hex, public_key=pub_hex)
        # random_hex_str=None → gmssl 内部随机
        sig_hex = signer.sign_with_sm3(payload, random_hex_str=None)
        return Signature(algorithm=self.algorithm, key_id=key_id, signature=sig_hex.encode("ascii"))

    def verify(self, *, public_key: bytes, payload: bytes, signature: bytes) -> bool:
        try:
            pub_hex = public_key.decode("ascii")
            sig_hex = signature.decode("ascii")
        except UnicodeDecodeError:
            return False
        # 验签不需要私钥；占位 "00"*32 即可（gmssl 接口要求两个 hex 字段）
        verifier = sm2.CryptSM2(private_key="00" * 32, public_key=pub_hex)
        return bool(verifier.verify_with_sm3(sig_hex, payload))

    def _new_key_id(self) -> str:
        return f"sm2-{uuid.uuid4().hex[:12]}"
