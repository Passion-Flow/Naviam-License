# forge-verifier (.NET / C#)

.NET 参考实现 —— ASP.NET / WPF / WinForms / .NET 8 后台应用启动期校验 Forge LA 颁发的 `.forge` license。

> 当前版本：**v0.3** —— Ed25519 + RSA-PSS（2048/4096）+ **SM2**（国密，Bouncy Castle）+ parse + signature + expiry，外加 `HeartbeatClient` / `CrlClient` / `SoftFingerprint` / `OnlineVerifier`。

## 要求

- .NET 8.0+
- BouncyCastle.Cryptography 2.4+（Ed25519 BCL 没有，借用 BC）

## 安装

```bash
dotnet add package YourCo.Forge.Verifier --version 0.1.0
```

或源码拷贝：`cp -r forge-verifier/csharp/src /your-app/Forge.Verifier`。

## 用法

```csharp
using YourCo.Forge.Verifier;

byte[] publicKey = Convert.FromBase64String("..."); // 32 bytes Ed25519，从 LA /public-keys 拉
try
{
    var r = ForgeVerifier.Verify(
        "/etc/myapp/license.forge",
        publicKey,
        DateTimeOffset.UtcNow);
    Console.WriteLine($"license ok: id={r.LicenseId} expires={r.ExpiresAt:O}");
}
catch (ForgeVerifier.ForgeException e)
{
    Console.Error.WriteLine($"license invalid: {e.Message} (status={e.Status})");
    Environment.Exit(1);
}
```

## API

| 类 / 方法 | 用途 |
|----------|------|
| `ForgeVerifier.Verify(path, publicKey, now)` | one-shot 校验 |
| `ForgeVerifier.Parse(path)` | 仅解析（CLI 检视） |
| `ForgeFile.Verify(publicKey, now)` | 已解析后单独校验 |
| `Result` | `Status` / `LicenseId` / `ExpiresAt` / `Binding` / `FingerprintMustMatch` |
| `ForgeException` | `Status` + 可选 `Result`（过期场景） |

## 测试

```bash
cd forge-verifier/csharp
dotnet test
```

测试读 `../spec/test-vectors/` 跨语言互操作向量。

## Heartbeat / CRL / Binding

```csharp
var fp = SoftFingerprint.Compute();

var hb = new HeartbeatClient("https://forge.your-co/api/v1", "fk_live_...", "myapp/1.4.2");
var resp = await hb.SendAsync("lic_abc", fp);
// resp.LicenseStatus, resp.MultiEnvAnomaly, resp.NextHeartbeatAfterSeconds

var crl = new CrlClient("https://forge.your-co/api/v1", "fk_live_...", "myapp/1.4.2");
await crl.RefreshAsync();
if (crl.IsRevoked("lic_abc")) { /* fail closed */ }
```

## 后续

- [ ] `IHostedService` / `IServiceCollection.AddForgeVerifier()` 扩展（定时 heartbeat / CRL refresh）
- [ ] AOT 兼容（去掉 reflection-based JSON 反序列化）

## 协议格式

见 `forge-verifier/spec/`。
