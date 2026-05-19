# nginx — Forge 反代

供 docker-compose 模式使用的 nginx 配置。Helm 模式由 Ingress Controller 处理（TLS 由 cert-manager 或 `helm/templates/shared/tls-secret.yaml` 提供）。

```
nginx/
├── templates/                  ← envsubst 输入；nginx 启动时替换 ${VAR}
│   ├── admin.conf.template     ← :80 主站（HTTP / 默认）
│   └── admin-tls.conf.template ← :443 TLS（NGINX_TLS_ENABLED=true 时启用）
├── ssl/                        ← TLS 证书（gitignore）— forge.crt + forge.key
└── logs/                       ← 访问/错误日志（gitignore）
```

## 变量来源

| 变量 | 来源 | 默认 |
|------|------|------|
| `${SERVER_PORT}` | `docker/.env` | `13001` |
| `${WEB_PORT}` | `docker/.env` | `80` |
| `${NGINX_SERVER_NAME}` | `docker/envs/infrastructure/nginx.env` | `forge.local` |
| `${NGINX_PROXY_BODY_SIZE}` | 同上 | `10m` |
| `${NGINX_TLS_ENABLED}` | 同上（compose profile 决定挂哪个模板） | `false` |

## 启用 TLS（compose 模式）

1. 把证书放到 `nginx/ssl/`：
   ```bash
   # 自签（本地测试）
   openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
       -keyout ssl/forge.key -out ssl/forge.crt -subj "/CN=forge.local"
   # 生产用 cert-manager / ACME / 客户企业 CA
   ```
2. `docker/.env` 加 `NGINX_TLS_ENABLED=true`、`HTTPS_PORT=18443`。
3. compose 自动把 `admin-tls.conf.template` 加入 nginx 容器（通过 profile）。

## TLS 模板内置安全头

`admin-tls.conf.template` 默认开：
- `Strict-Transport-Security: max-age=15552000; includeSubDomains`（180d HSTS）
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- TLS 1.2 / 1.3，禁用旧 cipher

调整请直接改模板；不要在 envsubst 注入安全头（容易遗漏 default-server 路径）。
