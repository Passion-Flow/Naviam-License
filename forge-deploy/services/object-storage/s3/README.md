# AWS S3 — Forge

公有云 provider，**无本地 compose**。本地开发请用 `../local/` MinIO 或 filesystem 模式。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=s3
OBJECT_STORAGE_ENDPOINT=                              # 默认走 AWS endpoint；S3 兼容服务（Ceph/R2/MinIO 远程）填实际
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_ACCESS_KEY_ID=AKIA...                  # 见下 IAM 策略
OBJECT_STORAGE_ACCESS_KEY_SECRET=...
OBJECT_STORAGE_USE_MANAGED_IAM=false                  # 在 EKS / EC2 上设 true → 走 IRSA / Instance Profile
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots
```

## IAM 最小权限策略

存为 `iam-policy.json` 后用 `aws iam create-policy --policy-name ForgeBuckets --policy-document file://iam-policy.json`。
变量替换：`<bucket-prefix>` = 客户 bucket 前缀（如 `forge`）；`<account-id>` = 客户 AWS 账号 ID。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListBuckets",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<bucket-prefix>-license-files",
        "arn:aws:s3:::<bucket-prefix>-public-keys",
        "arn:aws:s3:::<bucket-prefix>-audit-snapshots"
      ]
    },
    {
      "Sid": "ReadWriteObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": [
        "arn:aws:s3:::<bucket-prefix>-license-files/*",
        "arn:aws:s3:::<bucket-prefix>-public-keys/*",
        "arn:aws:s3:::<bucket-prefix>-audit-snapshots/*"
      ]
    }
  ]
}
```

不需要 `s3:CreateBucket` —— bucket 由客户在部署前手动创建。

## Bucket 创建命令

```bash
PREFIX=forge
REGION=us-east-1
for b in license-files public-keys audit-snapshots; do
  aws s3api create-bucket \
    --bucket "${PREFIX}-${b}" \
    --region "${REGION}" \
    $( [ "${REGION}" = "us-east-1" ] || echo "--create-bucket-configuration LocationConstraint=${REGION}" )
  # 加密 + 版本控制 + 私有
  aws s3api put-bucket-encryption --bucket "${PREFIX}-${b}" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-bucket-versioning --bucket "${PREFIX}-${b}" --versioning-configuration Status=Enabled
  aws s3api put-public-access-block --bucket "${PREFIX}-${b}" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
done
```

## 验证

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=us-east-1
PREFIX=forge bash verify.sh
```

## EKS / IRSA 推荐配置

不要把 access key 放 secret。在 EKS：
1. 创建 IAM Role，attach 上面的 policy
2. 给 ServiceAccount `forge-api` annotation `eks.amazonaws.com/role-arn=arn:aws:iam::<account>:role/ForgeApiRole`
3. forge-server `.env`：`OBJECT_STORAGE_USE_MANAGED_IAM=true`，留空 access key/secret

## 故障排查

| 现象 | 排查 |
|------|------|
| `403 AccessDenied` | IAM 策略 resource 不匹配，或 IRSA 没生效（kubectl exec → `aws sts get-caller-identity`）|
| `301 PermanentRedirect` | region 与 bucket region 不一致 |
| `NoSuchBucket` | bucket 没创建或拼错；与 `.env` 三个 bucket 名一一对应 |
| 上传慢 | 跨 region；用 `--endpoint-url` 指 transfer acceleration |
