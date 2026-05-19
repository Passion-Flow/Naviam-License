#!/usr/bin/env bash
# Forge — Google Cloud Storage 连通 + 读写自检
set -euo pipefail
: "${GOOGLE_APPLICATION_CREDENTIALS:?missing GOOGLE_APPLICATION_CREDENTIALS}"
: "${PROJECT:?missing PROJECT}"
PREFIX="${PREFIX:-forge}"
BUCKETS=( "${PREFIX}-license-files" "${PREFIX}-public-keys" "${PREFIX}-audit-snapshots" )

echo "[1/4] gcloud auth"
gcloud auth activate-service-account --key-file="$GOOGLE_APPLICATION_CREDENTIALS" --quiet
gcloud auth list --format='value(account)' --filter=status:ACTIVE | head -1

for b in "${BUCKETS[@]}"; do
  echo "[2/4] head bucket: $b"
  gcloud storage buckets describe "gs://$b" --format='value(name,location,iamConfiguration.uniformBucketLevelAccess.enabled)' >/dev/null
done

KEY="forge-probe/$(date -u +%s).txt"
TMP="$(mktemp)"; echo "forge probe $(date -u +%FT%TZ)" > "$TMP"
echo "[3/4] upload + read + delete on ${BUCKETS[0]}"
gcloud storage cp "$TMP" "gs://${BUCKETS[0]}/${KEY}" --quiet
gcloud storage cat "gs://${BUCKETS[0]}/${KEY}" >/dev/null
gcloud storage rm "gs://${BUCKETS[0]}/${KEY}" --quiet
rm -f "$TMP"

echo "[4/4] uniform-bucket-level-access check"
for b in "${BUCKETS[@]}"; do
  enabled=$(gcloud storage buckets describe "gs://$b" --format='value(iamConfiguration.uniformBucketLevelAccess.enabled)')
  test "$enabled" = "True" || { echo "WARN: $b uniform access disabled"; exit 1; }
done

echo "OK — Forge GCS ready"
