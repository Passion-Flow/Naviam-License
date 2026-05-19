# forge-deploy/services/

本地开发用的 **Service 实例容器**。每个 service 一份独立 compose，独立启停。

**与 docker/ 的区别**：
- `services/` = **本地开发**起单个 service（postgres / redis / minio ...）
- `docker/` = **客户私有化交付** —— 一份大 compose 编排整套 Forge

## 启动方式

```bash
cd services/database/postgres && docker-compose up -d
cd ../../cache/redis && docker-compose up -d
cd ../../object-storage/local && docker-compose up -d
```

## 已就位的 service

| 分类           | provider       | docker-compose 状态 | 备注                              |
|----------------|----------------|---------------------|-----------------------------------|
| Database       | postgres       | ✅ 完整              | 默认推荐                          |
| Database       | mysql          | 🟡 stub             | 待补                              |
| Database       | oracle         | 🟡 stub             | 待补，需 Oracle 镜像许可注意      |
| Database       | tidb           | 🟡 stub             | 待补                              |
| Cache          | redis          | ✅ 完整              | AOF + RDB 双开                    |
| Object Storage | local (minio)  | ✅ 完整              | local 模式默认走 MinIO            |
| Object Storage | s3 / 各云      | n/a                 | 公有云，无本地 compose；env 配置  |

## 端口（与 `.agent.md` 端口表一致）

- postgres: 15432
- mysql:    13306
- oracle:   11521
- tidb:     14000
- redis:    16379
- minio S3 API:  19000
- minio Console: 19001

## 数据卷

每个 service 的 `data/` 目录 **必须 gitignore**。
