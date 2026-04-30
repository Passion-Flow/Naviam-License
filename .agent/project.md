# License 项目规则

项目目录：`projects/license/`

创建日期：`2026-04-27`

## 项目定位

`License` 是厂商内部使用的「私有化产品 License 签发与管理平台」。它的唯一签发主体是厂商本身；接受 License 的客体是部署在客户内网的私有化产品实例。

第一版只服务一个产品，但架构按 N 个产品设计，扩展到第二个产品时无需迁移。

平台同时支持两种激活通道：

- 在线激活：产品实例直接连回厂商 Console 完成激活、续期、撤销。
- 离线激活：客户内网无外网，通过「产品端复制 Cloud ID -> Console 签发 Activation Code -> 产品端粘贴」完成激活，与 Dify 风格一致。

License 一次签发即开放完整功能，不做按功能颗粒度切分。

## 项目核心约束

### 安全是最高优先级

本平台直接关联厂商商业利益。所有设计、代码、依赖、部署都必须遵守：

- 不引入任何已知漏洞类。
- 不允许任何后门、调试旁路、隐藏管理员通道。
- 不自研加密算法，全部使用业界标准实现（Ed25519、Argon2id、TLS 1.3、HKDF、constant-time compare）。
- 任何攻击行为必须可被审计、可追溯、可恢复。
- 默认拒绝；任何放行都必须有显式策略与审计。
- 「百分之百安全」物理上不存在，平台目标是把攻击者成本抬到远高于收益、把每条已知攻击路径堵死、并保证任何成功攻击都可发现可定位可恢复。

### 认证机制

- 唯一会话机制：服务端会话 + HttpOnly + Secure + SameSite=Strict Cookie。
- 不使用浏览器侧 JWT/LocalStorage 存敏感凭证。
- 默认管理员账号：`Admin / admin@workerspace.ai / admin@workerspace.ai`，全部变量化（`.env.example`）。
- 默认强制 2FA（TOTP），首次登录强制改密 + 绑定 2FA。
- 登录限速、登录锁定、Argon2id 密码、CSRF 双提交、严格 CORS、HSTS、CSP。

### 数据与签名

- 离线激活基线：所有验证逻辑必须能在「无网络」下完成；产品端只持有厂商公钥即可校验。
- 在线激活只是增强：心跳、撤销、自动续期、用量上报。
- License 内部字段：`license_id, product_id, customer_id, cloud_id_binding, issued_at, expires_at, version, signature`。
- Activation Code 强绑定到具体的 Cloud ID（产品实例 + 硬件指纹），跨机复制无效。

## 项目边界

本项目的需求、设计、代码、服务、数据库、镜像和部署信息只能保存在 `projects/license/` 内。

禁止读取其他项目的业务方案。只有用户明确要求复用时，才可以参考其他项目，并且必须改写成本项目自己的设计。

## AI 工作原则

- 安全相关代码不允许「先跑通再加固」。第一版必须直接按生产标准实现密码哈希、签名验证、限速、审计与会话。
- 不允许业务配置硬编码，所有可变项进入 `.env.example`。
- Service 层使用独立 Docker Compose，应用代码默认手动启动。
- 除非用户明确要求，不主动 build 开发代码镜像。
- 前后端围绕同一份接口契约开发，契约源文件位于 `src/contracts/` 与 `docs/api/contracts.md`。
- 开发路径按功能 + 模块分阶段推进（详见 `docs/development/development-path.md`），不只写 P1/P2/P3。
- 数据库 schema、初始化数据、迁移、回滚、多环境同步必须提前规划。

## 读取顺序

处理本项目时，优先读取：

1. `.agent/project.md`
2. `.agent/context.md`
3. `docs/design/00-设计总览.md`
4. `docs/security/threat-model.md`
5. `docs/roadmap.md`
6. 最近的 `.agent/session-log.md`

## 文档维护

每次开发或讨论结束后，必须更新项目上下文与必要设计文档。

更新时必记：

- 本轮做了什么。
- 为什么这样做（特别是安全相关决策）。
- 影响哪些目录或模块。
- 哪些结论仍是假设。
- 下一步从哪里继续。

## 可主动扩展方向

AI 可以在不污染全局的前提下，新增以下方向的文档或目录：

- 安全审查清单、渗透测试用例、密钥轮换 SOP。
- 供应链安全（SBOM、依赖锁、镜像签名、可复现构建）。
- 关键事件应急预案（密钥泄漏、误签发、撤销失败）。
- 客户侧合规材料（部署手册、密钥管理说明、审计导出格式）。

## 企业私有化部署约束

本项目同时面向：

- 厂商 Console（厂商内部部署）。
- 产品 SDK（嵌入到客户产品镜像中）。

需考虑：Helm/Docker 交付、AMD64/ARM64、Mac/Linux/Windows 客户端浏览器、国内/国外/离线网络环境、明暗主题与自适应窗口、合规导出（审计日志、签发台账）。
