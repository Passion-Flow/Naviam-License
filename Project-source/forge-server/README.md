# forge-server

Forge 后端服务：API + 签发 + 验签 + 心跳 + 审计。

## 启动

```bash
# 一次性：在你的 venv 里以 editable 方式装上 forge-server 与（可选的）forge-verifier
pip install -e .                            # 自身：让 `import app` 不再依赖 PYTHONPATH
pip install -e ../forge-verifier/python     # e2e 测试需要；不在生产 Dockerfile 里走

cp .env.example .env       # 按需改本地配置
python main.py             # 或 uvicorn app.main:app --reload --port 13001
pytest                     # 套件不再需要 PYTHONPATH=. 前缀
```

依赖 Service 由 `../../forge-deploy/services/<分类>/<provider>/` 各自起。

## 目录布局

```
forge-server/
├── main.py                     ← 启动入口（uvicorn 包装）
├── pyproject.toml              ← 依赖与脚本（uv / poetry）
├── .env.example                ← 配置样例（注释清楚每个字段含义）
├── alembic.ini                 ← Alembic 配置
│
├── app/
│   ├── settings/               ← Pydantic Settings（无硬编码原则的落地点）
│   │
│   ├── api/v1/                 ← API 路由（每个 endpoint 一个目录）
│   │   ├── auth/               ← 厂商 admin 登录 + SSO
│   │   ├── customers/          ← 客户管理（list/detail/create/update/delete 各一目录）
│   │   ├── products/           ← 产品定义
│   │   ├── licenses/           ← License CRUD + issue/revoke/renew/verify/heartbeat/download
│   │   ├── keys/               ← 签名密钥管理（generate/rotate/revoke/export_public）
│   │   ├── api_keys/           ← Verifier 用 API Key
│   │   ├── revocation_list/    ← CRL 公开 endpoint
│   │   ├── public_keys/        ← 公钥发布 endpoint（Verifier 拉取用）
│   │   └── audit/              ← 审计日志查询
│   │
│   ├── core/                   ← 业务核心（无 framework 耦合）
│   │   ├── signing/            ← 签名引擎（ed25519/rsa/sm2 各一目录，遵循统一 Signer Protocol）
│   │   ├── license/            ← License 生命周期：issuer/revoker/renewer/verifier/heartbeat/scope/binding
│   │   ├── binding/            ← 绑定模式（none/soft/hard 各一目录，遵循统一 BindingPolicy）
│   │   ├── crl/                ← 撤销列表
│   │   ├── audit/              ← 审计事件
│   │   └── key_storage/        ← 私钥存储（local_file/object_storage/kms 各一目录）
│   │
│   ├── adapters/               ← Service 适配器（HARD RULE：分类下全 provider 必须实现）
│   │   ├── database/           ← interface + postgres/mysql/oracle/tidb
│   │   ├── cache/              ← interface + redis
│   │   └── object_storage/     ← interface + local/s3/azure_blob/aliyun_oss/google_storage/tencent_cos/volcengine_tos/huawei_obs
│   │
│   ├── models/                 ← SQLAlchemy ORM 模型
│   ├── schemas/                ← Pydantic 请求/响应 schema
│   ├── workers/                ← Celery 任务（心跳聚合、CRL 刷新、过期通知）
│   ├── middleware/             ← 鉴权 / request_id / 日志
│   └── exceptions/             ← 业务异常分层
│
├── migrations/                 ← Alembic
│   ├── env.py
│   └── versions/
│       ├── 000001_user_create_table.py
│       ├── 000002_customer_create_table.py
│       ├── 000003_product_create_table.py
│       ├── 000004_license_create_table.py
│       ├── 000005_signing_key_create_table.py
│       ├── 000006_api_key_create_table.py
│       ├── 000007_revocation_list_create_table.py
│       ├── 000008_heartbeat_log_create_table.py
│       └── 000009_audit_log_create_table.py
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── Dockerfile                  ← 交付用（本地开发不用）
```

## 关键设计要点

1. **adapter 层**：业务代码只调用 `app.adapters.<分类>.interface` 中的 Protocol，**不**直接 import 任何具体 provider 的 SDK
2. **签名引擎**：通过 `app.core.signing.Signer` Protocol 统一，3 算法同时注册
3. **私钥存储**：通过 `app.core.key_storage.KeyStorage` Protocol 抽象，本地加密文件 / object storage / KMS 可切换
4. **License 生命周期**：`app.core.license.<动作>/` 每个动作独立模块，便于单测与审计
5. **无硬编码 HARD RULE**：所有可外置值进 `app/settings/`，所有业务常量集中在 `app/core/constants.py`

## 业务流（核心）

### 签发流
```
Admin UI → POST /api/v1/licenses/issue
  → app/api/v1/licenses/issue/handler.py
  → app/core/license/issuer/issue.py
      → 拉客户/产品（adapters.database）
      → 构造 payload（包含 mode/scope/algorithm/binding）
      → 用 signing.<algo> 签名
      → 包成 .forge tarball
      → 存到 adapters.object_storage / 直接返回
      → 写 audit log
  → 返回 .forge 文件或下载链接
```

### Verifier 心跳流
```
Verifier → POST /api/v1/licenses/{id}/heartbeat
  Header: X-Forge-API-Key: <project-api-key>
  Body: { deployment_fingerprint, current_time, ... }
  → middleware 校验 API Key
  → app/core/license/heartbeat/record.py
      → 查 license 状态（adapters.database）
      → 比对 binding（adapters.cache 缓存指纹历史）
      → 检 CRL 是否吊销
      → 写心跳日志
      → 返回当前 license 状态（valid/expired/revoked/binding_mismatch）
```

## 历史变更

## [2026-05-13] 骨架初始化

- 完成目录骨架：3 层（api / core / adapters） + migrations + tests
- 13 个 Service 适配器目录已建好，等待具体实现
- 3 套签名算法目录已建好
- 3 档绑定模式目录已建好
- 3 套私钥存储目录已建好
