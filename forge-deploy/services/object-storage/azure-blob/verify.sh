#!/usr/bin/env bash
# Forge — Azure Blob 连通 + 容器 + 读写自检
set -euo pipefail
: "${AZURE_STORAGE_ACCOUNT:?missing AZURE_STORAGE_ACCOUNT}"
: "${AZURE_STORAGE_KEY:?missing AZURE_STORAGE_KEY (or use SAS via AZURE_STORAGE_SAS_TOKEN)}"
PREFIX="${PREFIX:-forge}"
CONTAINERS=( "${PREFIX}-license-files" "${PREFIX}-public-keys" "${PREFIX}-audit-snapshots" )

echo "[1/4] account exists?"
az storage account show -n "$AZURE_STORAGE_ACCOUNT" --query '{name:name, kind:kind, tls:minimumTlsVersion}' -o table

for c in "${CONTAINERS[@]}"; do
  echo "[2/4] container exists: $c"
  az storage container show --account-name "$AZURE_STORAGE_ACCOUNT" --account-key "$AZURE_STORAGE_KEY" -n "$c" --query name -o tsv
done

BLOB="forge-probe-$(date -u +%s).txt"
TMP="$(mktemp)"; echo "forge probe $(date -u +%FT%TZ)" > "$TMP"

echo "[3/4] upload + download"
az storage blob upload --account-name "$AZURE_STORAGE_ACCOUNT" --account-key "$AZURE_STORAGE_KEY" \
  -c "${CONTAINERS[0]}" -n "$BLOB" -f "$TMP" -o none
az storage blob download --account-name "$AZURE_STORAGE_ACCOUNT" --account-key "$AZURE_STORAGE_KEY" \
  -c "${CONTAINERS[0]}" -n "$BLOB" -f "${TMP}.out" -o none
diff "$TMP" "${TMP}.out"

echo "[4/4] cleanup"
az storage blob delete --account-name "$AZURE_STORAGE_ACCOUNT" --account-key "$AZURE_STORAGE_KEY" \
  -c "${CONTAINERS[0]}" -n "$BLOB" -o none
rm -f "$TMP" "${TMP}.out"

echo "OK — Forge Azure Blob ($AZURE_STORAGE_ACCOUNT) ready"
