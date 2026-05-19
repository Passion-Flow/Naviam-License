#!/usr/bin/env bash
# Forge — 备份签名密钥 + 数据库
#
# 用法：
#   bash backup-keys.sh [OUTPUT_DIR]
#
# 行为：
#   1. tar 打包 forge-api 容器内 ${KEY_STORAGE_LOCAL_PATH}（默认 /var/lib/forge/keys）
#   2. pg_dump 整个 forge_main 数据库
#   3. 用 BACKUP_GPG_RECIPIENT 公钥加密（推荐）或 BACKUP_PASSPHRASE 对称加密
#   4. 写到 OUTPUT_DIR/forge-backup-<UTC-ISO>.tar.gz.gpg
#
# ⚠️ 至少备份 KEY_MASTER_PASSPHRASE 本身（不在备份里，否则等于没加密）。
#    建议把 KEY_MASTER_PASSPHRASE 单独放保险柜 / Vault / HSM。
set -euo pipefail

OUTPUT_DIR="${1:-./forge-backups}"
COMPOSE_DIR="${COMPOSE_DIR:-../docker}"
DATABASE_CONTAINER="${DATABASE_CONTAINER:-forge-postgres}"
API_CONTAINER="${API_CONTAINER:-forge-api}"
KEY_STORAGE_LOCAL_PATH="${KEY_STORAGE_LOCAL_PATH:-/var/lib/forge/keys}"

mkdir -p "$OUTPUT_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[1/4] dumping signing keys from $API_CONTAINER:$KEY_STORAGE_LOCAL_PATH"
docker exec "$API_CONTAINER" tar -czf - -C "$KEY_STORAGE_LOCAL_PATH" . > "$WORK/keys.tar.gz"

echo "[2/4] dumping database"
docker exec -e PGPASSWORD="${DATABASE_PASSWORD:?set DATABASE_PASSWORD}" \
    "$DATABASE_CONTAINER" \
    pg_dump -U "${DATABASE_USERNAME:-forge_app}" -d "${DATABASE_DATABASE:-forge_main}" \
            --no-owner --clean --if-exists \
    > "$WORK/forge_main.sql"

echo "[3/4] bundling"
cp "$WORK/keys.tar.gz" "$WORK/forge_main.sql" "$OUTPUT_DIR/" 2>/dev/null || true
tar -czf "$WORK/forge-backup-$TS.tar.gz" -C "$WORK" keys.tar.gz forge_main.sql

echo "[4/4] encrypting"
OUT="$OUTPUT_DIR/forge-backup-$TS.tar.gz.gpg"
if [ -n "${BACKUP_GPG_RECIPIENT:-}" ]; then
    gpg --batch --yes --output "$OUT" --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
        "$WORK/forge-backup-$TS.tar.gz"
elif [ -n "${BACKUP_PASSPHRASE:-}" ]; then
    gpg --batch --yes --output "$OUT" --symmetric --cipher-algo AES256 \
        --passphrase "$BACKUP_PASSPHRASE" "$WORK/forge-backup-$TS.tar.gz"
else
    echo "WARN: neither BACKUP_GPG_RECIPIENT nor BACKUP_PASSPHRASE set; storing unencrypted!" >&2
    cp "$WORK/forge-backup-$TS.tar.gz" "${OUT%.gpg}"
    OUT="${OUT%.gpg}"
fi

# 容量 + 校验和
SIZE=$(du -h "$OUT" | cut -f1)
SHA=$(shasum -a 256 "$OUT" | cut -d' ' -f1)

echo "OK — $OUT ($SIZE, sha256=$SHA)"
echo
echo "⚠️ Reminder: also store KEY_MASTER_PASSPHRASE in a separate secret manager."
echo "   Without it, the encrypted signing keys inside this backup are useless."
