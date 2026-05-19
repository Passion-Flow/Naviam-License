# Huawei OBS — Forge

公有云 provider，**无本地 compose**。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=huawei-obs
OBJECT_STORAGE_ENDPOINT=https://obs.cn-north-4.myhuaweicloud.com
OBJECT_STORAGE_ACCESS_KEY_ID=<AK>                       # IAM 子账号 AccessKey
OBJECT_STORAGE_ACCESS_KEY_SECRET=<SK>
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots
```

## IAM 子用户 + 策略

控制台 → 统一身份认证服务 IAM → 用户 → 创建子用户 `forge-app`，仅勾「编程访问」。
创建自定义策略 `ForgeOBSBuckets`，绑给子用户：

```json
{
  "Version": "1.1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "obs:object:GetObject",
        "obs:object:PutObject",
        "obs:object:DeleteObject",
        "obs:bucket:HeadBucket",
        "obs:bucket:ListBucket"
      ],
      "Resource": [
        "OBS:*:*:bucket:forge-license-files",
        "OBS:*:*:object:forge-license-files/*",
        "OBS:*:*:bucket:forge-public-keys",
        "OBS:*:*:object:forge-public-keys/*",
        "OBS:*:*:bucket:forge-audit-snapshots",
        "OBS:*:*:object:forge-audit-snapshots/*"
      ]
    }
  ]
}
```

## Bucket 创建

```bash
REGION=cn-north-4
export OBS_ACCESS_KEY=... OBS_SECRET_KEY=...
for b in forge-license-files forge-public-keys forge-audit-snapshots; do
  obsutil mb "obs://${b}" -location="$REGION" -acl=private
done
```

> 默认关闭公开访问；如有合规要求强制 HTTPS，控制台 → bucket → 桶策略 → 拒绝 `SecureTransport != true`。

## CCE Pod 推荐

CCE 上用 IAM Agency 让 Pod 自动取临时凭证（华为 SDK `esdk-obs-python` ≥ 3.21 自动支持）。

## 验证

```bash
export OBS_ACCESS_KEY=... OBS_SECRET_KEY=...
export ENDPOINT=https://obs.cn-north-4.myhuaweicloud.com
export PREFIX=forge
bash verify.sh
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `403 AccessDenied` | IAM 策略 resource 不匹配 |
| `404 NoSuchBucket` | bucket 不在 endpoint 对应 region |
| `RequestTimeTooSkewed` | 容器时钟漂移 |
