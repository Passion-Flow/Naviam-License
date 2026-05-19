# forge-verifier (Rust)

Rust 参考实现 —— 嵌入到 Rust 二进制（CLI / daemon / Tauri 桌面应用）启动期校验 Forge LA 颁发的 `.forge` license。

> 当前版本：**v0.3** —— Ed25519 + RSA-PSS（2048/4096）+ **SM2**（国密，`libsm` crate）+ parse + signature + expiry，外加 `heartbeat::HeartbeatClient`、`crl::CrlClient`、`binding::compute_soft_fingerprint`、`online::OnlineVerifier`。

## 安装

```toml
# Cargo.toml
[dependencies]
forge-verifier = { git = "https://your-co/forge.git", branch = "main" }
# 或私有 cargo registry：
# forge-verifier = { version = "0.1", registry = "your-co" }
```

源码拷贝：`cp -r forge-verifier/rust /your-project/forge-verifier`，再 `[dependencies] forge-verifier = { path = "./forge-verifier" }`。

## 用法

```rust
use chrono::Utc;
use forge_verifier::{verify, ForgeError};

fn main() {
    let public_key: [u8; 32] = [/* 32 bytes Ed25519，从 LA /public-keys 拉 */];
    match verify("/etc/myapp/license.forge", &public_key, Utc::now()) {
        Ok(r) => println!("license ok: id={} expires={}", r.license_id, r.expires_at),
        Err(ForgeError::Expired { result, .. }) => {
            eprintln!("expired: license_id={}", result.license_id);
            std::process::exit(1);
        }
        Err(e) => {
            eprintln!("license invalid: {e}");
            std::process::exit(1);
        }
    }
}
```

## API

| 函数 / 类型 | 用途 |
|-------------|------|
| `verify(path, public_key, now) -> Result<VerifyResult, ForgeError>` | one-shot 校验 |
| `parse(path) -> Result<ForgeFile, ForgeError>` | 仅解析 |
| `ForgeFile::verify(public_key, now)` | 已解析后单独校验 |
| `VerifyResult` | `status` / `license_id` / `expires_at` / `binding` / `fingerprint_must_match` |
| `ForgeError` | `Malformed` / `AlgorithmUnsupported` / `SignatureInvalid` / `Expired { result, license_id }` |

## 测试

```bash
cd forge-verifier/rust
cargo test
```

测试读 `../spec/test-vectors/` 跨语言互操作向量。

## Heartbeat / CRL / Binding

```rust
use forge_verifier::binding::compute_soft_fingerprint;
use forge_verifier::heartbeat::HeartbeatClient;
use forge_verifier::crl::CrlClient;

let fp = compute_soft_fingerprint();

let hb = HeartbeatClient::new("https://forge.your-co/api/v1", "fk_live_...", "myapp/1.4.2");
let resp = hb.send("lic_abc", &fp)?;
// resp.license_status, resp.multi_env_anomaly, resp.next_heartbeat_after_seconds

let crl = CrlClient::new("https://forge.your-co/api/v1", "fk_live_...", "myapp/1.4.2");
crl.refresh()?;
if crl.is_revoked("lic_abc") { /* fail closed */ }
```

阻塞 IO（`ureq`）。需要 async 时调用方可以用 `tokio::task::spawn_blocking` 包一层。

## 后续

- [ ] async API（`tokio` feature flag，可选 `reqwest`）
- [ ] `no_std` offline-only 子集

## 协议格式

见 `forge-verifier/spec/`。
