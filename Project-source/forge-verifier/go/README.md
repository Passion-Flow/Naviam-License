# forge-verifier (Go)

Go 参考实现 —— 嵌入到 Go 客户端 / cmd 工具，启动期校验 Forge LA 颁发的 `.forge` license。

> 当前版本：**v0.3** —— Ed25519 + RSA-PSS（2048/4096）+ **SM2**（国密，`github.com/tjfoc/gmsm`）+ parse + signature + expiry，外加 heartbeat client、CRL fetcher、soft-fingerprint binding、hybrid/online 一站式 verifier。

## 安装

```bash
# 方案 A：源码拷贝（推荐，与"项目独立"铁律一致）
cp -r forge-verifier/go /your-project/internal/forgeverifier

# 方案 B：私有 Go module proxy
go get github.com/your-co/forge-verifier-go@v0.1.0

# 方案 C：直接 replace 到本地路径
echo "replace github.com/your-co/forge-verifier-go => ../forge-verifier/go" >> go.mod
```

## 用法

```go
package main

import (
    "log"
    "time"

    forgeverifier "github.com/your-co/forge-verifier-go"
)

func main() {
    // 公钥从 LA 的 /api/v1/public-keys 拉取，或在 build 时嵌入。
    publicKey := []byte{ /* 32 bytes Ed25519 raw */ }

    res, err := forgeverifier.Verify("/etc/myapp/license.forge", publicKey, time.Now().UTC())
    if err != nil {
        log.Fatalf("license invalid: %v (status=%s)", err, res.Status)
    }
    log.Printf("license ok: id=%s expires=%s", res.LicenseID, res.ExpiresAt)
}
```

## API

| 函数 / 类型 | 用途 |
|-------------|------|
| `Verify(path, publicKey, now) (*Result, error)` | one-shot 校验 |
| `Parse(path) (*File, error)` | 仅解析，不校验签名（用于 CLI 工具显示内容）|
| `(*File).Verify(publicKey, now)` | 已解析后单独校验 |
| `Result` | `Status` / `LicenseID` / `ExpiresAt` / `Binding` / `FingerprintMustMatch` |
| `Metadata` / `Payload` | 公开结构供调用方读取 |

## 错误

```go
errors.Is(err, forgeverifier.ErrForgeFileMalformed)      // 文件损坏
errors.Is(err, forgeverifier.ErrAlgorithmUnsupported)    // 非 Ed25519
errors.Is(err, forgeverifier.ErrSignatureInvalid)        // 签名校验失败
errors.Is(err, forgeverifier.ErrExpired)                 // 过期
```

## 测试

```bash
cd forge-verifier/go
go test -v ./...
```

测试读 `../spec/test-vectors/` 跨语言互操作向量；Python 与 Go 必须验证同一份 `.forge` 文件结果一致。

## Heartbeat / CRL / Binding

```go
// Soft fingerprint —— mac|hostname|cpu SHA-256
fp, _ := forgeverifier.ComputeSoftFingerprint()

// Heartbeat client
hb := &forgeverifier.HeartbeatClient{
    BaseURL:   "https://forge.your-co/api/v1",
    APIKey:    "fk_live_...",
    UserAgent: "myapp/1.4.2",
}
resp, err := hb.Send(ctx, "lic_abc", fp)
// resp.LicenseStatus, resp.MultiEnvAnomaly, resp.NextHeartbeatAfterSeconds

// CRL（一次创建，多次 Refresh，并发安全）
crl := &forgeverifier.CRLClient{BaseURL: hb.BaseURL, APIKey: hb.APIKey}
_ = crl.Refresh(ctx)
if crl.IsRevoked("lic_abc") { /* fail closed */ }
```

## 后续 (按客户需求逐步加)

- [ ] mTLS（高安全场景，可选）

## 协议格式（与所有语言 SDK 共用）

`.forge` 是 ustar tarball，内含 3 个固定 entry：

```
payload.json    canonical JSON（签名时的精确字节）
signature.bin   raw signature bytes
metadata.json   magic="forg" / forge_version / algorithm / key_id / signed_at
```

详细字段定义见 `forge-verifier/spec/`。
