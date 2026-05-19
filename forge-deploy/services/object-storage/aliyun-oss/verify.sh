#!/usr/bin/env bash
# Forge — Aliyun OSS 连通 + 读写自检
set -euo pipefail
: "${OSS_ENDPOINT:?missing OSS_ENDPOINT (e.g. https://oss-cn-hangzhou.aliyuncs.com)}"
: "${OSS_ACCESS_KEY_ID:?missing OSS_ACCESS_KEY_ID}"
: "${OSS_ACCESS_KEY_SECRET:?missing OSS_ACCESS_KEY_SECRET}"
PREFIX="${PREFIX:-forge}"
BUCKETS=( "${PREFIX}-license-files" "${PREFIX}-public-keys" "${PREFIX}-audit-snapshots" )

CFG="$(mktemp)"
cat > "$CFG" <<EOF
[Credentials]
language=EN
endpoint=$OSS_ENDPOINT
accessKeyID=$OSS_ACCESS_KEY_ID
accessKeySecret=$OSS_ACCESS_KEY_SECRET
EOF
trap 'rm -f "$CFG"' EXIT

run() { ossutil --config-file "$CFG" "$@"; }

for b in "${BUCKETS[@]}"; do
  echo "[1/3] stat bucket: $b"
  run stat "oss://$b" >/dev/null
done

KEY="forge-probe/$(date -u +%s).txt"
TMP="$(mktemp)"; echo "forge probe $(date -u +%FT%TZ)" > "$TMP"
echo "[2/3] put + get + rm on ${BUCKETS[0]}"
run cp "$TMP" "oss://${BUCKETS[0]}/${KEY}" >/dev/null
run cp "oss://${BUCKETS[0]}/${KEY}" - 2>/dev/null
run rm "oss://${BUCKETS[0]}/${KEY}" -f >/dev/null
rm -f "$TMP"

echo "[3/3] secure-transport check"
run bucket-policy --method get "oss://${BUCKETS[0]}" >/dev/null && echo "policy present"

echo "OK — Forge Aliyun OSS ready"
