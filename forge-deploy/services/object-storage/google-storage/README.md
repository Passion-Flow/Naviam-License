# Google Cloud Storage — Forge

公有云 provider，**无本地 compose**。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=google-storage
# GKE Workload Identity 模式：留空 GOOGLE_APPLICATION_CREDENTIALS，走 metadata server
# 自管 / on-prem 模式：把 service account JSON 挂到容器，路径填到下面
GOOGLE_APPLICATION_CREDENTIALS=/etc/forge/gcs-sa.json
OBJECT_STORAGE_REGION=<gcp-project-id>                      # 用作构造 gs://<project>/<bucket>
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots
```

> GCS 概念对齐：bucket 名全 GCP 全局唯一。建议加客户前缀：`<customer>-forge-license-files`。

## IAM 最小角色

不用预置 role；用 custom role 把权限收到 3 个动作：

```bash
PROJECT=my-gcp-project
gcloud iam roles create forgeBucketRW \
  --project="$PROJECT" \
  --title="Forge Bucket Read/Write" \
  --permissions="storage.objects.get,storage.objects.create,storage.objects.delete,storage.objects.list"
```

或者直接用预置 role（如不介意 list bucket）：`roles/storage.objectAdmin`。

## Service Account 创建

```bash
PROJECT=my-gcp-project SA=forge-app
gcloud iam service-accounts create "$SA" --project="$PROJECT" --display-name="Forge License Authority"

# 给 SA 绑定 custom role 到 3 个 bucket
for b in forge-license-files forge-public-keys forge-audit-snapshots; do
  gsutil iam ch \
    "serviceAccount:${SA}@${PROJECT}.iam.gserviceaccount.com:projects/${PROJECT}/roles/forgeBucketRW" \
    "gs://${b}"
done

# 自管模式：下载 key
gcloud iam service-accounts keys create gcs-sa.json \
  --iam-account="${SA}@${PROJECT}.iam.gserviceaccount.com"
```

## Bucket 创建

```bash
LOC=us-central1
for b in forge-license-files forge-public-keys forge-audit-snapshots; do
  gcloud storage buckets create "gs://$b" \
    --location="$LOC" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --default-storage-class=STANDARD
  # 版本控制
  gcloud storage buckets update "gs://$b" --versioning
done
```

## GKE Workload Identity

1. GKE cluster 启用 Workload Identity
2. 绑定 K8s ServiceAccount `forge-api` 到 GCP SA：

```bash
KSA=forge-api NS=forge
gcloud iam service-accounts add-iam-policy-binding \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:${PROJECT}.svc.id.goog[${NS}/${KSA}]" \
  "${SA}@${PROJECT}.iam.gserviceaccount.com"

kubectl annotate sa -n "$NS" "$KSA" \
  iam.gke.io/gcp-service-account="${SA}@${PROJECT}.iam.gserviceaccount.com"
```

forge-server `.env`：留空 `GOOGLE_APPLICATION_CREDENTIALS` → SDK 走 metadata server。

## 验证

```bash
export GOOGLE_APPLICATION_CREDENTIALS=$PWD/gcs-sa.json
export PROJECT=my-gcp-project
bash verify.sh
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `403 storage.objects.create denied` | custom role 权限不足或绑定到错 bucket |
| `404 bucket does not exist` | bucket 名全局唯一，可能被其他客户占用 — 加前缀 |
| Workload Identity 失败 | `kubectl exec ... -- gcloud auth list` 应显示 GCP SA |
| `Quota exceeded` | bucket 上传配额，开 case 申请 |
