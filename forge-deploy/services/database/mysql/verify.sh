#!/usr/bin/env bash
# Forge — MySQL 连通 + 基本权限自检
# 用法: bash verify.sh
set -euo pipefail

: "${MYSQL_PORT:=13306}"
: "${MYSQL_USER:=forge_app}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD required (see .env.example)}"
: "${MYSQL_DATABASE:=forge_main}"

HOST="127.0.0.1"

run() {
  docker exec -i forge-mysql mysql \
    -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -N -B -e "$1"
}

echo "[1/4] container running?"
docker inspect -f '{{.State.Health.Status}}' forge-mysql

echo "[2/4] SELECT 1"
test "$(run 'SELECT 1')" = "1"

echo "[3/4] CREATE / INSERT / DROP TEMP TABLE"
run "
CREATE TEMPORARY TABLE __forge_probe (id INT PRIMARY KEY, payload VARCHAR(32));
INSERT INTO __forge_probe VALUES (1, 'ok');
SELECT COUNT(*) FROM __forge_probe;
"

echo "[4/4] charset = utf8mb4"
test "$(run "SHOW VARIABLES LIKE 'character_set_database'" | awk '{print $2}')" = "utf8mb4"

echo "OK — Forge MySQL ready on ${HOST}:${MYSQL_PORT}"
