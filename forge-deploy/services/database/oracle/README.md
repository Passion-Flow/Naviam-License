# Oracle — Forge local instance

仅供本地开发使用。客户私有化部署连接客户自有 Oracle Database 19c / 21c / 23c（不交付镜像 —— 受 Oracle 许可限制）。

## Quickstart

```bash
cp .env.example .env
# 改 ORACLE_SYS_PASSWORD / ORACLE_PASSWORD 为高熵值
docker compose up -d
# Oracle 首次启动需要 3–5 分钟（创建 PDB + datafile）；观察健康
docker compose logs -f oracle | grep -i ready
bash verify.sh
```

启动后 SQL*Net 端口 `11521`，与 `forge-server/.env.example` 中 `DATABASE_PORT=11521` + `DATABASE_TYPE=oracle` + `DATABASE_SERVICE_NAME=FORGEPDB1` 对齐。

## 默认凭证

| 字段              | 值                              |
|-------------------|--------------------------------|
| host              | `127.0.0.1`                    |
| port              | `11521`                        |
| service_name      | `FORGEPDB1`                    |
| user              | `forge_app`                    |
| password          | `Oracle@!QAZxsw2.`             |
| default tablespace| `USERS`                        |

## 文件分布

```
oracle/
├── docker-compose.yaml      # gvenzl/oracle-xe 21
├── init/01-init-roles.sql   # GRANT + tablespace 设置
├── verify.sh                # 3 步连通自检
├── .env.example
└── .gitignore
```

## 客户私有化部署 — 准备清单

1. **Oracle 版本**：19c / 21c / 23c，建议 PDB 模式。
2. **NLS**：DBA 在数据库级设置 `NLS_CHARACTERSET = AL32UTF8`、`NLS_NCHAR_CHARACTERSET = AL16UTF16`。
3. **业务账号最小权限**（DBA 在客户 PDB 上执行）：

```sql
ALTER SESSION SET CONTAINER = FORGEPDB1;
CREATE USER forge_app IDENTIFIED BY "<高熵密码>"
    DEFAULT TABLESPACE USERS
    QUOTA UNLIMITED ON USERS;
GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE SEQUENCE,
      CREATE VIEW,
      CREATE PROCEDURE,
      CREATE TRIGGER,
      CREATE TYPE
   TO forge_app;
```

> 不给 `DBA` / `SYSDBA` —— 业务运行不需要。

4. **TLS / mTLS**（推荐）：DBA 配置 wallet，把 wallet 文件挂到 forge-server 容器；forge-server `.env` 设 `DATABASE_SSL_MODE=verify-full` + `DATABASE_WALLET_PATH=/etc/forge/oracle-wallet`。
5. **时区**：客户 DB session 必须 `ALTER SESSION SET TIME_ZONE = '+00:00'`（forge-server 启动时显式设置，DBA 无需配置）。

## 已知差异 vs Postgres

- **`updated_at` 自动更新**：Oracle 无 `ON UPDATE`，需 trigger；Forge alembic migration 已生成。
- **`SERIAL` / `IDENTITY`**：Forge 用 `secrets.token_hex(...)` 生成主键，跳过自增，不依赖 Oracle 序列。
- **`JSON` 列**：Oracle 21c+ 原生支持；19c 用 `CLOB`（migration 自动适配）。
- **大小写敏感**：identifier 用引号 → 大小写保留；无引号 → 强制大写。Forge 模型一律 lowercase + 引号。

## 故障排查

| 现象 | 排查 |
|------|------|
| 启动慢 5min+ | 正常，watch `docker logs -f forge-oracle` |
| `ORA-12541 TNS:no listener` | listener 还没起，等 healthcheck `healthy` |
| `ORA-01017 invalid credentials` | `.env` 中 `ORACLE_PASSWORD` 与连接串不一致 |
| `ORA-00942 table or view does not exist` | session container 不对 → `ALTER SESSION SET CONTAINER` |

## 许可注意

| 用途 | 镜像 | 许可 |
|------|------|------|
| 本地开发 | `gvenzl/oracle-xe`（社区） | OTN |
| 本地开发 | `container-registry.oracle.com/database/free` | 官方 Free，免登注册 |
| 私有化生产 | **不交付** | 客户自购 Oracle Enterprise/Standard License |
