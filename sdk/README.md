# license-sdk

License 校验 SDK（Python，被产品方嵌入）。

## 职责

- 加载 License 文件（offline 包：JSON + 签名）。
- 校验：签名（Ed25519）、有效期、product_id、cloud_id_binding、schema_version。
- 离线模式：仅本地校验；返回 `LicenseStatus(active|grace|expired|revoked|invalid)`。
- 在线模式（可选）：调用 Console `/v1/sdk/heartbeat`，刷新 revocation 状态与 grace。
- 不缓存私钥；不写入磁盘；线程安全。

## 不做

- 不实现密码学算法（cryptography 库托底）。
- 不解析 Activation Code（这是 Console 端的事）。
- 不主动联网（除非显式启用 online）。

## 安装

```bash
pip install license-sdk          # 仅离线校验
pip install license-sdk[online]  # 包含 httpx，启用心跳
```

## 用法

```python
from license_sdk import LicenseClient

client = LicenseClient.from_file(
    license_path="/var/lib/myapp/license.lic",
    pubkey_path="/etc/myapp/license-pubkey.pem",  # vendor public key
    product_id="default",
)
status = client.verify()
if not status.is_active():
    raise SystemExit("license not active: " + status.reason)
```

在线模式：

```python
from license_sdk import LicenseClient, OnlineConfig

client = LicenseClient.from_file(
    ...,
    online=OnlineConfig(
        endpoint="https://license.example.com",
        heartbeat_interval_seconds=3600,
    ),
)
```

## 协议版本

- `schema_version=1`：当前实现。
- 升级策略见 `docs/security/crypto-spec.md`。

## 安全

- 公钥固定在产品镜像内（pin），不接受运行期注入的公钥。
- License 文件不可写（产品启动时校验权限）。
- 在线心跳走 mTLS（产品镜像内置 client cert），不可降级到普通 HTTPS。
