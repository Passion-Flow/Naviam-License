# forge-verifier/spec/

License 协议规范的**权威源**。Python / Go / Java / C# / Rust / TypeScript 实现都从本目录读规范。

> 与 `Project-design/spec/` 的关系：
> - `Project-design/spec/` 偏**设计与决策记录**（业务侧、可读性优先）
> - 本目录偏**实现规范**（开发侧、机器可校验优先，含 test vectors）
>
> 内容有重叠；以本目录为实现依据，以 Project-design/spec 为业务决策依据。

## 规范文档

| 文件 | 内容 |
|------|------|
| [`payload-schema.json`](payload-schema.json) | JSON Schema 2020-12 定义 payload.json 所有字段 |
| [`forge-file-layout.md`](forge-file-layout.md) | `.forge` tarball 内布局 + canonical JSON 规则 |
| [`algorithm-encoding.md`](algorithm-encoding.md) | 4 算法的密钥 / 签名编码约定 |
| [`binding-fingerprint.md`](binding-fingerprint.md) | 部署指纹采集与归一化 |
| [`verification-state-machine.md`](verification-state-machine.md) | offline / hybrid / online 三种模式的完整状态机 |
| [`error-codes.md`](error-codes.md) | VerifierResult 错误码字典 |

## test-vectors/

跨语言互操作测试数据。每个测试向量包含：

```
test-vectors/
├── 001-ed25519-offline-none/
│   ├── keypair.json          ← 测试用密钥对（仅测试用、非真实凭证）
│   ├── payload.json          ← 待签 payload
│   ├── expected.forge        ← 期望生成的 .forge 文件
│   ├── expected.forge.hex    ← 同上 hex（便于 diff）
│   └── expected-verify.json  ← 验证后的期望结果
├── 002-ed25519-hybrid-soft/
├── 003-ed25519-offline-hard/
└── ...
```

生成器：`python test-vectors/generate.py`。每个语言 SDK 的测试套件**必须**跑通全部测试向量。

## 协议版本

当前 `forge_version = "1.0"`。

后续若发生 wire-breaking 变更：
1. 新版本必须 `forge_version` 跳 MAJOR；
2. LA + 所有 SDK 同步发布；
3. 旧 SDK 看到新 magic / version 必须明确拒绝并给客户 `algorithm.unsupported` 类错误。
