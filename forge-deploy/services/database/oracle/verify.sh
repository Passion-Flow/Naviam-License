#!/usr/bin/env bash
# Forge — Oracle XE 连通 + 权限自检
# 用法: bash verify.sh
set -euo pipefail

: "${ORACLE_PORT:=11521}"
: "${ORACLE_USER:=forge_app}"
: "${ORACLE_PASSWORD:?ORACLE_PASSWORD required}"
: "${ORACLE_DATABASE:=FORGEPDB1}"

probe() {
  docker exec -i forge-oracle sqlplus -S \
    "${ORACLE_USER}/${ORACLE_PASSWORD}@//localhost:1521/${ORACLE_DATABASE}" <<EOF
SET HEAD OFF FEEDBACK OFF PAGESIZE 0
$1
EXIT
EOF
}

echo "[1/3] container healthy?"
docker inspect -f '{{.State.Health.Status}}' forge-oracle

echo "[2/3] SELECT 1 FROM DUAL"
out=$(probe "SELECT 1 FROM dual;")
echo "$out" | tr -d '[:space:]' | grep -q '^1$'

echo "[3/3] CREATE / INSERT / DROP TABLE"
probe "
CREATE TABLE __forge_probe (id NUMBER PRIMARY KEY, payload VARCHAR2(32));
INSERT INTO __forge_probe VALUES (1, 'ok');
COMMIT;
DROP TABLE __forge_probe PURGE;
"

echo "OK — Forge Oracle ready on 127.0.0.1:${ORACLE_PORT}/${ORACLE_DATABASE}"
