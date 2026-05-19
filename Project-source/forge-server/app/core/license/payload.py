"""License payload — 业务字段的权威 Pydantic 模型。

序列化为 JSON 后作为 .forge 文件里的 payload.json。
**所有字段不接受默认值的字面值**——通过 settings / 显式构造传入，无硬编码原则。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 协议版本——签发与验签都看这一字段决定如何解释 payload
PROTOCOL_VERSION = "1.0"

VerificationMode = Literal["offline", "hybrid", "online"]
Scope = Literal["customer_x_product", "customer_bundle", "instance"]
SigningAlgorithm = Literal["ed25519", "rsa2048", "rsa4096", "sm2"]
BindingMode = Literal["none", "soft", "hard"]


class LicensePayload(BaseModel):
    """`.forge` 文件中 payload.json 的内容。

    序列化规则（重要）：
    - 用 `model_dump_json(sort_keys=True, separators=(",", ":"))` 生成规范化字节流
    - 签名/验签都对**规范化后的字节流**进行操作，避免空格 / key 顺序差异导致验签失败
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: str = Field(default=PROTOCOL_VERSION, description="License 协议版本（SemVer）")

    # 唯一标识
    license_id: str = Field(description="License 唯一 ID（uuid 推荐）")
    customer_id: str = Field(description="客户实体 ID")
    product_id: str = Field(description="产品 ID")

    # 业务参数
    mode: VerificationMode = Field(description="验证模式：offline / hybrid / online")
    scope: Scope = Field(description="颗粒度：customer_x_product / customer_bundle / instance")
    binding: BindingMode = Field(description="绑定模式：none / soft / hard")
    bound_fingerprint: str | None = Field(
        default=None,
        description="仅 binding=='hard' 时必填，签发时硬绑的部署指纹",
    )

    # 时间窗口（ISO 8601 UTC）
    issued_at: datetime = Field(description="签发时间")
    expires_at: datetime = Field(description="过期时间")

    # 功能与配额
    features: dict[str, object] = Field(
        default_factory=dict,
        description="启用的 features 映射（业务字段，由产品定义解释）",
    )
    limits: dict[str, object] = Field(
        default_factory=dict,
        description="配额：max_users / max_instances / max_cores 等",
    )

    def canonical_bytes(self) -> bytes:
        """生成可签名的规范化字节流。

        规则（一旦定下，**不可**修改，否则旧 license 全部失效）：
        - sort_keys=True：键按字典序
        - separators=(",", ":")：去掉所有多余空格
        - ensure_ascii=False：非 ASCII 字符按 UTF-8 输出，不转 \\uXXXX
        """
        data = self.model_dump(mode="json")
        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def from_canonical_bytes(cls, data: bytes) -> "LicensePayload":
        """从规范化字节流恢复 payload。"""
        return cls.model_validate_json(data.decode("utf-8"))
