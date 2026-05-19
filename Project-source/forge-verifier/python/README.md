# forge-verifier (Python)

Python 参考实现 —— 把 Forge License Authority 颁发的 `.forge` 文件嵌入到客户应用，启动期硬卡 + 运行期周期复查。

> Verifier 是 **被消费方应用 import 的库**。它本身没有"启动"动作。

---

## 安装

按消费方项目选择：

```bash
# 方案 A：源码拷贝（推荐，与"项目独立"铁律一致）
cp -r forge_verifier /path/to/consumer-project/

# 方案 B：私有 PyPI
pip install forge-verifier --index-url https://pypi.your-company/

# 方案 C：git subtree（与上游同步且独立目录）
git subtree add --prefix=vendor/forge-verifier git@your-co/forge.git main --squash
```

依赖（pyproject 已声明）：

| 包 | 用途 |
|----|------|
| `cryptography` | Ed25519 / RSA-PSS 签名校验 |
| `gmssl` | SM2 国密签名（仅 SM2 客户需要） |
| `httpx` | 心跳 + CRL 拉取 |

> ed25519 / RSA-PSS 不需要 gmssl；按客户场景选 extras：`pip install "forge-verifier[gmssl]"`。

---

## 5 分钟接入

### 1. 让 LA 给客户签发一把 license

```bash
curl -X POST https://forge.your-co/api/v1/licenses/issue \
  -H "X-Forge-API-Key: <project-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "acme",
    "product_id": "myapp-pro",
    "mode": "hybrid",
    "scope": "instance",
    "algorithm": "ed25519",
    "binding": "soft",
    "expires_at": "2027-01-01T00:00:00Z"
  }'
```

> 响应包含 `license_id`。下载 `.forge` 文件：`GET /api/v1/licenses/{license_id}/download`。

### 2. 客户应用启动时校验

```python
from forge_verifier import Verifier, VerificationFailed

verifier = Verifier(
    license_file_path="/etc/myapp/license.forge",
    public_key_b64=b"<LA 公钥 base64>",   # 直接 pin 或从 LA /public-keys 拉
    mode="hybrid",                       # offline | hybrid | online
    heartbeat_url="https://forge.your-co/api/v1/licenses/{license_id}/heartbeat",
    api_key="<project-api-key>",
    recheck_interval_seconds=300,
)

try:
    result = verifier.verify_blocking()
    print(f"License OK; valid_until={result.valid_until}")
except VerificationFailed as e:
    print(f"License 无效：{e.status} — {e.reason}")
    sys.exit(1)
```

### 3. 运行期周期复查

```python
verifier.start_periodic_recheck(
    on_invalid=lambda result: app.enter_readonly_mode(),
)
```

> 后台 daemon 线程，按 `recheck_interval_seconds` 自动跑；进程退出时记得 `verifier.stop()`。

---

## 模式

| 模式 | 适用场景 | 网络依赖 | 行为 |
|------|---------|----------|------|
| `offline` | 完全断网（air-gapped） | 无 | 仅校验签名 + 到期；不查 CRL、不发心跳 |
| `hybrid` | 默认；偶尔能上网 | 弱 | 启动时尝试拉 CRL；周期心跳。CRL/心跳失败不阻断启动（按 `grace_count`）|
| `online` | 实时强校验（金融/医疗） | 强 | 每次校验必须心跳成功；网络断 → `VerificationFailed` |

---

## Binding（指纹绑定）

| 等级 | 实现 | 用法 |
|------|------|------|
| `none` | 不采集指纹 | 测试 / 试用 license |
| `soft` | `mac + hostname + cpu_id` 哈希 | 推荐默认 |
| `hard` | 软指纹 + TPM PCR / SE platform UUID | 高安全；只对支持 TPM 的硬件 |

LA 签发时把指纹绑定到 license；Verifier 启动时重新采集并比对。多机移动 → 心跳上报新指纹 → LA 检测「多实例使用」并按策略告警 / 拒绝。

---

## 算法

四套算法签名校验已内置（与 LA 一一对应）：

| `algorithm` | 库 | 公钥编码 |
|-------------|----|----------|
| `ed25519` | `cryptography` Ed25519 | 32 B raw |
| `rsa2048` | `cryptography` RSA-PSS-SHA256 | DER SubjectPublicKeyInfo |
| `rsa4096` | 同上 | 同上 |
| `sm2` | `gmssl.sm2` | uncompressed point (65 B) |

> 验签前看 `.forge` 文件 `metadata.algorithm` 字段；与传入的 `public_key_b64` 算法必须一致，否则抛 `AlgorithmMismatch`。

---

## 心跳

`hybrid` / `online` 模式下，Verifier 每 `heartbeat_interval_seconds`（默认 24h，由 LA 在签发时写入 license）回报一次：

```
POST {heartbeat_url}
X-Forge-API-Key: <key>
X-Forge-Signature: <HMAC-SHA256 of body, key=API-Key 派生>
{
  "license_id": "...",
  "fingerprint": "...",          # 当前部署指纹
  "verifier_version": "0.1.0",
  "nonce": "<128-bit>",          # 防重放
  "reported_at": "2026-05-18T..."
}
```

LA 回 `{"ok": true}` 或具体 reason；Verifier 把响应缓存到 `~/.forge-verifier/heartbeat-state.json` 供下一次启动参考。

---

## 错误与状态

```python
from forge_verifier import (
    VerificationFailed,
    ForgeFileMalformed,
    AlgorithmMismatch,
    SignatureInvalid,
    Expired,
    BindingMismatch,
    Revoked,
    HeartbeatRejected,
)
```

所有异常继承 `VerificationFailed`，带 `.status` (string code) + `.reason` (human readable)。

---

## 目录

```
forge_verifier/
├── __init__.py                  ← 导出公共 API
├── verifier.py                  ← Verifier 主类
├── parsing/                     ← .forge tar 容器解析
├── algorithms/{ed25519,rsa,sm2}/← 算法适配器
├── binding/{none,soft,hard}/    ← 指纹策略
├── modes/{offline,hybrid,online}/← 模式策略
├── crl/                         ← CRL 拉取 + 校验
├── heartbeat/                   ← 心跳客户端 + HMAC
├── fingerprint.py
├── exceptions.py
└── types.py                     ← Result / Status / 错误码
```

---

## 开发与测试

```bash
pip install -e ".[dev]"
pytest                            # 48 tests
pytest tests/test_heartbeat.py -k hmac -v
```

---

## 与 forge-server 的版本兼容性

Verifier 与 LA 走 wire 协议：`.forge` 容器 schema + `/api/v1/licenses/{id}/heartbeat` JSON。两者按语义化版本演进；本 SDK 0.x 与 forge-server 0.x 互通。

升级路径（兼容性破坏型 minor 升级）：先发 LA，等所有客户 SDK 升级后再撤旧 wire format。

---

## 故障排查

| 现象 | 排查 |
|------|------|
| `ForgeFileMalformed` | `.forge` 文件路径错或被截断；检查 `file --mime-type`，应是 `application/x-tar` |
| `SignatureInvalid` | `public_key_b64` 与签发用的 key 不匹配；改用 LA 的 `/public-keys` API 拉最新 |
| `BindingMismatch` | 硬件指纹变了（换网卡 / VM 迁移）；联系 LA 管理员重发 license |
| `HeartbeatRejected reason=multi_env` | LA 检测到该 license 在多个不同指纹下心跳 → 客户违约多机部署 |
| 启动慢 5s+ | DNS 解析 LA 域名慢；hybrid 模式下 LA 不可达会等超时 → 改 `online_timeout_seconds` 缩短 |
