# 服务总账（License V1）

> V1 仅引入两类基础服务。其它（MinIO / Elastic / Nginx 反代 / 消息队列等）暂不引入；引入条件见 `docs/design/08-服务层设计.md`。

| 服务 | 角色 | 部署位置 | 必备 | 替代条件 |
| --- | --- | --- | --- | --- |
| Postgres 16 | 主数据库（accounts / licenses / audit 全量结构化数据） | `deploy/database/postgres/` | ✅ | 不可替代 |
| Redis 7 | 会话 / 限速 / 心跳节流 / 锁定窗口 | `deploy/cache/redis/` | ✅ | 单机内存够用前不替换 |

## V2 候选（明确不在 V1 内）

| 候选服务 | 触发条件 | 备注 |
| --- | --- | --- |
| 对象存储（MinIO / S3） | 客户附件 / 备份镜像超 1GB | 现阶段备份本地磁盘 + WAL 归档够用 |
| 全文检索（Postgres tsvector → Elastic） | 审计单表 > 5,000 万行且需要复杂查询 | 当前 `audit_event` 单库索引足够 |
| 消息队列（Redis Streams → Kafka） | Webhook 投递量 > 100 QPS | V1 直接 HTTP 同步 + 重试 |
| 反向代理（Nginx / Caddy） | 多副本 / 多域名 / 公网 | 私有化默认由企业现有入口托管 |

## 启动顺序（开发本地）

1. `deploy/database/postgres/` — `docker compose up -d`
2. `deploy/cache/redis/` — `docker compose up -d`
3. `apps/api/` — 等 Postgres healthy 后启动
4. `apps/web/` — 任何时候启动

## 不做

- 不在本目录放 license-api / license-web 的运行配置（它们属于 `apps/`）。
- 不在 V1 引入"以防万一"的服务；每多一个组件 = 多一个攻击面 + 多一份运维代价。
