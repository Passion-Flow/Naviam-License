# gitlab/ — 交付模式 2（GitLab CI）

面向客户**使用自托管 GitLab** 的私有化交付物：完整 CI/CD 流水线，可在客户实例里持续构建/发布。

## 计划包含的文件（待补）

| 文件                          | 用途                                                                |
|-------------------------------|---------------------------------------------------------------------|
| `.gitlab-ci.yml`              | 主流水线入口（include 各 stage 模块）                               |
| `pipelines/lint.yml`          | lint stage（ruff / eslint）                                         |
| `pipelines/test.yml`          | test stage（pytest / vitest）                                       |
| `pipelines/build.yml`         | build stage（admin 镜像 / server 镜像）                             |
| `pipelines/scan.yml`          | scan stage（依赖 / 容器 / SAST）                                    |
| `pipelines/publish.yml`       | publish stage（推到客户 private registry）                          |
| `pipelines/deploy-compose.yml`| deploy via docker-compose                                           |
| `pipelines/deploy-helm.yml`   | deploy via helm upgrade                                             |
| `pipelines/verify.yml`        | 部署后烟雾测试                                                      |
| `variables.md`                | CI Variables 清单 + 客户填表参考                                    |

## 必备 stage

```
stages:
  - lint
  - test
  - build
  - scan
  - publish
  - deploy
  - verify
```

每个 stage 可独立跳过/重跑，便于客户根据自己策略裁剪。

## 客户可变项（CI/CD Variables）

字段名必须与 `../docker/.env.example` 和 `../helm/values.yaml` **完全一致**。

具体清单见 `variables.md`（待生成）。

## 路径约定

GitLab 默认期望 `.gitlab-ci.yml` 在仓库根。本项目放此目录是为了三套交付物对称组织。
客户使用时两条路：
1. **推荐**：在仓库根放一个 stub `.gitlab-ci.yml`，内容仅 `include: '/forge-deploy/gitlab/.gitlab-ci.yml'`
2. **替代**：在 GitLab 项目设置 → CI/CD → General pipelines → **Custom CI/CD configuration file** 指向 `forge-deploy/gitlab/.gitlab-ci.yml`

## 升级 / 回滚

参见 `../../../Project-Docs/04-Deployment/gitlab.md`。
