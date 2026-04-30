# notifications 模块

## 职责

- 通道：邮件、Webhook（HMAC-SHA256 签名）。
- Outbox：持久化 + 重试 + 退避。
- 主题：license.expiring / license.revoked / license.renewed / system.alert。

## 关键文件（阶段 7 实现）

- `models.py`：`Channel`、`Outbox`。
- `services.py`：`publish(channel_id, topic, payload)`、`flush_outbox()`。
- `senders/email.py`、`senders/webhook.py`。

## 安全要求

- Webhook 出站 SSRF 防护（私网拒绝 + DNS 解析后再校验目标 IP）。
- 信封内容禁止包含密钥 / passphrase。
- Webhook header `X-License-Signature: t=<unix>,v1=<hex>`，接收端 constant-time 比较。

## 不做

- 不做客户端推送（与本平台无关）。
- 不做大规模并发队列（如需要触发 ADR + worker 镜像）。
