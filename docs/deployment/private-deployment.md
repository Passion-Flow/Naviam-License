# 私有化部署

本文件给厂商运维和客户实施提供可操作的部署指引。

## 部署形态

- 首选：Kubernetes + Helm chart `infra/helm/license/`。
- 备选：Docker Compose（小规模 / POC）。
- SDK：Python pip 包，由产品自行嵌入。

## 前置准备

- Kubernetes ≥ 1.28，或 Docker ≥ 24。
- Postgres 16（Helm 内置部署或外接客户已有 Postgres）。
- Redis 7（同上）。
- TLS 证书与域名（建议厂商内网或客户管理域名）。
- 签发私钥 passphrase（客户运维保管，不由产品保留）。
- 客户合规要求收集：审计保留期、导出格式、备份频率、监控对接方式。

## Helm 部署

### 关键 values（节选）

```yaml
image:
  api: ghcr.io/<vendor>/license-api:1.0.0
  web: ghcr.io/<vendor>/license-web:1.0.0

ingress:
  host: license.example.internal
  tls:
    secretName: license-tls

postgres:
  embedded: true   # 或 false 接外部 Postgres
  password: <PROVIDED>

redis:
  embedded: true
  password: <PROVIDED>

admin:
  username: Admin
  email: admin@example.com
  initialPassword: <PROVIDED>   # 首次登录强制改密

signing:
  passphrase: <PROVIDED>
  encryptedKeyFile: secrets/signing.age

monitoring:
  metrics:
    enabled: true
  alertManager:
    receivers: ...
```

### 步骤

1. 客户运维生成签发私钥 passphrase（高熵口令）。
2. 厂商交付加密私钥文件 `signing.age`（或客户在自己的环境生成）。
3. 部署 Helm chart：
   ```bash
   helm upgrade --install license ./infra/helm/license -f values.yaml
   ```
4. 等待 readiness probe 通过（私钥加载成功 + Postgres + Redis 连接）。
5. 首次登录 -> 强制改密 -> 绑 2FA。
6. 创建第一个客户 -> 签发第一个 License。
7. 备份 Postgres + Redis（规划日常备份策略）。

## Docker Compose 部署（备选）

仅用于 POC / 小规模演示：

```bash
cd projects/license/deploy
docker compose -f database/postgres/docker-compose.yaml up -d
docker compose -f cache/redis/docker-compose.yaml up -d

# API / Web 镜像在生产场景由 CI 构建或离线包提供
docker run -d --name license-api ... ghcr.io/<vendor>/license-api:1.0.0
docker run -d --name license-web ... ghcr.io/<vendor>/license-web:1.0.0
```

## 离线交付

当客户内网无法访问公共仓库：

1. 厂商在构建机执行 `make offline-bundle`：
   - `docker save` 镜像 tar。
   - Helm chart `tgz`。
   - SBOM + 镜像签名。
   - 默认 values 与 README。
2. 客户内网导入：
   - `docker load -i license-api.tar` / `license-web.tar`。
   - 推送到客户私有仓库。
   - `helm install` 指向客户私有仓库镜像地址。

## 多架构

镜像同时构建 `linux/amd64` 与 `linux/arm64`。客户机器架构异构时无需手动选择。

## TLS

- 生产强制 TLS 1.3 + HSTS preload。
- mTLS 用于在线模式 Console -> 产品实例：双方互认公钥；私钥不出本机。
- cert-manager 集成可选：客户也可手动注入证书。

## 监控

- Prometheus `/metrics`：仅内网可达。
- Grafana 模板：随 chart 提供。
- Alertmanager：登录失败激增、签发激增、撤销激增、私钥不可用、Postgres / Redis 不可用。

## 备份与恢复

- Postgres：每日 `pg_basebackup` + WAL；客户合规存储归档。
- Redis：缓存数据丢失允许；限速计数会重置。
- 签发私钥：加密文件 + passphrase 由客户运维保管；推荐冷存与轮换。

## 升级

1. 备份 Postgres。
2. 滚动升级 API + Web（保持至少 1 副本健康）。
3. 校验 `/readyz`、审计链完整、签发链路通。
4. 解除维护。

破坏性数据库变更必须 ADR + 影子库验证 + 灰度。

## 安全清单（交付时核对）

- 默认管理员账号已强制改密 + 绑定 2FA。
- 签发私钥已加密 + passphrase 由客户保管。
- TLS 证书已就位；HSTS 已启用。
- Webhook 通道已配置（如启用）+ HMAC 共享密钥。
- 备份与还原演练已通过。
- Prometheus / Grafana / Alertmanager 已联通。
- 审计导出格式已与客户合规对齐。

## 应急

- 私钥泄漏：立即生成新 kid -> 配置同时启用 -> 主动通知客户重新签发关键 License -> 旧 License 自然到期下线。
- 误签发：通过撤销 + 审计取证 + 人工通知。
- 数据库失控：从最近备份恢复 -> 校验审计链完整 -> 补签发缺失记录。
