# Aliyun OSS — Forge

公有云 provider，**无本地 compose**。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=aliyun-oss
OBJECT_STORAGE_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OBJECT_STORAGE_REGION=cn-hangzhou
OBJECT_STORAGE_ACCESS_KEY_ID=LTAI...                  # RAM 子账号 AccessKeyId
OBJECT_STORAGE_ACCESS_KEY_SECRET=...                  # 对应 AccessKeySecret
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots
```

## RAM 子账号 + 策略

1. 控制台 → RAM → 用户 → 创建用户 `forge-app` → 只勾「OpenAPI 调用访问」
2. 创建自定义策略 `ForgeOSSBuckets`，绑定到 `forge-app`：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["oss:ListBuckets"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "oss:GetBucketInfo",
        "oss:GetBucketAcl"
      ],
      "Resource": [
        "acs:oss:*:*:forge-license-files",
        "acs:oss:*:*:forge-public-keys",
        "acs:oss:*:*:forge-audit-snapshots"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["oss:GetObject", "oss:PutObject", "oss:DeleteObject"],
      "Resource": [
        "acs:oss:*:*:forge-license-files/*",
        "acs:oss:*:*:forge-public-keys/*",
        "acs:oss:*:*:forge-audit-snapshots/*"
      ]
    }
  ]
}
```

## Bucket 创建

```bash
REGION=cn-hangzhou
for b in forge-license-files forge-public-keys forge-audit-snapshots; do
  ossutil mb "oss://$b" -e "oss-${REGION}.aliyuncs.com" --acl private
  # 强制 HTTPS
  ossutil bucket-policy --method put "oss://$b" deny-http-policy.json
done
```

`deny-http-policy.json`：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": "oss:*",
      "Principal": ["*"],
      "Resource": ["acs:oss:*:*:forge-*/*"],
      "Condition": { "Bool": { "acs:SecureTransport": "false" } }
    }
  ]
}
```

## 私有云上 ECS 推荐 RAM Role

不要把 AK/SK 入 secret。在 ECS / ACK：
1. 创建 RAM Role 绑定 ECS 实例 / ACK ServiceAccount
2. forge-server 启动时通过 ECS 元数据服务自动取临时凭证（SDK 已支持，需 oss2 ≥ 2.16）
3. forge-server `.env` 留空 `OBJECT_STORAGE_ACCESS_KEY_ID/SECRET`

## 验证

```bash
export OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
export OSS_ACCESS_KEY_ID=... OSS_ACCESS_KEY_SECRET=...
bash verify.sh
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `AccessDenied` | RAM 策略 resource 不匹配 bucket 名 |
| `InvalidAccessKeyId.NotFound` | AK 已禁用或删除 |
| 跨 region 报错 | `OBJECT_STORAGE_ENDPOINT` 必须与 bucket 实际 region 一致 |
| 私有云 ACK 出错 | 检查 RAM Role 是否给到 Pod 的 ServiceAccount |
