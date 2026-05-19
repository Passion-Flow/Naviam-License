#!/usr/bin/env bash
# Forge — Huawei OBS 连通 + 读写自检（用 obsutil）
set -euo pipefail
: "${OBS_ACCESS_KEY:?missing OBS_ACCESS_KEY}"
: "${OBS_SECRET_KEY:?missing OBS_SECRET_KEY}"
: "${ENDPOINT:?missing ENDPOINT (e.g. https://obs.cn-north-4.myhuaweicloud.com)}"
PREFIX="${PREFIX:-forge}"
BUCKETS=( "${PREFIX}-license-files" "${PREFIX}-public-keys" "${PREFIX}-audit-snapshots" )

obsutil config -i="$OBS_ACCESS_KEY" -k="$OBS_SECRET_KEY" -e="$ENDPOINT" -interactive=false >/dev/null

for b in "${BUCKETS[@]}"; do
  echo "[1/2] stat: $b"
  obsutil stat "obs://$b" >/dev/null
done

KEY="forge-probe/$(date -u +%s).txt"
TMP="$(mktemp)"; echo "forge probe $(date -u +%FT%TZ)" > "$TMP"
echo "[2/2] cp + rm on ${BUCKETS[0]}"
obsutil cp "$TMP" "obs://${BUCKETS[0]}/${KEY}" -f >/dev/null
obsutil rm "obs://${BUCKETS[0]}/${KEY}" -f >/dev/null
rm -f "$TMP"

echo "OK — Forge Huawei OBS ready"
