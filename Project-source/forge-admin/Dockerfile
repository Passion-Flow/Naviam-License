## forge-admin — 多阶段镜像
## build 阶段 vite build；runtime 阶段 nginx serve 静态资源。

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build


FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="forge-admin"
LABEL org.opencontainers.image.licenses="Proprietary"

# 删除默认 site，使用我们的配置
RUN rm /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

# nginx 配置：SPA fallback + index.html 不缓存 + 资源指纹后强缓存
COPY <<'EOF' /etc/nginx/conf.d/forge-admin.conf
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;

    location = /index.html {
        add_header Cache-Control "no-store" always;
        try_files $uri =404;
    }

    location / {
        try_files $uri /index.html;
    }

    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        try_files $uri =404;
    }

    # 入口脚本运行时替换 window.__APP_CONFIG__；env_substitution 由 entrypoint 处理。
}
EOF

# entrypoint：把 index.html 里的 `<<TOKEN>>` 占位符替换成 env 真实值。
# 占位符名必须与 forge-admin/index.html 中 window.__APP_CONFIG__ 的字段一一对应。
# 必填项缺失 → 容器启动失败（HARD RULE: 无硬编码 / 不允许回落硬编码默认）。
COPY <<'EOF' /docker-entrypoint.d/40-app-config.sh
#!/bin/sh
set -eu
INDEX=/usr/share/nginx/html/index.html

require() {
  name="$1"; value="$2"
  if [ -z "$value" ]; then
    echo "FATAL: $name is empty — refusing to start with placeholder/hardcoded default." >&2
    exit 1
  fi
}

require APP_API_BASE_URL      "${APP_API_BASE_URL:-}"
require APP_SSO_ENABLED       "${APP_SSO_ENABLED:-}"
require APP_BRAND_PRIMARY_HSL "${APP_BRAND_PRIMARY_HSL:-}"

# `|` 作分隔符避免 URL / HSL 中的 `/` 冲突
sed -i \
    -e "s|<<APP_API_BASE_URL>>|${APP_API_BASE_URL}|g" \
    -e "s|<<APP_SSO_ENABLED>>|${APP_SSO_ENABLED}|g" \
    -e "s|<<APP_BRAND_PRIMARY_HSL>>|${APP_BRAND_PRIMARY_HSL}|g" \
    "$INDEX"

# 启动前自检：占位符必须全部已替换
if grep -q '<<APP_' "$INDEX"; then
    echo "FATAL: unresolved <<TOKEN>> placeholders in index.html:" >&2
    grep -o '<<APP_[A-Z_]*>>' "$INDEX" | sort -u >&2
    exit 1
fi
EOF
RUN chmod +x /docker-entrypoint.d/40-app-config.sh

EXPOSE 80
