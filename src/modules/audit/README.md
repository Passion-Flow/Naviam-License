# audit 模块

## 职责

- 哈希链审计：`prev_hash + canonical(payload) -> hash`，每条 Ed25519 签名。
- 写入：所有业务模块通过 `audit.append(event)` 写入；事务边界与业务事务一致。
- 查询：按时间倒序、按 action 过滤。
- 完整性：启动时全链校验；任意失配 -> 拒绝写新审计 + 高优告警。
- 导出：签名压缩包（data.jsonl + chain.json + pubkey.pem + signature.bin）。

## 关键文件（阶段 4 / 7 实现）

- `models.py`：`Event`（含 prev_hash / hash / signature / signature_kid / ts / actor_* / action / target_* / payload）。
- `services.py`：`append`、`integrity_check`、`export`。
- `chain.py`：哈希计算、规范化字节、链尾缓存。
- `views.py`：列表 / 完整性 / 导出。

## 安全要求

- Genesis 记录 `prev_hash = b'\\x00' * 32` 由初始化迁移写入。
- 永远不删除审计记录（合规需要）。
- `hash` 列加 `UNIQUE` 防止重放。

## 不做

- 不做日志聚合（外部 Loki / OTEL 承担）。
- 不做用户行为画像。
