# License Console（厂商签发台）

> 私有化部署产品的 License 签发与运营控制台 —— 仅厂商使用；客户企业不部署本系统。

## 这是什么

- 厂商运营人员在这里**签发 / 续费 / 吊销** License。
- 客户企业拿到 License 后，把它装进**自家私有化部署的产品**（首发：Workerspace AI；后续可扩展到 N 个产品）。
- 双模式：**离线**（Cloud ID → Activation Code）＋ **在线**（mTLS 心跳）。
- 一刀切式 License：买了就是全功能，不做按功能粒度授权。

## 这不是什么

- ❌ 不是给客户企业用的：客户拿到的是 **license 文件 + Activation Code**，不是这个 Console 账号。
- ❌ 不是 SaaS：本系统在厂商内网部署。
- ❌ 不做按功能授权：V1 不引入复杂的 entitlement 模型。

## 顶层目录

```
projects/license/
├── .agent/                # 项目记忆（项目规则 / 当前上下文 / 会话日志）
├── apps/
│   ├── api/               # Django 5 + DRF（厂商后端）
│   └── web/               # Next.js 14 App Router（运营 Console UI）
├── deploy/
│   ├── database/postgres/ # Postgres 16 docker-compose（仅监听内部网络）
│   └── cache/redis/       # Redis 7 docker-compose
├── docs/                  # 设计文档（13 份）+ 安全扩展（3 份）+ API 契约 / ADR / 开发路径
├── sdk/                   # 产品方嵌入的 Python 校验 SDK
├── src/contracts/         # 跨模块契约（IKeySigner、AuditEvent、错误模型、分页）
├── src/modules/           # 八个业务模块（accounts / customers / products / licenses /
│                          # activations / audit / notifications / security）
├── tests/                 # 跨模块集成测试
├── infra/                 # 基础设施声明（占位；V2 引入 Helm / Pulumi 时填）
└── services/              # 占位；V1 不引入额外服务
```

详见 `docs/design/04-目录设计.md`。

## 快速上手

```bash
# 1) 起基础服务
cd deploy/database/postgres && cp .env.example .env  # 改 POSTGRES_PASSWORD
docker compose up -d
cd ../../cache/redis        && cp .env.example .env  # 改 REDIS_PASSWORD
docker compose up -d

# 2) 起 API（Python 3.12）
cd apps/api
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt
cp ../../.env.example ../../.env                     # 改 ⚠️ 标注的字段
python manage.py migrate
python manage.py loaddata config/fixtures/initial.json
python manage.py runserver

# 3) 起 Web（Node 20）
cd ../web
pnpm install
pnpm dev
```

打开 http://localhost:3000，使用默认账号登录：

```
用户名：Admin
邮箱：admin@workerspace.ai
密码：admin@workerspace.ai     # 首次登录强制改密
```

## 设计文档阅读顺序

| 想了解 | 先读 |
| --- | --- |
| 这个项目要解决什么 | `docs/design/00-设计总览.md` → `docs/design/01-需求视角挖掘.md` |
| 用什么技术 / 为什么 | `docs/design/02-开发技术栈设计.md` |
| 整体怎么搭起来的 | `docs/design/03-架构设计.md` |
| 目录长什么样 / 边界 | `docs/design/04-目录设计.md` |
| 后端 / 前端怎么写 | `docs/design/05-后端设计.md`、`docs/design/06-前端设计.md`、`docs/design/07-前端UI设计.md` |
| 服务 / 数据库 / 镜像 | `docs/design/08-服务层设计.md` ~ `10-镜像设计.md` |
| 私有化约束 | `docs/design/11-企业私有化部署约束.md` |
| 怎么落地 / 阶段验收 | `docs/design/12-开发路径与模块化规范.md`、`docs/development/development-path.md` |
| 安全模型 | `docs/security/threat-model.md`、`owasp-coverage.md`、`crypto-spec.md` |
| API 怎么调 | `docs/api/contracts.md` |
| 边界决策 | `docs/decisions/0001-项目边界.md` |

## 安全说明

> ⚠️ 任何"绝对安全"的承诺都是失实的。本项目的目标是：
>
> - **没有已知的漏洞类别**（覆盖 OWASP Top 10、STRIDE 主线）。
> - **没有人为埋设的后门**（开源依赖锁版本 + hash + SBOM；构建可复现）。
> - **可被检测、可被追溯、可被恢复**（哈希链审计；签名密钥可轮换；离线吊销有 grace + 上线追认）。
>
> 详见 `docs/security/`。

## 许可

[MIT](./LICENSE)
