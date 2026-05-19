# `.forge` 文件布局 v1.0

`.forge` 是 **uncompressed POSIX tar** 包，固定 3 个成员文件。

## 容器格式

| 属性                | 值                                                 |
|---------------------|----------------------------------------------------|
| 容器类型            | POSIX tar（USTAR 格式）                            |
| 压缩                | **无**（保持 bit-identical 输出）                   |
| 文件扩展名          | `.forge`                                           |
| MIME 类型           | `application/vnd.forge.license+x-tar`              |

## tar 成员（顺序无关，存在性必备）

| 文件名         | 内容                                                          |
|----------------|---------------------------------------------------------------|
| `payload.json` | LicensePayload 的规范化字节流（详见 `payload-schema.md`）      |
| `signature.bin`| detached signature 字节流                                     |
| `metadata.json`| 签名元信息（algorithm / key_id / signed_at / forge_version）   |

## tar 条目属性（HARD）

签发端必须固定以下属性，保证同输入产生 bit-identical 输出：

| 属性          | 值        |
|---------------|-----------|
| `mtime`       | `0`       |
| `mode`        | `0644`    |
| `uid` / `gid` | `0`（默认）|
| `uname` / `gname` | 空      |

## metadata.json schema

| 字段             | 类型     | 描述                                                       |
|------------------|----------|------------------------------------------------------------|
| `magic`          | string   | 固定 `"forg"`                                              |
| `forge_version`  | string   | 容器格式版本 SemVer，当前 `"1.0"`                          |
| `algorithm`      | string   | 签名算法：`ed25519` / `rsa2048` / `rsa4096` / `sm2`        |
| `key_id`         | string   | 签名密钥 ID（与 LA 公钥分发 endpoint 对齐）                 |
| `signed_at`      | datetime | 签名时间（UTC ISO 8601）                                    |

`metadata.json` 同样按 sort_keys + 无空格 + UTF-8 序列化。

## signature.bin

detached signature 的**原始字节**（不做 base64 / hex 编码）。
长度由算法决定：

| 算法     | 长度       |
|----------|------------|
| ed25519  | 64 字节    |
| rsa2048  | 256 字节   |
| rsa4096  | 512 字节   |
| sm2      | 64-72 字节（DER 编码 R + S）|

## 验签输入

签名覆盖**且仅覆盖** `payload.json` 的字节内容。
**不**覆盖 `metadata.json` —— metadata 的 `algorithm` 与 `key_id` 用于查找公钥，不能既是输入又是结果。

## 解包安全注意

- tar 解包必须限制：单条目 ≤ 1 MB，总 tar ≤ 8 MB
- 拒绝任何不在白名单内的成员（`payload.json` / `signature.bin` / `metadata.json` 之外报错）
- 拒绝带绝对路径或 `..` 的成员（虽然我们写入时不会出现，但解包仍要防御）
- 不允许 symlink / hardlink 成员

## 人可读性

`.forge` 是 tar 包，客户可以用 `tar -tvf license.forge` 看内容、`tar -xOf license.forge payload.json | jq` 看 payload。
**便于客户人工排障**，无需特殊工具。
