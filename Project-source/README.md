# Project-source

Forge 的源码，3 个源代码子产品 → 产出 **4 个交付镜像 + 1 个 SDK**：

| 源码目录          | 产出镜像                                                    | 角色                                |
|-------------------|-------------------------------------------------------------|-------------------------------------|
| `forge-admin/`    | `forge-web`（Dockerfile）                                   | 厂商后台（React + TS + Tailwind + shadcn）  |
| `forge-server/`   | `forge-api`（Dockerfile.api）<br>`forge-worker`（Dockerfile.worker）<br>`forge-scheduler`（Dockerfile.scheduler） | FastAPI HTTP / Celery worker / Celery beat |
| `forge-verifier/` | （不产生镜像；产生 SDK）                                    | Python + TS + Go Verifier SDK，嵌入消费方项目 |

**为什么 forge-server 一份源码产 3 个镜像**：API / Worker / Scheduler 共享同一份业务代码、同一组 service 连接、同一份配置，仅 ENTRYPOINT 不同。多 Dockerfile 让镜像独立扩缩 + 角色清晰。

**为什么 forge-admin 改名 forge-web**：源码目录用"admin"表达业务（厂商后台），镜像用"web"表达运行时（nginx 静态资源）。

源码子产品**可独立迭代发布**：UI 改动不需要 server 发版；verifier 的 SDK 版本独立于 server API 版本（通过 protocol_version 兼容）。
