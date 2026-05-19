#!/usr/bin/env bash
# Forge — AWS S3 连通 + 权限自检
# 需要环境变量：AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
# 可选：PREFIX（默认 forge）
set -euo pipefail
: "${AWS_ACCESS_KEY_ID:?missing AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?missing AWS_SECRET_ACCESS_KEY}"
: "${AWS_DEFAULT_REGION:?missing AWS_DEFAULT_REGION}"
PREFIX="${PREFIX:-forge}"
BUCKETS=( "${PREFIX}-license-files" "${PREFIX}-public-keys" "${PREFIX}-audit-snapshots" )

echo "[1/4] identity"
aws sts get-caller-identity --output text

for b in "${BUCKETS[@]}"; do
  echo "[2/4] head-bucket: $b"
  aws s3api head-bucket --bucket "$b"
done

KEY="forge-probe/$(date -u +%s).txt"
echo "[3/4] put + get + delete on ${BUCKETS[0]}"
echo "forge probe $(date -u +%FT%TZ)" | aws s3 cp - "s3://${BUCKETS[0]}/${KEY}"
aws s3 cp "s3://${BUCKETS[0]}/${KEY}" - >/dev/null
aws s3 rm "s3://${BUCKETS[0]}/${KEY}"

echo "[4/4] encryption status"
aws s3api get-bucket-encryption --bucket "${BUCKETS[0]}" >/dev/null
echo "OK — Forge S3 (${PREFIX}) ready"
