# forge-deploy

Forge 的**企业级私有化交付物**与本地 Service 实例。

## 子目录

| 子目录       | 内容                                               |
|--------------|----------------------------------------------------|
| `docker/`    | **交付模式 1**：docker-compose.yml + Dockerfile + .env.example |
| `gitlab/`    | **交付模式 2**：.gitlab-ci.yml + CI 流水线脚本 / variables 文档 |
| `helm/`      | **交付模式 3**：Helm Chart（Chart.yaml + values + templates） |
| `services/`  | **本地 Service 实例**：每个 provider 独立子目录，独立 docker-compose 启动 |
| `nginx/`     | 反代配置（compose 模式与裸机部署用）                |

## 三种交付模式必须等价

- 同一镜像 tag 在 compose / Helm 都能启动
- 环境变量字段名在 docker/.env / GitLab CI variables / Helm values 中**一一对应**
- 同样的健康检查、日志格式、资源限制语义

## 本地开发用法（与交付模式无关）

本地开发**不用**这三种交付模式。直接：

```bash
# 进入需要的 service 目录起容器
cd services/database/postgres && docker-compose up -d
cd services/cache/redis && docker-compose up -d
cd services/object-storage/local && docker-compose up -d
```

然后用语言原生命令起 forge-admin / forge-server。详见 `../README.md` 快速上手。

## 关于 `.gitlab-ci.yml` 路径约定

GitLab 默认期望 `.gitlab-ci.yml` 在仓库根。本项目放在 `forge-deploy/gitlab/.gitlab-ci.yml`，
客户使用时需要在 GitLab 项目设置 → CI/CD → General pipelines → **Custom CI/CD configuration file** 中指定该路径。

仓库根也可以放一个 stub `.gitlab-ci.yml` 转发到此（include 形式），按客户偏好。
