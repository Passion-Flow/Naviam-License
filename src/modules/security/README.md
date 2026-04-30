# security 模块

## 职责

跨业务的安全基础设施。包括：

- 密钥加载（A 方案 = `age` / `sops` 加密文件 + passphrase）。
- IKeySigner 接口与 FileKeySigner 实现；KMS / HSM 后续替换。
- 审计哈希链工具（与 audit 模块协作）。
- 限速、登录锁定、安全头（HSTS / CSP / X-Frame / Referrer / COOP）。
- secrets 抽象：把 `.env` 与运行期 secret 统一在一处。
- 全站异常处理（`exceptions.exception_handler`）。
- 结构化 JSON 日志 + 敏感字段红黑名单（`logging.JsonFormatter`）。
- 启动期校验：缺关键设置 / 无私钥 -> 拒启动。

## 关键文件

- `signing.py`：FileKeySigner / public_key 导出 / kid 管理。
- `audit_chain.py`：与 audit 模块共用的链运算。
- `headers.py`：补充安全头中间件（如 Permissions-Policy）。
- `ratelimit.py`：自定义限速规则（按 actor + IP 维度）。
- `secrets.py`：env / 运行期 secret 解耦。
- `startup.py`：启动期 assert（生产 SECURE_*、PASSWORD_HASHERS、私钥可加载）。
- `exceptions.py`：DRF EXCEPTION_HANDLER。
- `logging.py`：JSON 格式 + 敏感字段红黑名单。
- `health_urls.py`：`/healthz`、`/readyz`。

## 关键约束

- 私钥永远在进程内存；不打印 / 不日志 / 不 dump。
- 所有 secrets 通过 `secrets.get('NAME')` 访问；禁止 `os.environ` 直读。
- 红黑名单中的字段被自动 `***` 替换；单测覆盖。

## 不做

- 不实现密码学算法。
- 不替代 audit 模块；本模块只提供工具。
