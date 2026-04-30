# 接口契约

本项目接口契约的源文件位于 `src/contracts/`（Python）。前端类型镜像位于 `apps/web/src/types/contracts.ts`。

任何接口变更须通过 `/sync-api-contract` 命令级联更新。

## 通用约定

- Base URL：`/v1/`。
- 鉴权：服务端 Session（HttpOnly Cookie）。
- 写操作：必须带 CSRF Token（`X-CSRFToken`）。
- 错误返回：

```json
{
  "code": "<machine-readable>",
  "message": "<human readable>",
  "hint": "<optional>",
  "trace_id": "<uuid>"
}
```

- 列表分页：

```json
{
  "items": [...],
  "total": 123,
  "page": 1,
  "page_size": 20
}
```

- 时间字段：`timestamptz`，对外 ISO-8601 UTC，前端按用户时区展示。

## 端点清单（V1）

### 鉴权 / 账户

```
POST   /v1/auth/login            { username, password } -> { challenge: "totp" } 或 { ok }
POST   /v1/auth/totp             { code }              -> { ok }
POST   /v1/auth/logout
POST   /v1/auth/change-password  { current_password, new_password }
GET    /v1/auth/me               -> { user }
POST   /v1/auth/totp/setup       -> { otpauth_uri, qr_svg }
POST   /v1/auth/totp/confirm     { code } -> { recovery_codes }
```

### 客户

```
GET    /v1/customers             ?q=&page=&page_size=
POST   /v1/customers             { display_name, contact_*, region, notes }
GET    /v1/customers/{id}
PATCH  /v1/customers/{id}        { ...partial }
DELETE /v1/customers/{id}        // 软删除 + 审计
```

### 产品

```
GET    /v1/products              -> [ { code, display_name, schema_version } ]
GET    /v1/products/{code}
```

第一版无 POST / PATCH / DELETE；通过 fixtures 维护一条 `default`。

### License

```
GET    /v1/licenses              ?customer_id=&product_code=&status=
POST   /v1/licenses/issue        { mode: "online" | "offline",
                                    customer_id, product_code,
                                    cloud_id (offline) | instance_callback (online),
                                    not_before, not_after, notes }
                                  -> { license_id,
                                       activation_code (offline) | delivery_status (online) }
GET    /v1/licenses/{id}
POST   /v1/licenses/{id}/renew   { not_before, not_after, mode } -> { activation_code? }
POST   /v1/licenses/{id}/revoke  { reason } -> { ok }
GET    /v1/licenses/{id}/heartbeats ?since=
GET    /v1/licenses/{id}/audit
```

### 激活（产品端入站）

```
POST   /v1/activations/online    { license_payload }   // 由 Console 主动调用产品端，仅作为 SDK 接口反向参考
POST   /v1/heartbeats            { license_id, status, detail }   // SDK -> Console
GET    /v1/activations/lookup-by-cloud-id  { cloud_id } -> { license_id?, status? }
```

### 审计

```
GET    /v1/audit                 ?action=&since=&until=&page=
POST   /v1/audit/export          { since, until } -> { download_url }    // 服务端打包并签名
GET    /v1/audit/integrity       -> { ok, last_hash, last_signature }
```

### 通知

```
GET    /v1/notifications/channels
POST   /v1/notifications/channels  { customer_id, kind, destination }
DELETE /v1/notifications/channels/{id}
GET    /v1/notifications/outbox    ?status=
```

### 设置

```
GET    /v1/settings/security      -> { kid, last_rotation_at, kms_status, password_policy }
POST   /v1/settings/security/rotate-keys   // 仅生成新 kid，不删除旧的
```

## 错误码（节选）

| code | 说明 |
|---|---|
| `auth.invalid_credentials` | 用户名或密码错误 |
| `auth.locked` | 账号已锁定 |
| `auth.totp_required` | 需要 2FA |
| `auth.totp_invalid` | 2FA 码错误 |
| `auth.csrf_missing` | 缺少 CSRF |
| `license.cloud_id_invalid` | Cloud ID 解码失败 |
| `license.cloud_id_checksum` | Cloud ID 校验位失败 |
| `license.signature_invalid` | License 签名失败 |
| `license.expired` | License 已过期 |
| `license.revoked` | License 已撤销 |
| `license.cross_machine` | Cloud ID 与 License 绑定不一致 |
| `license.online_unreachable` | 在线签发的产品实例不可达 |
| `audit.chain_broken` | 审计链失配 |
| `ratelimit.exceeded` | 触发限速 |
| `server.internal` | 服务器异常（携带 trace_id） |

## 头部

请求：

- `X-CSRFToken`：写操作必带。
- `Cookie: sessionid=...`：HttpOnly。
- `Accept-Language`: 默认 `zh-CN`。
- `X-Request-ID`：客户端可选传；服务器透传。

响应：

- `X-Trace-Id`：全部响应必带。
- `Cache-Control: no-store`：默认。
- `Strict-Transport-Security`：生产开启。

## 版本

V1 仅保证向后兼容增量字段。破坏性变更必须 `v2` 路径并保留 `v1` 至少 6 个月。
