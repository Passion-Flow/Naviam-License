# forge-verifier

Forge License **Verifier SDK** —— 嵌入到"以后的项目"里做 license 验签。

| 子目录          | 状态        | 说明                                                          |
|-----------------|-------------|---------------------------------------------------------------|
| `spec/`         | 待完善      | 协议规范（payload / signature / verification flow / 算法矩阵 / 测试向量），**权威源**，所有语言实现必须遵守 |
| `python/`       | 骨架        | Python 参考实现（与 forge-server 默认栈一致）                 |
| `typescript/`   | 占位        | TS/Node 实现（后续）                                          |
| `go/`           | 占位        | Go 实现（后续）                                               |

## 设计原则

1. **协议优先**：spec/ 是权威；各语言实现 must round-trip `test-vectors/` 中的样本数据
2. **零运行时联网**（offline 模式）：仅在 hybrid/online 模式才回连 LA
3. **公钥内置**：消费方项目编译期把 LA 公钥（或公钥指纹）打进镜像 / 客户端，避免运行时拉取
4. **失败硬卡 + 定期复查**：与全局 .agent.md 中"验签失败时项目该怎么举"一致
5. **provider-中立**：3 算法（Ed25519 / RSA / SM2）统一接口，运行时按 license metadata 选

## 分发模式

**项目选择**（与全局 .agent.md 一致）：
- 消费方项目可拷源码（推荐，与"项目独立"铁律最贴）
- 或私有 PyPI / npm 包消费（注意依赖管理）
- 或 git submodule（高度耦合，慎用）

Forge 不强推任何一种；只保证 spec/ 与各语言实现可独立演进。

## 版本与兼容性

- 协议版本走 SemVer，写在 license payload 的 `protocol_version` 字段
- Verifier 拒绝无法识别的 major 版本（明确报错）
- 同一 major 内的 minor 升级保持向后兼容（旧 verifier 能验新 license）
