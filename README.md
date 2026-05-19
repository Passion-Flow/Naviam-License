# Forge

> License Authority — 厂商侧 license 签发与验签平台。
> 客户私有化部署购买 Forge 签发的 license，未持有效 license 时消费方项目拒绝启动。

## 顶层结构

```
Forge/
├── .agent.md                ← 项目专属规则（必读）
├── README.md                ← 本文件
│
├── Project-design/          ← 品牌 / Mockup / 协议规范
│   ├── brand/               ← logo、色板（继承全局翠绿 #34C759 + 白/黑）
│   ├── mockup/              ← Admin UI 设计稿
│   └── spec/                ← License 协议、payload schema、验签流程、算法矩阵
│
├── Project-source/          ← 3 个子产品
│   ├── forge-admin/         ← React + TS 厂商后台（产出 forge-web 镜像）
│   ├── forge-server/        ← Python FastAPI 签发 + API（产出 forge-api / forge-worker / forge-scheduler 三镜像）
│   └── forge-verifier/      ← Verifier SDK（spec + python + typescript + go，**不**产生镜像）
│
└── forge-deploy/            ← 企业级私有化交付 + 本地 Service 实例
    ├── docker/              ← 交付模式 1（compose / Dockerfile / .env.example）
    ├── gitlab/              ← 交付模式 2（.gitlab-ci.yml / pipelines / variables.md）
    ├── helm/                ← 交付模式 3（Chart / values / templates）
    ├── services/            ← 本地 Service：每个 provider 独立子目录
    │   ├── database/{postgres,mysql,oracle,tidb}/
    │   ├── cache/redis/
    │   └── object-storage/{local,s3,azure-blob,aliyun-oss,google-storage,tencent-cos,volcengine-tos,huawei-obs}/
    └── nginx/
```

## 快速上手（本地开发）

```bash
# 1. 起 Service（按需，最小套件：postgres + redis + minio）
cd forge-deploy/services/database/postgres && docker-compose up -d
cd ../../cache/redis && docker-compose up -d
cd ../../object-storage/local && docker-compose up -d

# 2. 起后端
cd ../../../../Project-source/forge-server
cp .env.example .env
python main.py        # http://localhost:13001

# 3. 起前端
cd ../forge-admin
pnpm install && pnpm dev    # http://localhost:13000
```

默认超管登录：`Admin` / `admin@forge.local`

## 企业级私有化部署

三种交付模式必备（各自独立子目录，对称组织）：

| 模式            | 入口目录                       |
|-----------------|--------------------------------|
| docker-compose  | `forge-deploy/docker/`         |
| GitLab CI       | `forge-deploy/gitlab/`         |
| Helm            | `forge-deploy/helm/`           |

详见 `forge-deploy/README.md`。

## 文档导航

- 项目专属规则：`.agent.md`
- 全局规则：`../Project-Docs/`（见根 `.agent`）
- License 协议规范：`Project-design/spec/`
- 后端结构：`Project-source/forge-server/README.md`
- Verifier 协议：`Project-source/forge-verifier/spec/README.md`
- 部署：`forge-deploy/README.md`
