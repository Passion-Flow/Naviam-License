# Volcengine TOS — Forge

公有云 provider，**无本地 compose**。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=volcengine-tos
OBJECT_STORAGE_ENDPOINT=tos-cn-beijing.volces.com
OBJECT_STORAGE_REGION=cn-beijing
OBJECT_STORAGE_ACCESS_KEY_ID=AKLT...                      # IAM 子账号 AccessKey
OBJECT_STORAGE_ACCESS_KEY_SECRET=...
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots
```

## IAM 子用户 + 策略

控制台 → 访问控制 → 用户 → 创建子用户 `forge-app`，绑定如下自定义策略 `ForgeTOSBuckets`：

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "tos:GetObject",
        "tos:PutObject",
        "tos:DeleteObject",
        "tos:HeadBucket",
        "tos:ListBucket"
      ],
      "Resource": [
        "trn:tos:::forge-license-files",
        "trn:tos:::forge-license-files/*",
        "trn:tos:::forge-public-keys",
        "trn:tos:::forge-public-keys/*",
        "trn:tos:::forge-audit-snapshots",
        "trn:tos:::forge-audit-snapshots/*"
      ]
    }
  ]
}
```

## Bucket 创建

```bash
REGION=cn-beijing
export VOLC_ACCESSKEY=... VOLC_SECRETKEY=...
for b in forge-license-files forge-public-keys forge-audit-snapshots; do
  tosutil mb "tos://${b}" -e "tos-${REGION}.volces.com" --acl private
done
```

> 推荐打开「请求强制 HTTPS」 + 「关闭公共访问」。

## VKE Pod 身份

可选：用 VKE 的 IAM Role for ServiceAccount，避免 AK/SK 明文。

## 验证

```bash
export VOLC_ACCESSKEY=... VOLC_SECRETKEY=...
export REGION=cn-beijing PREFIX=forge
bash verify.sh
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `AccessDenied` | IAM 策略 resource 不匹配 |
| `NoSuchBucket` | bucket 没创建或在其他 region |
| `RequestTimeTooSkewed` | NTP 配置 |
