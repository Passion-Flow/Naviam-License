#!/usr/bin/env bash
# Forge — 从 backup-keys.sh 产物恢复
#
# 用法：
#   bash restore-keys.sh <forge-backup-<ts>.tar.gz.gpg>
#
# 前置条件：
#   - 目标环境 docker compose 已起（forge-postgres + forge-api healthy）
#   - KEY_MASTER_PASSPHRASE 在 .env 里设的是与备份当时**完全一致**的值
#   - DATABASE_PASSWORD 与备份时一致（用于 pg_restore）
set -euo pipefail

INPUT="${1:?usage: restore-keys.sh <backup.tar.gz[.gpg]>}"
DATABASE_CONTAINER="${DATABASE_CONTAINER:-forge-postgres}"
API_CONTAINER="${API_CONTAINER:-forge-api}"
KEY_STORAGE_LOCAL_PATH="${KEY_STORAGE_LOCAL_PATH:-/var/lib/forge/keys}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[1/5] verify backup file: $INPUT"
test -r "$INPUT"

DECRYPTED="$WORK/forge-backup.tar.gz"
if [[ "$INPUT" == *.gpg ]]; then
    echo "[2/5] decrypting"
    if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
        gpg --batch --yes --output "$DECRYPTED" --passphrase "$BACKUP_PASSPHRASE" --decrypt "$INPUT"
    else
        gpg --batch --yes --output "$DECRYPTED" --decrypt "$INPUT"   # 走 ~/.gnupg keyring
    fi
else
    cp "$INPUT" "$DECRYPTED"
fi

echo "[3/5] extracting"
mkdir -p "$WORK/extracted"
tar -xzf "$DECRYPTED" -C "$WORK/extracted"
test -f "$WORK/extracted/keys.tar.gz"
test -f "$WORK/extracted/forge_main.sql"

echo "[4/5] restoring signing keys into $API_CONTAINER:$KEY_STORAGE_LOCAL_PATH"
docker exec "$API_CONTAINER" sh -c "rm -rf $KEY_STORAGE_LOCAL_PATH/* && mkdir -p $KEY_STORAGE_LOCAL_PATH"
cat "$WORK/extracted/keys.tar.gz" | docker exec -i "$API_CONTAINER" tar -xzf - -C "$KEY_STORAGE_LOCAL_PATH"

echo "[5/5] restoring database"
# CAUTION: this drops + recreates objects from the dump
cat "$WORK/extracted/forge_main.sql" | \
    docker exec -i -e PGPASSWORD="${DATABASE_PASSWORD:?set DATABASE_PASSWORD}" "$DATABASE_CONTAINER" \
    psql -U "${DATABASE_USERNAME:-forge_app}" -d "${DATABASE_DATABASE:-forge_main}" -v ON_ERROR_STOP=1 >/dev/null

echo "OK — restore complete. Restart forge-api to reload key cache:"
echo "    docker compose restart forge-api forge-worker forge-scheduler"
