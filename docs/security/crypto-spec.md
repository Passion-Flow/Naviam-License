# 加密与协议规范

本文件定义本项目使用的加密原语、Cloud ID 协议、Activation Code 协议、审计哈希链与密钥管理接口。所有实现必须使用 `cryptography` 库；禁止自研。

## 1. 原语

| 用途 | 算法 | 库 |
|---|---|---|
| 数字签名 | Ed25519 | `cryptography.hazmat.primitives.asymmetric.ed25519` |
| 密钥协商 | X25519（V2 在线模式互信） | `cryptography.hazmat.primitives.asymmetric.x25519` |
| 摘要 | SHA-256 | `cryptography.hazmat.primitives.hashes.SHA256()` |
| 密钥派生 | HKDF-SHA256 | `cryptography.hazmat.primitives.kdf.hkdf` |
| 对称加密 | XChaCha20-Poly1305 / AES-256-GCM（任择其一） | `cryptography.hazmat.primitives.ciphers.aead` |
| 密码哈希 | Argon2id | `argon2-cffi` |
| 哈希比较 | constant-time | `hmac.compare_digest` |

## 2. 厂商签发密钥

- 算法：Ed25519。
- 长度：标准 32 字节私钥 + 32 字节公钥。
- 标识：`signature_kid` 字符串，多代号同时存在；不删除旧 kid（避免历史 License 验签失败）。
- 存储：A 方案 = `age` / `sops` 加密文件 + passphrase；启动时一次性解密到进程内存。
- 接口：`IKeySigner`（详见 `src/contracts/signing.py`）。

```python
class IKeySigner(Protocol):
    def kid(self) -> str: ...
    def public_key(self) -> bytes: ...     # 32 字节
    def sign(self, payload: bytes) -> bytes: ...   # 64 字节
```

## 3. Cloud ID 协议（v1）

Cloud ID 由产品端 SDK 在客户机生成，包含「产品 + 实例 + 实例公钥指纹 + 硬件指纹 + 协议版本」。

字段（CBOR / 规范化字节序列）：

```text
schema_version: u16     // = 1
product_code:   bstr    // 产品代号；如 "default"
instance_id:    bstr    // SDK 启动时生成的稳定 ID（持久化到 SDK 数据目录）
instance_pubkey_fp: bstr // X25519/ed25519 实例公钥的 SHA-256 截短前 16 字节
hardware_fp:    bstr    // 客户机器特征的 HMAC-SHA256，详见 §3.1
nonce:          bstr    // 16 字节随机
created_at:     u64     // unix-seconds（产品端时间）
```

编码：

```text
canonical_bytes = CBOR(map_above)
checksum = SHA-256(canonical_bytes)[:4]
encoded = base32(canonical_bytes || checksum)
display = group(encoded, 6)  // 每 6 字符插入 '-'，便于人工复制
```

校验：

- 解码后必须能 CBOR 解包。
- 校验 `checksum` 一致。
- `created_at` 与服务器时间偏差超过 ±10 分钟 -> 拒绝（防止时钟攻击）。
- `instance_pubkey_fp` 长度 = 16；`hardware_fp` 长度 = 32。

### 3.1 hardware_fp 计算

产品端在 SDK 初始化时收集：

```text
inputs = [
  machine_id (Linux: /etc/machine-id; Mac: IOPlatformUUID; Windows: SMBIOS UUID),
  cpu_model_normalized,
  motherboard_serial_or_uuid,
  primary_disk_serial,
]
```

`hardware_fp = HMAC-SHA256(key=instance_pubkey, msg=normalized_inputs)`。

不存原始硬件信息；仅存 HMAC 结果。

## 4. License 内容

```text
license = {
  schema_version:  u16 = 1,
  license_id:      str (uuid v4),
  product_code:    str,
  customer_id:     str (uuid v4),
  cloud_id_binding: bstr,        // 编码同 §3 但无 checksum
  not_before:      u64,
  not_after:       u64,
  grace_seconds:   u32,           // 默认 30 天
  notes:           str (<=1024)?,
  signature_algo:  str = "ed25519",
  signature_kid:   str,
}
payload_canonical = CBOR(license_without_signature)
signature = ed25519.sign(signing_key, payload_canonical)
```

License 文件格式：

```text
license_file = base64url( CBOR( {
  v: 1,
  payload: payload_canonical,
  sig: signature,
  kid: signature_kid,
} ) )
```

SDK 校验：

1. base64url 解码 + CBOR 解包。
2. 通过 `kid` 在 SDK 内置公钥集中找到公钥（V1 仅一个）。
3. `ed25519.verify(public_key, signature, payload)`。
4. 解包 `payload` 得到 license 字段。
5. 校验 `cloud_id_binding` 与本机 Cloud ID 一致（除 nonce 与 created_at 外字段全相同）。
6. 校验 `not_before <= now <= not_after + grace_seconds`。

## 5. Activation Code

Activation Code 是 License 文件的「人类可读版本」，用于离线流程。

```text
activation_code = group( base32( CBOR( {
  v: 1,
  license_file: license_file_bytes,
  checksum: SHA-256(license_file_bytes)[:4],
} ) ), 6 )
```

校验：

- 解码 + CBOR 解包 + 校验 checksum。
- 验签使用 §4 同步流程。

## 6. 审计哈希链

```text
record = {
  ts, actor_id, actor_kind, actor_ip, action, target_kind, target_id,
  request_id, payload (jsonb-canonical),
}
prev_hash = chain.tail.hash    // 链头 prev_hash = 0x00 * 32
canonical = CBOR(record)
hash = SHA-256(prev_hash || canonical)
signature = ed25519.sign(audit_key, hash)
```

- `audit_key` 与签发私钥分离，但同样用 A 方案存储。
- 启动时全链 hash 校验：从最早到最新顺序计算并与表中 `hash` 字段比对。
- 任何记录被改动会导致后续所有记录的 hash 失配。
- 导出包：`data.jsonl`（每行一条记录） + `chain.json`（链摘要） + `pubkey.pem` + `signature.bin`（对 chain.json 整体签名）。

## 7. Webhook 签名

```text
header X-License-Signature: t=<unix>,v1=<hex>
v1 = HMAC-SHA256(secret, f"{t}.{body}")
```

接收方按 `secret` 复算并 constant-time 比较；`t` 与当前时间偏差超过 ±5 分钟拒绝。

## 8. 密钥轮换

- 厂商公钥轮换：在 SDK 中支持「已知公钥集合」；新 kid 加入，旧 kid 保留。
- 计划：每 12 个月主动轮换；事件触发立即轮换。
- 轮换流程：生成新密钥 -> 同时配置旧 + 新 -> 新签发使用新 kid -> 旧 License 自然到期后下线旧 kid。
- 文档：每次轮换写入 ADR + 审计记录。

## 9. 失败处理

- 签名校验失败：拒绝 + 审计 + 用户提示「License 不合法」。
- Cloud ID 解码失败：拒绝 + 提示「Cloud ID 损坏，请重新复制」。
- Activation Code 校验位失败：拒绝 + 提示「校验位失败，请确认完整复制」。
- 审计链 hash 失配：API 立即进入「拒绝写新审计」状态 + 强烈告警；人工介入。

## 10. 不做

- 不在客户端做密钥协商以「绕过」厂商签名（架构上不需要）。
- 不实现 License 加密（机密性不在威胁面，完整性才是）。
- 不引入 zero-knowledge / blockchain；增加复杂度但不解决核心问题。
- 不做密钥分割多签（V1 只有一个签发者；V2 视合规要求评估）。
