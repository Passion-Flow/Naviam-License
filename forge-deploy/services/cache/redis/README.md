# Redis — Forge local instance

## 启动

```bash
docker-compose up -d
```

监听 `0.0.0.0:16379`。

默认密码：`Redis@!QAZxsw2.`

### 多 db 切分（与 .agent.md 一致）
- db 0：应用缓存
- db 1：Session
- db 2：Celery broker
- db 3：Celery result

### 危险命令已 rename
- FLUSHALL / FLUSHDB / KEYS / CONFIG 全部禁用
