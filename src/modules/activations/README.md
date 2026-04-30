# activations 模块

## 职责

- Cloud ID 协议（v1）解码与校验。
- Activation Code 协议（v1）编码与解码（Console 输出 / SDK 解码）。
- 心跳入站：限速 + 校验 + 持久化。
- 在线签发出站：mTLS 调用产品实例激活回调。

## 文件

- `cloud_id_codec.py`：CBOR + base32 + 校验位。
- `activation_code_codec.py`：License 文件 + base32 + 校验位。
- `heartbeat.py`：入站校验、状态推断、记录 `activations_heartbeat`。
- `online.py`：mTLS 客户端、产品实例公钥指纹核对。

## 关键约束

- Cloud ID 解码失败 / 校验位失败 -> 立即拒绝 + 审计。
- created_at 与服务器时间偏差超过 ±10 分钟 -> 拒绝（防止时钟攻击）。
- 心跳频率受限速保护；高于上限的心跳直接拒绝。
- 在线激活的产品实例公钥指纹必须与 Cloud ID 中一致。

## 不做

- 不做产品端 UI（属于 SDK / 客户产品）。
- 不做硬件指纹采集（产品端自行采集，平台只接收 HMAC）。
