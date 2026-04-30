# 开发路径

详细分阶段计划见 `docs/design/12-开发路径与模块化规范.md`。本文件作为执行视图，对每个阶段给出「先做什么文件 / 哪些 PR / 入口测试」。

## 阶段 1：项目骨架与安全基线

### 任务

1. `apps/api/pyproject.toml`、`requirements/{base,dev,prod}.txt`、`Dockerfile`。
2. `apps/api/config/settings/{base,dev,prod}.py` 落地全部 `02-开发技术栈设计.md` 的安全默认值。
3. `apps/api/config/urls.py`、`asgi.py`、`wsgi.py`。
4. `src/modules/security/`：`apps.py`、`signing.py`（IKeySigner + FileKeySigner 占位）、`audit_chain.py`（哈希链）、`ratelimit.py`、`headers.py`。
5. `apps/web/`：`package.json`、`next.config.js`、`tailwind.config.ts`、`src/app/layout.tsx`、登录页骨架。
6. `tests/integration/test_security_baseline.py`：启动期校验关键 settings。

### 入口测试

```bash
# 启动 Service
cd projects/license/deploy/database/postgres && docker compose up -d
cd projects/license/deploy/cache/redis && docker compose up -d

# 后端
cd projects/license/apps/api
uv pip install -r requirements/dev.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8080

# 前端
cd projects/license/apps/web
pnpm install
pnpm dev
```

curl 校验：

```bash
curl -i http://127.0.0.1:8080/healthz
curl -i http://127.0.0.1:8080/readyz
```

## 阶段 2：账户与登录

### 任务

1. `src/modules/accounts/` 全套（model / serializer / view / service / urls / permissions / middleware）。
2. `apps/web/src/app/(auth)/login/` 登录页 + 2FA 输入 + 强制改密。
3. `tests/integration/test_accounts.py`、`tests/security/test_login_attack.py`。

### 入口测试

- 默认管理员首次登录强制改密 + 绑 2FA。
- 5 次密码错误锁定，10 分钟解锁。

## 阶段 3：客户 / 产品

### 任务

1. `src/modules/customers/`、`src/modules/products/`（产品仅只读）。
2. `apps/web/src/app/(dashboard)/customers/`、`products/`。
3. fixtures：默认产品 `code='default'`。

## 阶段 4：License 离线签发闭环

### 任务

1. `src/modules/activations/cloud_id_codec.py`（CBOR + base32 + checksum）。
2. `src/modules/licenses/services.py` 签发主流程。
3. `src/modules/licenses/codec.py`（License 文件编码 / Activation Code 编码）。
4. `apps/web/src/app/(dashboard)/licenses/` 签发表单 + Cloud ID 解析 + Activation Code 显示与复制。
5. `sdk/src/license_sdk/{loader,validator,crypto,errors}.py`：纯离线校验。
6. 安全测试：篡改、回放、跨机复制、checksum 失败。

### 入口测试

- 本地用 SDK 校验 Console 输出的 Activation Code 通过。
- 任意改动 license_id / customer_id / signature 任一字节都让 SDK 拒绝。

## 阶段 5：续期 + 撤销

### 任务

1. `services.renew`、`services.revoke`。
2. `apps/web/.../[id]/renew`、`.../[id]/revoke` 表单。
3. 审计写入 + 通知 outbox（仅创建条目，发送在阶段 7）。

## 阶段 6：在线激活 + 心跳

### 任务

1. `src/modules/activations/online.py`：mTLS 客户端 + 公钥指纹核对。
2. `src/modules/activations/heartbeat.py`：入站校验 + 限速 + 持久化。
3. SDK `online.py`：心跳 + 自动续期。
4. 集成测试：fake-product server。

## 阶段 7：通知 + 审计导出

### 任务

1. `src/modules/notifications/`：channel CRUD + outbox + 邮件 + Webhook + HMAC 签名。
2. `src/modules/audit/export.py`：打包 + 签名。
3. `apps/web/src/app/(dashboard)/audit/` 导出 UI。

## 阶段 8：私有化交付

### 任务

1. `infra/helm/license/`：Chart 编排（API、Web、Postgres、Redis、Ingress、cert-manager 集成）。
2. 离线交付脚本：`docker save` -> tar，Helm chart -> tgz，SBOM、签名、README。
3. Prometheus metrics + Grafana 模板。

## 不可妥协

- 安全测试不通过，阶段不闭环。
- 审计链可被篡改，阶段不闭环。
- 默认管理员未强制改密 / 2FA，阶段不闭环。
- License 任意字段串改后仍能通过 SDK 校验，阶段不闭环。
