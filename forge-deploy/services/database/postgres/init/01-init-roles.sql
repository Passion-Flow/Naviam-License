-- Forge — Postgres 初始化脚本 1：账号与权限
--
-- 此脚本仅在数据目录为空时由 postgres 镜像自动执行一次。
-- 内容应与 forge-server alembic migration 解耦：本脚本只建账号 / DB / 扩展，
-- 表结构由 alembic 完成。

-- 应用账号（POSTGRES_USER 已由 entrypoint 创建为超管；这里建一个最小权限账号）
-- 注意：POSTGRES_USER 默认就是 forge_app，并且是 OWNER。如果区分迁移账号/应用账号，
-- 在这里建第二个账号并 grant SELECT/INSERT/UPDATE/DELETE 即可。

-- 建扩展（如需 uuid / citext）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";

-- 时区
SET timezone TO 'UTC';
