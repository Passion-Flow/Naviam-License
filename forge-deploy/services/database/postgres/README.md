# PostgreSQL — Forge local instance

## 启动

```bash
docker-compose up -d
```

监听 `0.0.0.0:15432`（已避开系统 5432 防冲突）。

## 默认凭证（**仅本地开发**；交付前客户必须改）

- user: `forge_app`
- password: `Postgres@!QAZxsw2.`
- database: `forge_main`

## 文件

- `docker-compose.yaml` — 启动定义
- `config/postgresql.conf` — Postgres 主配置（max_connections / shared_buffers / wal_level 等）
- `config/pg_hba.conf` — 客户端认证策略
- `init/*.sql` — 首次启动自动执行（建用户、建库、grant 权限、seed 等）
- `data/` — 数据卷（gitignore）

## 重置数据

```bash
docker-compose down -v
rm -rf data/*
docker-compose up -d
```
