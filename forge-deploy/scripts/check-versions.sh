#!/usr/bin/env bash
# Forge — 版本一致性闸门
#
# 三个版本必须始终对齐：
#   Project-source/forge-server/pyproject.toml      version
#   Project-source/forge-admin/package.json         version
#   forge-deploy/helm/Chart.yaml                    version + appVersion
#
# 任一不一致 → 退出码 1（CI lint 阶段调用 → 红）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

server_version=$(grep -E '^version\s*=' "$ROOT/Project-source/forge-server/pyproject.toml" \
    | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
admin_version=$(grep -E '"version"' "$ROOT/Project-source/forge-admin/package.json" \
    | head -1 | sed -E 's/[^0-9]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/')
chart_version=$(grep -E '^version:' "$ROOT/forge-deploy/helm/Chart.yaml" \
    | head -1 | awk '{print $2}')
app_version=$(grep -E '^appVersion:' "$ROOT/forge-deploy/helm/Chart.yaml" \
    | head -1 | awk '{print $2}' | tr -d '"')

echo "forge-server pyproject : $server_version"
echo "forge-admin  package   : $admin_version"
echo "helm Chart   version   : $chart_version"
echo "helm Chart   appVersion: $app_version"

fail=0
if [ "$server_version" != "$admin_version" ]; then
    echo "✗ server != admin" >&2; fail=1
fi
if [ "$server_version" != "$chart_version" ]; then
    echo "✗ server != chart.version" >&2; fail=1
fi
if [ "$server_version" != "$app_version" ]; then
    echo "✗ server != chart.appVersion" >&2; fail=1
fi
[ $fail -eq 0 ] && echo "OK — versions aligned ($server_version)" || exit 1
