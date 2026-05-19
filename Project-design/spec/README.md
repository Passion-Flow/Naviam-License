# License 协议规范

License 文件格式、签名流程、Verifier 行为的**权威定义**。所有语言实现都必须遵守本目录的规范。

## 即将填充的文档（占位）

| 文件                          | 内容                                                                                  |
|-------------------------------|---------------------------------------------------------------------------------------|
| `payload-schema.md`           | `payload.json` 所有字段定义、必选/可选、版本演进规则                                  |
| `signature-format.md`         | `signature.bin` 字节布局，detached signature 与 payload 的关联                         |
| `metadata-format.md`          | `metadata.json` 字段（算法、签名时间、签发者、公钥 ID 等）                            |
| `forge-file-format.md`        | `.forge` 容器格式（tar 内 layout）                                                    |
| `verification-flow.md`        | offline / hybrid / online 三种模式的完整状态机                                        |
| `algorithms.md`               | Ed25519 / RSA-2048 / RSA-4096 / SM2 的具体使用约定（编码、padding、hash 等）           |
| `binding-modes.md`            | none / soft / hard 三档绑定的指纹采集与比对规则                                       |
| `revocation.md`               | CRL 文件格式、Verifier 拉取频率、心跳吊销判定                                          |
| `error-codes.md`              | 验签错误码字典（VerifierResult.code），供业务层判断                                   |
| `interop-test-vectors.md`     | 跨语言互操作测试向量（Python / TS / Go 实现必须互相验通）                              |

## 版本管理

- 协议版本走 SemVer：`v1.0.0` / `v1.1.0` / `v2.0.0`
- `payload.json` 包含 `protocol_version` 字段
- Verifier 拒绝无法识别的 major 版本（明确报错）
