# 验证流状态机 v1.0

Verifier 从拿到 `.forge` 文件到给出 VerificationResult 的完整状态机。

## 状态码（最终结果之一）

| status              | 含义                                                          | 业务层动作建议                      |
|---------------------|---------------------------------------------------------------|-------------------------------------|
| `valid`             | License 完全有效                                              | 正常启动                            |
| `grace_period`      | License 已过期但在配置的宽限期内                              | 启动 + 告警 + 提示续期              |
| `binding_anomaly`   | soft binding 检测到指纹变化（不阻断）                         | 启动 + 上报心跳 + 写本地审计        |
| `expired`           | 已过期超过宽限期                                              | **拒绝启动** + exit 1               |
| `binding_mismatch`  | hard binding 指纹不匹配                                       | **拒绝启动** + exit 1               |
| `signature_invalid` | 签名校验失败（payload 被篡改或公钥不匹配）                    | **拒绝启动** + exit 1 + 告警        |
| `revoked`           | LA 端 CRL 显示已吊销（仅 hybrid/online 模式能拿到此结果）     | **拒绝启动** + exit 1               |
| `malformed`         | `.forge` 文件解析失败 / metadata 错误 / 未知算法              | **拒绝启动** + exit 1               |
| `unknown_key`       | metadata.key_id 在 LA 端公钥库中不存在                        | **拒绝启动** + exit 1               |
| `network_error`     | online 模式但联不上 LA 且无可用缓存                            | 按项目策略：拒绝 / 走宽限           |

## 完整状态机

```
┌───────────────────────────────┐
│ Verifier.verify_blocking()    │
└──────────────┬────────────────┘
               │
               ▼
   ┌─────────────────────────┐
   │ 1. 读 .forge 文件        │ ─── 读失败 ──▶  malformed
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 2. 解 tar / 三成员校验   │ ─── 缺成员 / tar 异常 ──▶  malformed
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 3. 解析 metadata.json    │ ─── magic 错 / 字段缺 ──▶  malformed
   │    解析 payload.json     │
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 4. protocol_version 检查 │ ─── 不识别 major ──▶  malformed
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 5. 算法分发 + 验签        │ ─── 算法不支持 ──▶  malformed
   │    （signature.bin       │ ─── 签名验证失败 ──▶ signature_invalid
   │      vs payload bytes）  │
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 6. 过期检查              │ ─── 过期 + 无宽限 ──▶  expired
   │    expires_at vs now    │ ─── 过期 + 在宽限 ──▶  grace_period (return)
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 7. binding 检查          │
   │  ┌────────────────────┐ │
   │  │ binding=none       │ │ ─── pass，仅采集指纹 ──▶ (继续 8)
   │  │ binding=hard       │ │ ─── fp mismatch ──▶ binding_mismatch
   │  │ binding=soft       │ │ ─── first-run / stable ──▶ (继续 8)
   │  │                    │ │ ─── fingerprint changed ──▶ binding_anomaly (return)
   │  └────────────────────┘ │
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ 8. mode 处理              │
   │  ┌────────────────────┐ │
   │  │ offline            │ │ ─── 不回连 ──▶ valid (return)
   │  │ hybrid             │ │ ─── 后台心跳；当前判定即返回 ──▶ valid
   │  │                    │ │     （联不上 LA 不阻断启动）
   │  │ online             │ │ ─── 同步回连 LA 查 CRL ──▶
   │  │                    │ │     pass: valid
   │  │                    │ │     revoked: revoked
   │  │                    │ │     unreachable: network_error
   │  └────────────────────┘ │
   └─────────────────────────┘
                │
                ▼
            VerificationResult
```

## 业务层与 Verifier 的契约

### 启动期（verify_blocking）
- 业务层调一次 `verify_blocking()`
- 任何 `VerificationFailed` → 业务层 **必须 exit 1**，错误信息打到 stderr + 日志
- 任何 `VerificationResult.status != "valid"` 但未抛异常的情况：
  - `grace_period`：业务层启动 + 在 UI / 日志显著提示"license 即将过期 / 已在宽限期"
  - `binding_anomaly`：业务层启动 + 上报心跳（hybrid 模式自动做）+ 本地审计
  - 业务层**可以**选择更严格策略（如把 binding_anomaly 也当 fatal），但默认不阻断

### 运行期（start_periodic_recheck）
- 每 `recheck_interval_seconds` 调一次 `verify_blocking()`
- 状态从 valid → 非 valid → 调用 `on_invalid(result)` 回调
- 业务层在 on_invalid 中**应**进入只读 / 部分禁用 / 计划下线，而不是立即 kill 进程

## 时间漂移容忍

- Verifier 与 LA 时钟可能漂移（私有化客户环境）
- `expires_at` 比对时建议给 **5 分钟** 容忍（业务层可配）
- 心跳 nonce 必须含 `issued_at` 防重放（hybrid/online 实现时落地）
