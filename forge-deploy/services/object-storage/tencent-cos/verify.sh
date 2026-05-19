#!/usr/bin/env bash
# Forge — Tencent COS 连通 + 读写自检（用 coscli）
set -euo pipefail
: "${TENCENTCLOUD_SECRET_ID:?missing TENCENTCLOUD_SECRET_ID}"
: "${TENCENTCLOUD_SECRET_KEY:?missing TENCENTCLOUD_SECRET_KEY}"
: "${APPID:?missing APPID (your Tencent Cloud APPID)}"
: "${REGION:=ap-shanghai}"
PREFIX="${PREFIX:-forge}"
BUCKETS=( "${PREFIX}-license-files-${APPID}" "${PREFIX}-public-keys-${APPID}" "${PREFIX}-audit-snapshots-${APPID}" )

CFG="$(mktemp -d)/cos.yaml"
cat > "$CFG" <<EOF
cos:
  base:
    secretid: $TENCENTCLOUD_SECRET_ID
    secretkey: $TENCENTCLOUD_SECRET_KEY
    sessiontoken: ""
    protocol: https
EOF
trap 'rm -rf "$(dirname "$CFG")"' EXIT

for b in "${BUCKETS[@]}"; do
  echo "[1/3] head bucket: $b"
  coscli -c "$CFG" bucket-head -b "$b" -r "$REGION" >/dev/null
done

KEY="forge-probe/$(date -u +%s).txt"
TMP="$(mktemp)"; echo "forge probe $(date -u +%FT%TZ)" > "$TMP"
echo "[2/3] cp + cat + rm on ${BUCKETS[0]}"
coscli -c "$CFG" cp "$TMP" "cos://${BUCKETS[0]}/${KEY}" -r "$REGION" >/dev/null
coscli -c "$CFG" cat "cos://${BUCKETS[0]}/${KEY}" -r "$REGION" >/dev/null
coscli -c "$CFG" rm "cos://${BUCKETS[0]}/${KEY}" -r "$REGION" -f >/dev/null
rm -f "$TMP"

echo "[3/3] bucket policy present"
coscli -c "$CFG" bucket-policy-get -b "${BUCKETS[0]}" -r "$REGION" >/dev/null || echo "(no policy — set deny-http if compliance requires)"

echo "OK — Forge Tencent COS ready"
