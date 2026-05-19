#!/usr/bin/env bash
# Forge — Volcengine TOS 连通 + 读写自检（用 tosutil）
set -euo pipefail
: "${VOLC_ACCESSKEY:?missing VOLC_ACCESSKEY}"
: "${VOLC_SECRETKEY:?missing VOLC_SECRETKEY}"
: "${REGION:=cn-beijing}"
PREFIX="${PREFIX:-forge}"
BUCKETS=( "${PREFIX}-license-files" "${PREFIX}-public-keys" "${PREFIX}-audit-snapshots" )
EP="tos-${REGION}.volces.com"

for b in "${BUCKETS[@]}"; do
  echo "[1/2] stat: $b"
  tosutil stat "tos://$b" -e "$EP" -i "$VOLC_ACCESSKEY" -k "$VOLC_SECRETKEY" >/dev/null
done

KEY="forge-probe/$(date -u +%s).txt"
TMP="$(mktemp)"; echo "forge probe $(date -u +%FT%TZ)" > "$TMP"
echo "[2/2] cp + rm on ${BUCKETS[0]}"
tosutil cp "$TMP" "tos://${BUCKETS[0]}/${KEY}" -e "$EP" -i "$VOLC_ACCESSKEY" -k "$VOLC_SECRETKEY" >/dev/null
tosutil rm "tos://${BUCKETS[0]}/${KEY}" -e "$EP" -i "$VOLC_ACCESSKEY" -k "$VOLC_SECRETKEY" -f >/dev/null
rm -f "$TMP"

echo "OK — Forge Volcengine TOS ready"
