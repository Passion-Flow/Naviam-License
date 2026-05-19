# forge-verifier (Java)

Java 参考实现 —— Spring Boot / 企业级 Java 应用启动期校验 Forge LA 颁发的 `.forge` license。

> 当前版本：**v0.3** —— Ed25519 + RSA-PSS（2048/4096）+ **SM2**（国密，Bouncy Castle）+ parse + signature + expiry，外加 `HeartbeatClient` / `CrlClient` / `SoftFingerprint` / `OnlineVerifier`。

## 要求

- JDK 17+（Ed25519 是 JDK 15+ 标准 API）
- Maven 3.9+

## 安装

```xml
<dependency>
    <groupId>com.your-co</groupId>
    <artifactId>forge-verifier</artifactId>
    <version>0.1.0</version>
</dependency>
```

或源码拷贝：`cp -r forge-verifier/java/src /your-app/src/` 后改 package。

## 用法

```java
import com.yourco.forge.verifier.ForgeVerifier;
import com.yourco.forge.verifier.ForgeVerifier.Result;
import com.yourco.forge.verifier.ForgeVerifier.ForgeException;

import java.nio.file.Paths;
import java.time.Instant;
import java.util.Base64;

public class App {
    public static void main(String[] args) {
        byte[] publicKey = Base64.getDecoder().decode("..."); // 从 LA /public-keys 拉
        try {
            Result r = ForgeVerifier.verify(
                Paths.get("/etc/myapp/license.forge"),
                publicKey,
                Instant.now()
            );
            System.out.printf("license ok: id=%s expires=%s%n", r.licenseId, r.expiresAt);
        } catch (ForgeException e) {
            System.err.printf("license invalid: %s (status=%s)%n", e.getMessage(), e.status);
            System.exit(1);
        }
    }
}
```

## API

| 类 / 方法 | 用途 |
|----------|------|
| `ForgeVerifier.verify(path, publicKey, now)` | one-shot 校验 |
| `ForgeVerifier.parse(path)` | 仅解析（CLI 检视） |
| `ForgeFile.verify(publicKey, now)` | 已解析后单独校验 |
| `Result` | `status` / `licenseId` / `expiresAt` / `binding` / `fingerprintMustMatch` |
| `ForgeException` | `status` + 可选 `result`（过期场景） |

## 测试

```bash
cd forge-verifier/java
mvn test
```

测试读 `../spec/test-vectors/` 跨语言互操作向量。

## Heartbeat / CRL / Binding

```java
String fp = SoftFingerprint.compute();

HeartbeatClient hb = new HeartbeatClient(
    "https://forge.your-co/api/v1", "fk_live_...", "myapp/1.4.2");
HeartbeatClient.Response r = hb.send("lic_abc", fp);
// r.licenseStatus, r.multiEnvAnomaly, r.nextHeartbeatAfterSeconds

CrlClient crl = new CrlClient("https://forge.your-co/api/v1", "fk_live_...", "myapp/1.4.2");
crl.refresh();
if (crl.isRevoked("lic_abc")) { /* fail closed */ }
```

## 后续

- [ ] Spring Boot starter（auto-config + 定时 heartbeat / CRL refresh）

## 协议格式

见 `forge-verifier/spec/`（与所有语言 SDK 共用）。
