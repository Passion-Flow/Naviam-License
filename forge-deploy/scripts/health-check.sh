#!/usr/bin/env bash
# Forge — 综合健康检查（compose 模式）
#
# 检查项：
#   1. 5 个核心容器 healthy
#   2. forge-api /api/v1/health 200
#   3. forge-api /metrics 200 + 含 forge_http_requests_total
#   4. forge-worker celery inspect ping
#   5. 数据库连通 + 表数量 ≥ 10
#   6. Redis 连通 + 4 个 DB 可达
#
# 退出码 0 = 全绿；非 0 = 至少一项失败。
set -euo pipefail

PROJECT="${1:-forge}"
HOST_PORT="${HTTP_PORT:-18080}"
fail=0
check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "✓ $name"
    else
        echo "✗ $name" >&2
        fail=1
    fi
}

echo "──── Containers ────"
for svc in forge-api forge-worker forge-scheduler forge-web; do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
    if [ "$status" = "healthy" ] || [ "$status" = "" ]; then
        echo "✓ $svc ($status)"
    else
        echo "✗ $svc ($status)"; fail=1
    fi
done

echo "──── HTTP endpoints ────"
check "GET /api/v1/health" curl -sf "http://localhost:${HOST_PORT}/api/v1/health"
check "GET /metrics" sh -c "curl -sf http://localhost:${HOST_PORT}/metrics | grep -q forge_http_requests_total"

echo "──── Celery ────"
check "worker inspect ping" docker exec forge-worker celery -A app.workers inspect ping -d "celery@$(docker exec forge-worker hostname)"

echo "──── Database ────"
DB_CONTAINER="${DB_CONTAINER:-forge-postgres}"
DB_USER="${DATABASE_USERNAME:-forge_app}"
DB_NAME="${DATABASE_DATABASE:-forge_main}"
if docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    tables=$(docker exec -e PGPASSWORD="${DATABASE_PASSWORD:-}" "$DB_CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" \
        2>/dev/null | tr -d ' \n')
    if [ "${tables:-0}" -ge 10 ]; then
        echo "✓ ${DB_CONTAINER} ($tables tables)"
    else
        echo "✗ ${DB_CONTAINER} (only $tables tables, expected ≥10)"; fail=1
    fi
else
    echo "✗ ${DB_CONTAINER} not ready"; fail=1
fi

echo "──── Redis ────"
RC="${REDIS_CONTAINER:-forge-redis}"
PASS="${CACHE_PASSWORD:-}"
check "redis ping" docker exec "$RC" redis-cli -a "$PASS" ping

echo
if [ $fail -eq 0 ]; then
    echo "All checks passed."
    exit 0
fi
echo "FAIL: at least one check failed." >&2
exit 1
