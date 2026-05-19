# GitLab CI Variables — Forge

客户在 GitLab → 项目设置 → CI/CD → Variables 中配置以下变量。
字段名与 `../docker/.env.example` 和 `../helm/values.example.yaml` **完全一致**。

## 镜像仓库

| Variable                 | Type   | Masked | Required | 描述                          |
|--------------------------|--------|--------|----------|-------------------------------|
| CI_REGISTRY              | Var    | No     | Y        | 由 GitLab 自动注入            |
| CI_REGISTRY_USER         | Var    | No     | Y        | 由 GitLab 自动注入            |
| CI_REGISTRY_PASSWORD     | File   | Yes    | Y        | 由 GitLab 自动注入            |
| DEPLOY_REGISTRY_HOST     | Var    | No     | Y        | 客户私有 registry 地址        |
| DEPLOY_REGISTRY_USER     | Var    | No     | Y        | 推送账号                      |
| DEPLOY_REGISTRY_TOKEN    | Var    | Yes    | Y        | 推送密钥                      |

## 部署目标

| Variable                 | Type   | Masked | Required | 描述                                |
|--------------------------|--------|--------|----------|-------------------------------------|
| DEPLOY_TARGET            | Var    | No     | Y        | `compose` 或 `helm`                 |
| DEPLOY_HOST              | Var    | No     | 取决于 target | compose 模式的目标主机          |
| DEPLOY_K8S_CLUSTER       | Var    | No     | 取决于 target | helm 模式的 K8s 上下文         |
| DEPLOY_NAMESPACE         | Var    | No     | Y        | helm release namespace              |
| ENV_NAME                 | Var    | No     | Y        | `dev` / `staging` / `prod`          |

## 应用配置（与 docker/.env.example / helm/values.yaml 一致）

字段名详见 `../docker/.env.example`。所有"⚠️ 交付前改"项必须在 GitLab Variables 中由客户填入。

## 通知 / 审批

| Variable                 | Type   | Masked | Required | 描述                              |
|--------------------------|--------|--------|----------|-----------------------------------|
| APPROVE_DEPLOY           | Var    | No     | N        | `true` 时 deploy stage 需手动批准 |
| NOTIFY_WEBHOOK_URL       | Var    | Yes    | N        | 部署成功/失败回调                 |
