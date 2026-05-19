# Tencent COS — Forge

公有云 provider，**无本地 compose**。

## forge-server env

```ini
OBJECT_STORAGE_TYPE=tencent-cos
OBJECT_STORAGE_REGION=ap-shanghai
OBJECT_STORAGE_ACCESS_KEY_ID=<SecretId>
OBJECT_STORAGE_ACCESS_KEY_SECRET=<SecretKey>
OBJECT_STORAGE_TENCENT_SCHEME=https
OBJECT_STORAGE_BUCKET_LICENSE_FILES=forge-license-files-<AppId>
OBJECT_STORAGE_BUCKET_PUBLIC_KEYS=forge-public-keys-<AppId>
OBJECT_STORAGE_BUCKET_AUDIT=forge-audit-snapshots-<AppId>
```

> 腾讯 COS 的 bucket 名形如 `<name>-<APPID>`，必须包含 AppId（与你 CAM 主账号绑定）。

## CAM 子账号 + 策略

1. 控制台 → 访问管理 → 用户 → 新建子用户 `forge-app`，仅勾「可访问腾讯云 API」
2. 创建自定义策略 `ForgeCOSBuckets`，绑定到 `forge-app`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": ["cos:GetService"],
      "resource": "*"
    },
    {
      "effect": "allow",
      "action": [
        "cos:GetObject",
        "cos:PutObject",
        "cos:DeleteObject",
        "cos:GetBucket",
        "cos:HeadBucket"
      ],
      "resource": [
        "qcs::cos:<region>:uid/<APPID>:forge-license-files-<APPID>/*",
        "qcs::cos:<region>:uid/<APPID>:forge-public-keys-<APPID>/*",
        "qcs::cos:<region>:uid/<APPID>:forge-audit-snapshots-<APPID>/*"
      ]
    }
  ]
}
```

## Bucket 创建

```bash
APPID=1250000000 REGION=ap-shanghai
export TENCENTCLOUD_SECRET_ID=... TENCENTCLOUD_SECRET_KEY=...
for b in forge-license-files forge-public-keys forge-audit-snapshots; do
  coscli bucket-create -b "${b}-${APPID}" -r "${REGION}"
  # 强制 HTTPS + 不允许公开读
  coscli bucket-policy-put -b "${b}-${APPID}" -r "${REGION}" --policy-file deny-http-policy.json
done
```

## TKE Pod Identity 推荐

避免长期 AK/SK：在 TKE 用 CAM Role for Pod（OIDC 模式）。forge-server 启动时通过元数据服务取临时凭证（cos-python-sdk-v5 ≥ 1.9 自动支持）。

## 验证

```bash
export TENCENTCLOUD_SECRET_ID=... TENCENTCLOUD_SECRET_KEY=...
export PREFIX=forge APPID=1250000000 REGION=ap-shanghai
bash verify.sh
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `AccessDenied` | CAM 策略 resource 不匹配 AppId / bucket |
| `NoSuchBucket` | bucket 名缺 `-<APPID>` 后缀 |
| `RequestTimeTooSkewed` | 容器时钟漂移超过 15 分钟，配 NTP |
| 跨 region 报错 | `OBJECT_STORAGE_REGION` 必须与 bucket 实际 region 一致 |
