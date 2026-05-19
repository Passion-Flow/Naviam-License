# Azure Blob — Forge

公有云 provider，**无本地 compose**。Azure 概念对齐：bucket ↔ container，key ↔ blob name。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=azure-blob
OBJECT_STORAGE_ENDPOINT=https://<account>.blob.core.windows.net
OBJECT_STORAGE_ACCESS_KEY_ID=<storage-account-name>
OBJECT_STORAGE_ACCESS_KEY_SECRET=<storage-account-key>     # 或留空走 Managed Identity
OBJECT_STORAGE_AZURE_ENDPOINT_SUFFIX=core.windows.net      # AzureChinaCloud 用 core.chinacloudapi.cn
OBJECT_STORAGE_AZURE_USE_MANAGED_IDENTITY=false           # AKS 上设 true → 走 Workload Identity
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots
```

> Forge bucket = Azure container。命名规则：3–63 字符，仅小写字母 / 数字 / `-`。

## Storage Account 创建

```bash
RG=forge-rg LOC=eastus ACCOUNT=forgeprod001
az group create -n "$RG" -l "$LOC"
az storage account create \
  -n "$ACCOUNT" -g "$RG" -l "$LOC" \
  --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --https-only true \
  --allow-blob-public-access false
```

## Container 创建

```bash
ACCOUNT_KEY=$(az storage account keys list -g "$RG" -n "$ACCOUNT" --query '[0].value' -o tsv)
for c in forge-license-files forge-public-keys forge-audit-snapshots; do
  az storage container create \
    --account-name "$ACCOUNT" --account-key "$ACCOUNT_KEY" \
    --name "$c" --public-access off
done
```

## RBAC 最小权限（推荐 Managed Identity）

不要用 account key。建议用 Workload Identity / Managed Identity，给定 RBAC role：

```bash
PRINCIPAL_ID=<managed-identity-object-id>
ACCOUNT_RESOURCE_ID=$(az storage account show -n "$ACCOUNT" -g "$RG" --query id -o tsv)

# Storage Blob Data Contributor —— 仅指定的 container
for c in forge-license-files forge-public-keys forge-audit-snapshots; do
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Storage Blob Data Contributor" \
    --scope "${ACCOUNT_RESOURCE_ID}/blobServices/default/containers/${c}"
done
```

## AKS Workload Identity 部署

1. 启用 cluster 上的 OIDC + Workload Identity
2. 创建 Federated Identity Credential 绑 K8s ServiceAccount `forge-api`
3. forge-server `.env`：`OBJECT_STORAGE_AZURE_USE_MANAGED_IDENTITY=true`，留空 `OBJECT_STORAGE_ACCESS_KEY_SECRET`

## 验证

```bash
export AZURE_STORAGE_ACCOUNT=forgeprod001 AZURE_STORAGE_KEY=$ACCOUNT_KEY
bash verify.sh
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `403 AuthenticationFailed` | account key 错或过期；轮换 key |
| `404 ContainerNotFound` | container 没建；运行上面 `az storage container create` |
| `AuthorizationPermissionMismatch` | RBAC role 没生效（最长 5min 传播）|
| 中国云连不通 | endpoint suffix 错；改成 `core.chinacloudapi.cn` |
