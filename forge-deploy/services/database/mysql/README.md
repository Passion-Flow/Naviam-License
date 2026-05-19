# MySQL — Forge local instance

仅供本地开发使用。客户私有化部署连接客户自有 MySQL 8.x 实例（不交付镜像）。

## Quickstart

```bash
cp .env.example .env
# 修改 MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD 为高熵值
docker compose up -d
bash verify.sh
```

启动后端口 `13306`，与 `forge-server/.env.example` 中 `DATABASE_PORT=13306` + `DATABASE_TYPE=mysql` 对齐。

## 默认凭证（与全局命名规则一致）

| 字段        | 值                              |
|-------------|--------------------------------|
| host        | `127.0.0.1`                    |
| port        | `13306`                        |
| user        | `forge_app`                    |
| password    | `Mysql@!QAZxsw2.`              |
| database    | `forge_main`                   |
| charset     | `utf8mb4`                      |
| collation   | `utf8mb4_unicode_ci`           |
| sql_mode    | STRICT_TRANS_TABLES + 等       |

## 文件分布

```
mysql/
├── docker-compose.yaml      # 本地开发起 mysql:8.0
├── config/my.cnf            # 应用层 my.cnf（charset / sql_mode / isolation）
├── init/01-init-roles.sql   # GRANT 给 forge_app
├── verify.sh                # 4 步连通自检
├── .env.example             # 仅本地凭证；不入仓
└── .gitignore               # data/ + .env
```

## 客户私有化部署 — 准备清单

1. **MySQL 实例**：8.0+（5.7 不支持 `caching_sha2_password` 默认 + `JSON` 列性能差）
2. **字符集 / 排序**：必须 `utf8mb4` + `utf8mb4_unicode_ci`
3. **sql_mode**：必须包含 `STRICT_TRANS_TABLES`、`NO_ZERO_DATE`
4. **时区**：UTC（DBA 在 `[mysqld]` 设 `default-time-zone=+00:00`）
5. **业务账号最小权限**（在客户 DB 上执行）：

```sql
CREATE DATABASE forge_main CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'forge_app'@'%' IDENTIFIED BY '<高熵密码>';
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE,
      CREATE, ALTER, DROP, INDEX, REFERENCES,
      CREATE TEMPORARY TABLES, LOCK TABLES, TRIGGER
   ON forge_main.* TO 'forge_app'@'%';
FLUSH PRIVILEGES;
```

> 不给 `SUPER` / `RELOAD` / `PROCESS` —— `forge-api` 不需要。

6. **TLS**（推荐）：客户端在 forge-server `.env` 设 `DATABASE_SSL_MODE=required` 并把 CA 证书挂到容器。

## 容量预估（参考）

| 表                | 单行 ≈ | 1k 客户 / 1y 估算   |
|-------------------|--------|---------------------|
| `licenses`        | 8 KB   | ≈ 80 MB（含 forge_file blob）|
| `heartbeat_logs`  | 0.3 KB | ≈ 11 GB（持续 archive 后稳定在 90 天）|
| `audit_logs`      | 0.5 KB | ≈ 1 GB（与 `AUDIT_RETENTION_DAYS` 关联）|

## 已知差异 vs Postgres

- MySQL 8 的 `JSON` 列没有真正的 GIN 索引；查询性能略低于 Postgres。Forge 业务不依赖 JSON 复杂查询，差异可忽略。
- `expires_at < NOW()` 在 MySQL 走索引（与 PG 行为一致）。
- 默认事务隔离 = `READ-COMMITTED`（避免 RR 死锁）。

## 故障排查

| 现象 | 排查 |
|------|------|
| `ERROR 2003 Can't connect` | 容器未起 → `docker compose ps` |
| `ER_ACCESS_DENIED_ERROR` | `.env` 与 forge-server `.env` 不一致 |
| `1366 Incorrect string value` | 表 / 列不是 `utf8mb4` |
| 性能慢 | `slow_query_log` 看 `> 200ms` 查询，加索引或 `EXPLAIN` |
