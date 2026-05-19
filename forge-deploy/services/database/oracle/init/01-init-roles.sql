-- forge_app schema 由镜像入口脚本（APP_USER env）创建。
-- 本文件追加授予表空间 / 默认参数（Oracle 19c+ PDB 风格）。
-- gvenzl/oracle-xe 镜像在 *.sql 文件结尾不需要 / —— 但显式留更兼容。

ALTER SESSION SET CONTAINER = FORGEPDB1;

-- 把 USERS 表空间作为默认（XE 默认就是 USERS，这里显式声明）
ALTER USER forge_app DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS;

-- 业务必须权限：DDL + DML + 序列；不给 SYSDBA / ANY ROLE
GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE SEQUENCE,
      CREATE VIEW,
      CREATE PROCEDURE,
      CREATE TRIGGER,
      CREATE TYPE
   TO forge_app;
