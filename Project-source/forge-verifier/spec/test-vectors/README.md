# test-vectors/

跨语言互操作测试数据（占位）。所有 Verifier 实现必须跑通本目录全部测试向量。

每个测试目录建议命名：`NNN-<algo>-<mode>-<binding>/`，例如：

- `001-ed25519-offline-none/`
- `002-rsa2048-hybrid-soft/`
- `003-sm2-online-hard/`

每个目录包含：
- `keypair.json`（测试用，绝不在生产复用）
- `payload.json`
- `expected.forge`（hex / base64）
- `expected-verify.json`

待 forge-server 签发引擎与 spec 文档完善后，由 LA 端工具批量生成本目录数据。
