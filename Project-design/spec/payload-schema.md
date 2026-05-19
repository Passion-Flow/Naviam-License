# License Payload Schema v1.0

`.forge` 文件中 `payload.json` 的权威定义。**所有语言实现必须严格遵守**。

## 序列化规范化（HARD — 一旦定下不可改）

签名前必须把 payload 字典按下述规则规范化，得到字节流：

| 选项               | 值                              |
|--------------------|---------------------------------|
| `sort_keys`        | **true** — 键名按字典序          |
| `separators`       | **`(",", ":")`** — 无任何多余空格 |
| `ensure_ascii`     | **false** — 非 ASCII 走 UTF-8     |
| 字符编码           | **UTF-8**（无 BOM）              |
| `datetime` 字段    | **ISO 8601** with timezone offset|

> Python 实现：`json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`
>
> **改动这套算法 = 旧 license 全部失效**。任何变更必须走 protocol_version 大版本升级。

## 字段定义

| 字段                  | 类型         | 必填 | 描述                                                              |
|-----------------------|--------------|------|-------------------------------------------------------------------|
| `protocol_version`    | string       | ✓    | 协议版本 SemVer，当前 `"1.0"`                                     |
| `license_id`          | string       | ✓    | License 唯一 ID（推荐 UUIDv4）                                     |
| `customer_id`         | string       | ✓    | 客户实体 ID（与 LA 客户表对齐）                                    |
| `product_id`          | string       | ✓    | 产品 ID（与 LA 产品表对齐）                                        |
| `mode`                | enum         | ✓    | 验证模式：`offline` / `hybrid` / `online`                          |
| `scope`               | enum         | ✓    | 颗粒度：`customer_x_product` / `customer_bundle` / `instance`      |
| `binding`             | enum         | ✓    | 绑定模式：`none` / `soft` / `hard`                                 |
| `bound_fingerprint`   | string\|null | hard 必填 | 仅 `binding=="hard"` 时必填；签发时硬绑的部署指纹（SHA-256 hex） |
| `issued_at`           | datetime     | ✓    | 签发时间（UTC ISO 8601）                                          |
| `expires_at`          | datetime     | ✓    | 过期时间（UTC ISO 8601）                                          |
| `features`            | object       | ✓    | 启用 features 映射（业务字段由产品定义解释；空对象合法）          |
| `limits`              | object       | ✓    | 配额：`max_users` / `max_instances` / `max_cores` 等               |

## 示例

```json
{
  "bound_fingerprint": null,
  "customer_id": "cust-acme-corp",
  "expires_at": "2027-05-13T00:00:00+00:00",
  "features": {"sso": true, "audit_log": true},
  "issued_at": "2026-05-13T10:23:45+00:00",
  "license_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "limits": {"max_users": 50},
  "mode": "hybrid",
  "product_id": "prod-naviam",
  "protocol_version": "1.0",
  "scope": "customer_x_product"
}
```

注意：键已按字典序排列、无多余空格——这正是签名时的字节流。

## 版本演进规则

- **minor 升级**（1.0 → 1.1）：仅允许**新增可选字段**；老 verifier 应忽略未识别字段
- **major 升级**（1.0 → 2.0）：可任意改字段；老 verifier 必须**明确拒绝**未知 major 版本

## 安全注意

- 任何字段值都不得包含未编码的控制字符
- `customer_id` / `product_id` / `license_id` 长度建议 ≤ 256 字节
- `features` / `limits` 嵌套深度建议 ≤ 5 层；避免 verifier 解析时栈爆
