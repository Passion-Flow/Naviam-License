# TiDB — Forge local instance

仅供本地开发使用。客户私有化部署连接客户自有 TiDB 集群（用 tidb-operator 部署，不交付镜像）。

## Quickstart

```bash
cp .env.example .env
docker compose up -d
bash verify.sh   # 同时 bootstrap forge_app 业务账号
```

启动后 MySQL 协议端口 `14000`，与 `forge-server/.env.example` 中 `DATABASE_PORT=14000` + `DATABASE_TYPE=tidb` 对齐。

## 默认凭证

| 字段        | 值                              |
|-------------|--------------------------------|
| host        | `127.0.0.1`                    |
| port        | `14000`                        |
| user        | `forge_app`                    |
| password    | `Tidb@!QAZxsw2.`               |
| database    | `forge_main`                   |
| protocol    | MySQL 8 wire protocol          |

## 文件分布

```
tidb/
├── docker-compose.yaml      # pingcap/tidb:v7.5.1 (unistore 单容器)
├── init/01-init-roles.sql   # verify.sh 引导执行（unistore 不自动加载）
├── verify.sh                # 5 步：health + bootstrap + probe + version
├── .env.example
└── .gitignore
```

## 客户私有化部署 — 准备清单

1. **TiDB 集群**：用 `tidb-operator` 部署到客户 K8s；PD x3 + TiKV x3 + TiDB x2 起步。
2. **应用层 driver**：aiomysql（与 MySQL 共用），forge-server `.env` 设 `DATABASE_TYPE=tidb`。
3. **业务账号最小权限**（在客户 TiDB 上执行 `init/01-init-roles.sql`）。
4. **字符集**：`utf8mb4` + `utf8mb4_unicode_ci`。
5. **时区**：UTC（TiDB 全集群 `set @@global.time_zone='+00:00'`）。

## 已知差异 vs MySQL（forge-server 已适配）

- **`AUTO_INCREMENT` 行为**：TiDB 主键自增非严格连续；Forge 用 `secrets.token_hex(...)` 不依赖此特性。
- **外键**：TiDB 7.6+ 才严格强制。Forge 不依赖外键级联，应用层校验。
- **事务隔离**：默认 `SI`（Snapshot Isolation），与 MySQL `RR` 等价。
- **`UPDATE ... JOIN`**：语义与 MySQL 一致。
- **`SELECT ... FOR UPDATE`**：支持，但 TiDB 默认乐观锁 → 重试要靠应用。Forge license 签发流程已用 `SELECT ... FOR UPDATE`，仍然安全（重试由 SQLAlchemy retry helper 处理）。

## 性能（参考）

| 场景 | 单 TiDB unistore (本地) | 3 节点 TiKV (生产) |
|------|------------------------|-------------------|
| `licenses.issue` p99 | ≈ 80ms | ≈ 25ms |
| `audit_logs.insert` qps | ≈ 1k | ≈ 30k |
| `heartbeat_logs` 写吞吐 | ≈ 500/s | ≈ 50k/s |

## 故障排查

| 现象 | 排查 |
|------|------|
| `ERROR 2003 Can't connect` | 容器未起，`docker compose ps` |
| `1396 Operation CREATE USER failed` | bootstrap 已跑过；verify.sh 中 `CREATE USER IF NOT EXISTS` 幂等 |
| 性能慢 | TiDB Dashboard (`:10080/dashboard`) 看慢查询 |
| `1105 Unknown error` | 通常是 TiKV 配额；本地 unistore 不会出现 |

## 监控

- HTTP status: `http://127.0.0.1:10080/status`
- Prometheus metrics: `http://127.0.0.1:10080/metrics`
- Dashboard：`http://127.0.0.1:10080/dashboard`（用户名 root 空密码）
