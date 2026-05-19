-- forge_app 已由镜像的 MYSQL_USER env 创建并授予 MYSQL_DATABASE 全部权限。
-- 本文件保留为占位 + 显式 GRANT，便于客户审计。
-- 注意：CREATE USER IF NOT EXISTS + GRANT 写法在 MySQL 8.0+ 受支持。

CREATE DATABASE IF NOT EXISTS forge_main
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 显式 GRANT：所有非 DDL 业务权限给到 forge_app
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE,
      CREATE, ALTER, DROP, INDEX, REFERENCES,
      CREATE TEMPORARY TABLES, LOCK TABLES, TRIGGER
    ON forge_main.*
    TO 'forge_app'@'%';

FLUSH PRIVILEGES;
