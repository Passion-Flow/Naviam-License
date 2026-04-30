# OWASP Top 10 (2021) 覆盖

本文件把 License 平台的安全控制映射到 OWASP Top 10 (2021) 每一条。每条都必须有「在哪里实现」「如何验证」。

## A01:2021 – Broken Access Control

实现：

- 视图层 `permission_classes` 显式声明，默认 `IsAuthenticated`。
- 服务层 `services.<action>` 在写操作前二次校验「actor 是否被允许操作该资源」。
- 列表与详情按 `customer_id`、`product_id` 强过滤。
- 无横向越权：第一版只有一个超级管理员，但视图与服务函数仍按多角色形态写，便于未来扩展。

验证：

- `tests/security/test_access_control.py` 覆盖：未登录访问敏感端点 401、跨资源访问 403、强制改密未完成跳转 302。

## A02:2021 – Cryptographic Failures

实现：

- 仅使用 `cryptography` 库的标准实现（Ed25519 / X25519 / HKDF）。
- 私钥存储：`age` / `sops` 加密文件 + passphrase。
- 密码哈希：Argon2id（`argon2-cffi`）；参数从 `.env` 注入。
- TOTP secret / 备用码：使用对称加密落盘（key 来自启动 passphrase 衍生）。
- 所有传输：TLS 1.3；HSTS preload；SameSite=Strict Cookie。
- 不自研任何密码学。

验证：

- `tests/security/test_crypto.py` 覆盖：错误密钥拒绝、签名重放被拒、Argon2id 参数符合最低标准。
- 启动时校验 `PASSWORD_HASHERS[0] == 'django.contrib.auth.hashers.Argon2PasswordHasher'`。

## A03:2021 – Injection

实现：

- ORM：Django ORM + 参数化；禁止 `extra(where=...)` 字符串拼接（如必须，加显式注释 + 单元测试）。
- HTML：模板自动转义；前端 React 自动转义。
- Shell / OS：禁止使用 `subprocess.call(shell=True)`；如必须使用 `shell=True`，必须 `shlex.quote` 并在审计中标记。
- LDAP / NoSQL：第一版无；引入时必须更新本节。
- HTTP header 注入：响应头通过 Django 接口构造；禁止直接 `\r\n`。

验证：

- bandit + semgrep。
- `tests/security/test_injection.py` 覆盖：恶意 payload 通过 API 输入不影响 SQL 与日志。

## A04:2021 – Insecure Design

实现：

- 默认拒绝。
- 失败模式 fail-closed（限速 / 锁定 / Webhook 不影响主流程但其它必经路径不通即拒绝）。
- 安全设计源于威胁模型 (`docs/security/threat-model.md`)，不是事后补丁。
- 离线撤销限制显式承认并文档化，配套 C3 / 短有效期缓解。

验证：

- 每个新模块在 PR 阶段必须更新威胁模型与本表。
- ADR 流程对架构决策留痕。

## A05:2021 – Security Misconfiguration

实现：

- 全部配置进 `.env.example`，生产覆盖默认值。
- `DEBUG=False`、`ALLOWED_HOSTS` 显式、`SECURE_*` 全开（生产）。
- 镜像 distroless + 非 root + 只读 FS。
- 依赖锁 `--generate-hashes`；CI 禁止使用未锁版本。
- 不开放 Django Admin（或开放但仅本机访问）。

验证：

- `tests/security/test_settings_baseline.py` 启动时 assert 关键设置。
- 镜像扫描 trivy。
- Helm `values.yaml` 必填字段：admin password、私钥 passphrase、TLS 证书。

## A06:2021 – Vulnerable and Outdated Components

实现：

- `pip-audit` + `safety` + `bandit` 在 CI。
- 前端 `pnpm audit` + `npm-audit-resolver`。
- 依赖锁 + hash 校验。
- 季度全量回补。

验证：

- CI 工作流通过门禁；高危 0。
- 月度报告归档。

## A07:2021 – Identification and Authentication Failures

实现：

- 强密码 + Argon2id。
- 强制 2FA TOTP；备用码加密。
- 登录限速 (`django-ratelimit`) + 锁定 (`django-axes`)。
- Session 服务端 + Redis 后端 + 滑动过期 + 一键失效。
- 强制改密首次登录。
- Cookie：HttpOnly + Secure + SameSite=Strict。

验证：

- `tests/security/test_login_attack.py`、`test_session_security.py`。

## A08:2021 – Software and Data Integrity Failures

实现：

- 镜像签名（cosign）+ SBOM（syft）。
- 依赖锁 hash。
- 审计哈希链 + 服务端签名。
- License 文件签名（Ed25519）。
- 不接受未签名 / 不可校验的导入。

验证：

- `tests/security/test_integrity.py` 篡改检测。
- 离线交付演练校验签名。

## A09:2021 – Security Logging and Monitoring Failures

实现：

- 结构化 JSON 日志 + 关键字段（trace_id、actor、action、target、result）。
- 审计哈希链单独表 + 全量保留。
- 关键事件实时告警（登录激增、签发激增、撤销激增、私钥不可用）。
- 日志不打印密钥、密码、token。

验证：

- `tests/security/test_logging_redaction.py` 输入敏感数据，断言日志被遮蔽。
- Prometheus + Alertmanager 演练。

## A10:2021 – Server-Side Request Forgery

实现：

- 所有出站 URL 通过白名单 / 协议白名单。
- Webhook 不允许 `localhost`、`127.0.0.0/8`、`169.254.0.0/16`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、IPv6 unique-local。
- DNS 解析后再次校验目标 IP。
- 出站连接超时 + 大小限制。

验证：

- `tests/security/test_ssrf.py` 覆盖各类内网 IP / DNS rebinding。

## 复核

- 每季度更新本表。
- 任何新对外接口必须在 PR 阶段提交对本表的影响分析。
