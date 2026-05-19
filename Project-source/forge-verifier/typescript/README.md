# forge-verifier (TypeScript / Node)

TS / Node 参考实现 —— Electron 桌面 / Node 后端 / CLI 启动期校验 Forge LA 颁发的 `.forge` license。

> **v0.2** —— Ed25519 + RSA-PSS（2048/4096）+ SM2（可选）+ parse + signature + expiry，外加 `HeartbeatClient` / `CrlClient` / `computeSoftFingerprint` / `OnlineVerifier`。Node 18+，零必装 deps（仅 SM2 走 optional `sm-crypto`）。

## 要求

- Node 18.17+（`crypto.verify` 已稳定）
- TypeScript 5+（如果你的工程也是 TS）

## 安装

```bash
npm install @yourco/forge-verifier
# 信创场景需要 SM2：
npm install sm-crypto
```

或源码拷贝：`cp -r forge-verifier/typescript /your-app/forge-verifier`。

## 用法

```typescript
import { verify, ForgeError } from "@yourco/forge-verifier";

// 公钥从 LA /api/v1/public-keys 拉，base64 解为 32 字节 Uint8Array（ed25519）。
const publicKey = new Uint8Array(Buffer.from("...", "base64"));

try {
  const res = await verify("/etc/myapp/license.forge", publicKey, new Date());
  console.log(`license ok: id=${res.licenseId} expires=${res.expiresAt}`);
} catch (err) {
  if (err instanceof ForgeError) {
    console.error(`license invalid: ${err.message} (status=${err.status})`);
    process.exit(1);
  }
  throw err;
}
```

## Heartbeat / CRL / Binding

```typescript
import {
  HeartbeatClient,
  CrlClient,
  OnlineVerifier,
  computeSoftFingerprint,
} from "@yourco/forge-verifier";

const fingerprint = computeSoftFingerprint();
const baseUrl = "https://forge.your-co/api/v1";
const apiKey = "fk_live_...";

const heartbeat = new HeartbeatClient({ baseUrl, apiKey, userAgent: "myapp/1.4.2" });
const crl = new CrlClient({ baseUrl, apiKey });
const v = new OnlineVerifier({ publicKey, heartbeat, crl });

// 一站式 —— license 内嵌的 mode 决定 offline / hybrid / online 行为
const res = await v.verify("/etc/myapp/license.forge", fingerprint, new Date());
```

## API

| 导出 | 用途 |
|------|------|
| `verify(path, publicKey, now) → Promise<VerifyResult>` | one-shot 校验 |
| `parse(path) → Promise<ForgeFile>` / `parseBytes(bytes)` | 仅解析（CLI 检视） |
| `verifyFile(file, publicKey, now)` | 已解析后单独校验 |
| `OnlineVerifier` | 组合 verify + heartbeat + CRL，按 license.mode 自动调度 |
| `HeartbeatClient` | `/api/v1/licenses/{id}/heartbeat` |
| `CrlClient` | `/api/v1/revocation-list` with ETag 缓存 |
| `computeSoftFingerprint()` | SHA-256 over (MAC \| hostname \| CPU) |
| `canonicalize(value)` | RFC 8785 子集 —— HMAC 签 body 时与服务器一致 |
| `ForgeError` | `status` ∈ `valid` / `expired` / `revoked` / `signature_invalid` / `algorithm_unsupported` / `malformed` |

## 测试

```bash
cd forge-verifier/typescript
npm install
npm test
```

测试读 `../spec/test-vectors/` 跨语言互操作向量 —— Python / Go / Java / C# / Rust / TS 必须验证同一份 `.forge` 文件结果一致。

## 协议格式

见 `forge-verifier/spec/`（与所有语言 SDK 共用）。
