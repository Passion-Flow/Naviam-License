# Postgres 16（License Console 主数据库）

唯一的关系型存储；承载 accounts / customers / products / licenses / activations / audit / notifications 等所有结构化数据。

## 部署形态

- 私有化默认：单实例 + 每日 `pg_basebackup` + WAL 归档（≤ 5min RPO）。
- 增长后：streaming replication 主从（V2，不在 V1 镜像内置）。

## 启动

```bash
cd projects/license/deploy/database/postgres
cp .env.example .env  # 填入 POSTGRES_PASSWORD（≥ 24 字节随机）
docker compose up -d
```

## 关键约束

- 仅监听内部网络：`127.0.0.1:5432` 或 docker overlay；不允许暴露公网。
- Postgres 角色分层：
  - `license_owner`：执行迁移；密码仅迁移期内可用。
  - `license_app`：API 运行时使用；只能读写应用表，禁 DDL。
  - `license_ro`：审计 / 报表只读。
- 加密：传输强制 `sslmode=verify-full`；存储依赖卷加密（OS / LUKS）。
- 密码、复制 slot、备份口令通过 secrets 注入；禁止写入 compose 文件。
- 备份：`pg_basebackup` + WAL 归档到对象存储或异地磁盘；定期演练恢复。

## 监控指标（V1 必采）

- `pg_stat_activity` 长事务数。
- `pg_stat_replication` lag（主从模式启用后）。
- WAL 归档失败次数。
- 连接数 / 连接池水位。
- 备份成功率与上次成功时间。

## 不做

- 不跑业务存储过程；所有业务逻辑在 Django 层。
- 不直连暴露给前端；前端只能走 API。
