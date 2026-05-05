# Postgres 16（License Console 主数据库）

唯一的关系型存储；承载 accounts / customers / products / licenses / activations / audit / notifications 等所有结构化数据。

## 部署形态

- 私有化默认：单实例 + 每日 `pg_basebackup` + WAL 归档（≤ 5min RPO）。
- 增长后：streaming replication 主从（V2，不在 V1 镜像内置）。

## 启动

```bash
cd projects/license/deploy/database/postgres
cp .env.example .env  # 默认 username/db = naviam_license, password = Postgres@!QAZxsw2.（仅本地）
docker compose up -d
```

## 关键约束

- 仅监听内部网络：`127.0.0.1:5432` 或 docker overlay；不允许暴露公网。
- 命名规范（与团队约定一致）：
  - DB / username 都 = `naviam_<project>`（License 项目即 `naviam_license`）
  - 密码 = `<Service>@!QAZxsw2.`（dev 默认；生产由 secrets 注入）
- V1 单角色：`naviam_license` 同时承担迁移 + 应用 + 只读（V1 没必要分层增加运维复杂度）。
- V2 拆分预留：`naviam_license_ro`（只读报表）、`naviam_license_repl`（复制）— pg_hba.conf 已留注释。
- 加密：传输强制 `sslmode=verify-full`（settings 里读 `prefer`，跨主机部署需改 verify-full）；存储依赖卷加密（OS / LUKS）。
- 密码、复制 slot、备份口令通过 secrets 注入；禁止写入 compose 文件。
- 备份：`pg_basebackup` + WAL 归档到对象存储或异地磁盘；定期演练恢复（V1 dev 默认关闭 WAL 归档，需要时在 postgresql.conf 解开 `archive_mode = on` 并预创建 archive 目录）。

## 监控指标（V1 必采）

- `pg_stat_activity` 长事务数。
- `pg_stat_replication` lag（主从模式启用后）。
- WAL 归档失败次数。
- 连接数 / 连接池水位。
- 备份成功率与上次成功时间。

## 不做

- 不跑业务存储过程；所有业务逻辑在 Django 层。
- 不直连暴露给前端；前端只能走 API。
