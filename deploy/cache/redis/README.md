# Redis 7（License Console 缓存 / 会话 / 限速 / 心跳水位）

唯一的内存数据存储；承载：

- Django 会话（`SESSION_ENGINE=cache`）。
- django-axes 失败计数 / 锁定窗口。
- django-ratelimit 限速窗口。
- SDK 在线心跳的去重 / 节流（V2）。

## 部署形态

- 私有化默认：单实例（AOF + RDB）。
- 增长后：Sentinel 主从（V2，不在 V1 镜像内置）。

## 启动

```bash
cd projects/license/deploy/cache/redis
cp .env.example .env  # 填入 REDIS_PASSWORD（≥ 32 字节随机）
docker compose up -d
```

## 关键约束

- 仅监听内部网络：`127.0.0.1:6379` 或 docker overlay。
- 必须开启 `requirepass`；禁止空密码。
- 关闭危险命令：`FLUSHALL` / `FLUSHDB` / `KEYS` / `CONFIG` / `DEBUG` / `SHUTDOWN`。
- AOF + RDB 双开；`appendfsync=everysec`，可接受 ≤ 1s 数据丢失。
- 不存敏感数据：不会出现明文密码 / 私钥 / Activation Code。
- 内存上限：`maxmemory` 设置后启用 `allkeys-lru`，避免 OOM。

## 监控指标（V1 必采）

- 内存使用率 / 命中率。
- 连接数 / 慢日志。
- 持久化失败次数。
- AOF 落盘延迟。

## 不做

- 不当主存储；任何持久化业务数据进 Postgres。
- 不开放给前端直连；只允许 API 与后台 worker 访问。
