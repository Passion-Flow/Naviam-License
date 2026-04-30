# apps/api - License Console API

Django 5 + DRF。Console 后端入口，所有业务模块挂在 `INSTALLED_APPS`，源码在 `src/modules/`。

## 启动

```bash
# 启动 Service 层
cd ../../deploy/database/postgres && docker compose up -d
cd ../../deploy/cache/redis && docker compose up -d

# 安装依赖
cd ../../apps/api
uv venv && uv pip install -r requirements/dev.txt

# 数据库迁移 + 默认管理员 fixtures
python manage.py migrate
python manage.py loaddata config/fixtures/initial.json

# 启动
python manage.py runserver 127.0.0.1:8080
```

## 关键约束

- `DEBUG=False` 仅开发使用 `dev.py`；生产 `prod.py`。
- Argon2id 必须为首选 password hasher。
- 私钥加载失败拒启动。
- `/readyz` 检查 Postgres + Redis + 私钥。
- 不允许写硬编码业务参数；所有可变值进入 `.env`。

## 目录

```text
apps/api/
  manage.py
  pyproject.toml
  Dockerfile
  requirements/
    base.txt
    dev.txt
    prod.txt
  config/
    asgi.py
    wsgi.py
    urls.py
    fixtures/
      initial.json
    settings/
      base.py
      dev.py
      prod.py
```

业务实现按 `docs/development/development-path.md` 阶段化推进。
