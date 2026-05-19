#!/usr/bin/env bash
# Forge — TiDB 连通 + bootstrap 业务账号自检
# 用法: bash verify.sh
set -euo pipefail

: "${TIDB_PORT:=14000}"
: "${TIDB_USER:=forge_app}"
: "${TIDB_PASSWORD:?TIDB_PASSWORD required (.env.example)}"
: "${TIDB_DATABASE:=forge_main}"

run_root() {
  # unistore 启动时 root 无密码
  docker exec -i forge-tidb mysql -h 127.0.0.1 -P 4000 -u root --skip-ssl -N -B -e "$1"
}

run_app() {
  docker exec -i forge-tidb mysql -h 127.0.0.1 -P 4000 \
    -u"$TIDB_USER" -p"$TIDB_PASSWORD" "$TIDB_DATABASE" --skip-ssl -N -B -e "$1"
}

echo "[1/5] container healthy?"
docker inspect -f '{{.State.Health.Status}}' forge-tidb

echo "[2/5] bootstrap forge_app + forge_main (idempotent)"
run_root "$(cat $(dirname "$0")/init/01-init-roles.sql)"

echo "[3/5] forge_app SELECT 1"
test "$(run_app 'SELECT 1')" = "1"

echo "[4/5] CREATE / INSERT / DROP TABLE"
run_app "
CREATE TABLE __forge_probe (id INT PRIMARY KEY, payload VARCHAR(32));
INSERT INTO __forge_probe VALUES (1, 'ok');
DROP TABLE __forge_probe;
"

echo "[5/5] TiDB version"
run_app "SELECT VERSION();"

echo "OK — Forge TiDB ready on 127.0.0.1:${TIDB_PORT}/${TIDB_DATABASE}"
