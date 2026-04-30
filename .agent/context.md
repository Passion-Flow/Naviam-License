# License 项目上下文

创建日期：`2026-04-27`

## 当前阶段

初始化完成。已完成开放式设计会话与第一版方案落地。下一步进入实现阶段。

## 当前目标

按 `docs/development/development-path.md` 推进第一版骨架到可签发可激活可校验的最小闭环。

## 已确定事项

### 业务

- 唯一签发主体：厂商。
- 唯一接收对象：私有化部署的产品实例。
- 第一版仅一个产品，架构按多产品设计；扩展到第二个产品零迁移成本。
- License 一次签发开放完整功能，不做按 feature 颗粒度切分。
- 默认管理员账号：`Admin / admin@workerspace.ai / admin@workerspace.ai`（变量化）。
- 单一超级管理员，第一版不需要多角色；后续按用户要求扩展。

### 激活流程

- 在线激活与离线激活均必须支持。
- 离线激活采用 Dify 风格：产品 UI 显示 Cloud ID -> 客户复制到 Console -> Console 签发 Activation Code -> 客户粘贴回产品 -> 产品本地校验签名落地。
- Cloud ID 编码：`(product_id, instance_id, instance public key fingerprint, hardware fingerprint hash, schema_version)`。
- Activation Code 是厂商私钥对「特定 Cloud ID + License 元数据」的签名，跨机复制无效。

### 过期 / 续期 / 撤销

- 过期 A2：到期后只读 + 30 天宽限期，宽限期内仅允许导出 / 续期相关操作。
- 续期 B2/B3：B2 同实例新签发覆盖；B3 在线模式下自动续期。
- 撤销 C1：在线模式下立即撤销；离线模式下记录「已撤销但客户仍可在到期日前使用」并产出 Webhook + 邮件通知，纳入审计。
- 离线撤销不可达是物理限制，已写入威胁模型；缓解手段是「短有效期 + 必选在线检查（C3 可选）」。

### 技术栈

- 后端：Python 3.12 + Django 5 + Django REST Framework + Postgres 16 (psycopg 3) + Redis 7。
- 认证：django-allauth + django-otp + pyotp（TOTP 2FA）+ argon2-cffi + django-axes（登录锁定）+ django-ratelimit + django-csp。
- 加密：cryptography 库（Ed25519 / X25519 / HKDF）。不自研。
- 前端：Next.js 14 App Router + TypeScript + shadcn/ui + Tailwind + React Hook Form + Zod。
- SDK：独立 Python pip 包 `license_sdk`，离线优先。
- 依赖锁定：uv / pip-tools 全 hash 锁；CI 强制 pip-audit + safety + bandit + semgrep。
- 镜像：distroless 基底 + 非 root + 只读文件系统 + NetworkPolicy + 镜像签名 + SBOM + 可复现构建。

### Service 层

- 第一版仅启用 Postgres + Redis。
- 不引入 MinIO（License 文件直接由 API 返回）。
- 不引入 Elasticsearch / 向量库（无搜索/向量需求）。
- 不引入 Nginx Service（直连 API + Web，私有化部署阶段再加反代）。
- 未引入的 Service 已在 `docs/design/08-服务层设计.md` 记录「暂不引入」理由与触发引入条件。

### 镜像边界

- 第一版仅 `apps/api/` + `apps/web/`。
- `worker / gateway / sandbox / enterprise-web / enterprise-worker` 全部暂不引入；触发条件已在 `docs/design/10-镜像设计.md` 写明。

### 目录约束（写入 `docs/design/04-目录设计.md`）

- 业务模块 = 目录。一个登录功能是一个目录，不允许「一个按钮一个目录」。
- 每个目录至少 ≥ 2 个有用文件，否则不创建目录。
- 最大 4 层深度；Next.js App Router 路由是已记录的例外。
- 单文件组件不单独建目录，直接和兄弟组件平级。
- 单文件超过约 400 行触发拆分；不到则保持。

### 安全策略（写入 `docs/security/`）

- 威胁模型：STRIDE 全维度覆盖；OWASP Top 10 全条目可追溯到代码与配置。
- 密钥保管：默认 A 方案 = 加密文件（age / sops）+ passphrase + 启动时解封；预留 KMS / HSM 接口（IKeySigner）。
- 审计哈希链：每条审计记录 = `(prev_hash, payload, server_signature)`；篡改可证伪。
- 失败策略：默认拒绝；任何放行必须显式策略 + 审计。

## 需要持续确认的问题

- KMS / HSM 是否进入第二阶段（接口已预留）。
- 是否需要 C3「必选在线检查」作为高敏感客户的可选项。
- 是否需要硬件锁（USB Token）作为最高级别签发审批的二级凭证。
- 客户侧合规导出格式（PDF / CSV / 数字签名压缩包）。

## 项目记忆

### 用户目标

厂商安全签发与管理 License；杜绝破解、复制、伪造；同时支持在线 / 离线两种激活通道；用户体验对齐 Dify 的 Cloud ID / Activation Code 流程。

### 产品判断

- 离线优先：有线下客户、内网客户和高合规客户；离线必须自洽。
- 在线增强：心跳、撤销、续期、统计在在线模式下提供。
- 一个 License 一个完整功能：不做 feature flag 颗粒度，简单可信。

### 技术判断

- Python + Django 是稳定 + 安全默认值最完善的后端栈，匹配既有产品语言。
- Next.js App Router + shadcn/ui 是当下私有化 Console 最易交付的前端组合。
- Ed25519 + 业界标准库；不自研密码学。
- 默认拒绝 + 审计哈希链 + 限速 + 锁定是最低基线。

### 决策变化

- 初期讨论曾考虑 Go 后端，因「既有产品是 Python」改为 Django。
- 初期讨论曾考虑「JSON 激活文件交换」，被用户改为 Dify 风格 Cloud ID / Activation Code，UX 更轻、安全模型相同。
- 初期讨论曾考虑「百分之百安全」承诺，AI 拒绝并改为「无已知漏洞类、无后门、可发现可追溯可恢复」。

### 可复用沉淀

- 「业务模块 = 目录、≥2 文件、≤4 层、单文件 ≤400 行、单文件组件不建目录」的目录约束已纳入本项目 `04-目录设计.md`；如其他项目验证有效，可同步到工作区全局规则。

## 下一步

按 `docs/development/development-path.md` 第一阶段推进：

1. 完成 `apps/api/` Django 项目骨架与 `config/settings/{base,dev,prod}.py`。
2. 完成 `src/modules/security/` 的 Ed25519 密钥加载、审计哈希链、限速与会话基础。
3. 完成 `src/modules/accounts/` 登录 / 2FA / 强制改密 / 锁定。
4. 完成 `src/modules/licenses/` 与 `src/modules/activations/` 第一版离线签发 + 校验闭环。
5. 完成 `apps/web/` 登录页 + License 列表 + 签发表单 + Cloud ID/Activation Code 交换 UI。
6. 配合 `sdk/` 完成产品端校验最小流程（仅离线模式）。
