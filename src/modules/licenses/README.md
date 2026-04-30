# licenses 模块

## 职责

本项目核心。承担：

- 签发：解析 Cloud ID -> 创建 License -> Ed25519 签名 -> 输出 Activation Code（离线）或推送（在线）。
- 续期：B2 同实例覆盖；B3 在线自动续期。
- 撤销：C1 在线立即生效；离线记录 + 通知。
- 状态机：`draft -> issued -> active -> {expired -> grace -> sunset, revoked -> sunset}`。

## 字段

`license_id, product_id, customer_id, cloud_id_binding, cloud_id_text, hardware_fp_hash, instance_pubkey, status, issued_at, not_before, expires_at, grace_until, signature, signature_algo, signature_kid, payload_canonical, notes, issued_by`。

## 关键约束

- 任何状态变化必须通过 services.<action>，不允许视图层直接改 status。
- 任何写操作必须写审计哈希链。
- 签名永远在 API 进程内，永远不出进程。
- payload 规范化使用 CBOR 字典字段排序；不允许使用 JSON（避免空白 / 顺序差异）。

## 不做

- 不做 feature 颗粒度。
- 不做财务计费 / 续费触发邮件（通知由 notifications 模块统一负责）。

## 上下游

- 上游：customers、products、activations。
- 下游：activations（Cloud ID 解码）、audit（写链）、notifications（撤销 / 续期通知）。
