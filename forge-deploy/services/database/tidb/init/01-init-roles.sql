-- TiDB unistore 启动时无 root 密码；本脚本 idempotent 设置业务账号。
-- TiDB 兼容 MySQL 8 协议，语法与 MySQL 一致。
-- 通过 verify.sh 引导执行（unistore 不支持镜像 entrypoint sql 自动载入）。

CREATE DATABASE IF NOT EXISTS forge_main
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'forge_app'@'%' IDENTIFIED BY 'Tidb@!QAZxsw2.';

GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE,
      CREATE, ALTER, DROP, INDEX, REFERENCES,
      CREATE TEMPORARY TABLES, LOCK TABLES, TRIGGER
   ON forge_main.*
   TO 'forge_app'@'%';

FLUSH PRIVILEGES;
