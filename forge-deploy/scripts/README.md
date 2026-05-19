# forge-deploy/scripts

部署运维脚本。所有脚本可独立于 docker / helm 模式执行，**变量从 env 注入，不硬编码**。

## 备份 + 恢复

| 脚本 | 用途 |
|------|------|
| `backup-keys.sh` | dump 签名密钥目录 + `pg_dump` → GPG 加密 tarball |
| `restore-keys.sh` | 反向：解密 → 解 tar → 写回容器 + `psql` 恢复 DB |

### 备份（每日定时跑）

```bash
export DATABASE_PASSWORD='...'                  # 与 forge-server/.env 一致
export BACKUP_GPG_RECIPIENT='ops@your-co.com'   # 推荐：非对称加密
# 或：export BACKUP_PASSPHRASE='高熵口令'        # 对称加密

bash forge-deploy/scripts/backup-keys.sh /var/backups/forge
```

cron：

```cron
15 2 * * * /opt/forge/scripts/backup-keys.sh /var/backups/forge >> /var/log/forge-backup.log 2>&1
```

### 恢复

```bash
export DATABASE_PASSWORD='...'
export BACKUP_PASSPHRASE='高熵口令'                # 对称加密时

bash forge-deploy/scripts/restore-keys.sh /var/backups/forge/forge-backup-20260518T020000Z.tar.gz.gpg

# 完事重启 backend
docker compose restart forge-api forge-worker forge-scheduler
```

## ⚠️ 关键注意事项

1. `KEY_MASTER_PASSPHRASE` **不在备份里**。它必须单独保存（Vault / HSM / 公司保险柜）。
   备份里的 `keys/` 目录文件用此口令加密。备份 + 口令两者都丢 = 业务全废。
2. 备份文件 = **所有签发能力**。务必：
   - 异地存储（S3 跨 region replication / 离线介质）
   - 加密传输（GPG 已加，但也别用 HTTP 上传）
   - 定期演练 restore（每季度真跑一次）
3. `pg_dump` 用 `--clean --if-exists` —— 恢复时会先 drop schema 再重建。**不要往生产 DB 上 restore**，先在备机演练。

## 健康检查

`bash health-check.sh` —— TODO（Round AN）：综合检查 forge-api / DB / Redis / object-storage / 签名密钥 可读性。
