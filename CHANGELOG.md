# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 项目骨架初始化：apps/api（Django 5 + DRF）、apps/web（Next.js 14）、sdk（Python 校验 SDK）。
- 八个业务模块骨架：accounts / customers / products / licenses / activations / audit / notifications / security。
- 部署基线：Postgres 16 + Redis 7 docker-compose（仅监听内部网络、强制密码、配置文件分离）。
- 设计文档 13 份（00 总览 → 12 开发路径），覆盖需求、技术栈、架构、目录、前后端、UI、服务层、数据库、镜像、私有化约束、模块化规范。
- 安全扩展文档：threat-model（STRIDE）、owasp-coverage（OWASP Top 10 2021）、crypto-spec（Ed25519 + Cloud ID v1 + 哈希链）。
- API 契约（V1 endpoints 与错误码）、ADR-0001（项目边界）、开发路径（8 阶段）、私有化部署指南。

### Notes
- V1 仅引入两类基础服务：Postgres + Redis；其它（MinIO / Elastic / 反代 / MQ）暂不引入，引入条件见 `docs/design/08-服务层设计.md`。
- 默认超管账号 `Admin / admin@workerspace.ai` 仅用于本地开发；生产部署必须强制改密码。
- Vendor 签名私钥默认走 A 方案（age / sops 加密文件 + passphrase）；KMS / HSM 后续可替换 IKeySigner 实现。
