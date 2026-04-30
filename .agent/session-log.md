# License 会话记录

## 2026-04-27 - 初始化项目

### 本轮完成

- 完成开放式设计会话：从「厂商签发 + 私有化产品 + 在线/离线双通道 + 最高安全」收敛到完整第一版方案。
- 创建项目目录骨架（按设计会话裁剪：仅 Postgres + Redis；仅 api + web 镜像）。
- 写入 `.agent/`（项目规则、上下文、会话记录）。
- 写入 `docs/design/` 全部 13 份并按本项目方案落地，`04-目录设计.md` 写入了本项目特有的目录强约束。
- 主动扩展 `docs/security/`（threat-model / owasp-coverage / crypto-spec）作为本项目专属文档。
- 写入 `docs/api/contracts.md` 接口契约骨架、`docs/development/development-path.md` 模块化路径、`docs/deployment/private-deployment.md` 私有化部署约束。
- 写入 `apps/api/` Django 项目骨架与 `apps/web/` Next.js App Router 骨架（仅结构，不含业务实现）。
- 写入 `src/modules/{accounts,customers,products,licenses,activations,audit,notifications,security}/` 八个模块骨架。
- 写入 `sdk/` Python 包骨架，包含 `client / loader / validator / crypto / online / errors` 平铺文件。
- 写入 `deploy/database/postgres/` 与 `deploy/cache/redis/` 独立 Compose 与说明。
- `.env.example` 按本项目裁剪：保留 Postgres、Redis、签发密钥、Session、CSRF、SDK 公钥；移除 MinIO、Elastic、Nginx、worker/gateway/sandbox/enterprise-* 段落。
- 在 `projects/_registry/projects.md` 追加本项目记录。

### 关键决策

- 安全基调改为「无已知漏洞类、无后门、可审计可追溯可恢复、不自研加密」，AI 主动否定了用户字面的「百分之百安全」表述并解释原因。
- 后端从初期讨论的 Go 改为 Python + Django，匹配既有产品语言并复用 Django 安全默认值。
- 离线激活流程从初期讨论的「JSON 激活文件交换」改为 Dify 风格 Cloud ID + Activation Code，UX 更轻、安全模型一致。
- License 一次签发即完整功能，不做 feature 颗粒度，降低误用面与复杂度。
- 第一版仅一个产品，但架构与 schema 按 N 个产品设计；扩展第二产品零迁移。
- 目录约束（业务模块 = 目录 / ≥2 文件 / ≤4 层 / 单文件组件不建目录 / 单文件 ≤400 行）成为本项目硬性规则。
- 仅启用 Postgres + Redis。MinIO / Elastic / Nginx Service / worker / gateway / sandbox / enterprise-* 全部暂不引入，触发条件全部写入对应设计文档。
- 密钥保管默认 A 方案：加密文件 + passphrase + 预留 KMS / HSM 接口。

### 变更文件

- `projects/license/.agent/{project.md,context.md,session-log.md}`
- `projects/license/docs/design/00-12*.md`
- `projects/license/docs/security/{threat-model.md,owasp-coverage.md,crypto-spec.md}`
- `projects/license/docs/api/contracts.md`
- `projects/license/docs/decisions/0001-项目边界.md`
- `projects/license/docs/development/development-path.md`
- `projects/license/docs/deployment/private-deployment.md`
- `projects/license/docs/roadmap.md`
- `projects/license/apps/api/{...}` Django 骨架
- `projects/license/apps/web/{...}` Next.js 骨架
- `projects/license/src/modules/{accounts,customers,products,licenses,activations,audit,notifications,security}/`
- `projects/license/src/{shared,contracts,config}/`
- `projects/license/sdk/`
- `projects/license/deploy/{database/postgres,cache/redis}/` + `deploy/SERVICE-CATALOG.md`
- `projects/license/{.env.example,.gitignore,.editorconfig,README.md,LICENSE,CHANGELOG.md}`
- `projects/_registry/projects.md`

### 不确定结论

- KMS / HSM 接入时机（接口已预留 IKeySigner，由后续业务量与合规要求触发）。
- C3「强制在线检查」是否作为高敏感客户可选项。
- 是否需要硬件 USB Token 作为签发审批二级凭证。
- 客户侧合规导出格式（PDF / CSV / 签名压缩包）。

### 下一步

- 按 `docs/development/development-path.md` 第一阶段推进 Django 项目骨架与 `security` 模块。
- 在 `apps/api/config/settings/base.py` 落地：`SECURE_*`、`SESSION_COOKIE_*`、`CSRF_*`、`PASSWORD_HASHERS`（Argon2id）、`AUTH_PASSWORD_VALIDATORS`、`django-axes`、`django-ratelimit`、`django-otp`、`django-csp` 全套默认值。
- 在 `src/modules/security/` 实现 Ed25519 密钥加载（A 方案）、审计哈希链、签发签名、Activation Code 编码。

## 后续记录要求

后续每轮记录使用倒序追加。每次记录应说明：

- 做了什么。
- 为什么这样做（安全相关变更必须显式记录权衡）。
- 影响哪些文件。
- 哪些结论仍不确定。
- 下一次继续时应优先看哪里。

如本轮产生威胁模型、密钥管理、合规、商业或工程判断，必须主动记录。
