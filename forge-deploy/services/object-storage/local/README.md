# Object Storage — local (双模)

## 模式

`OBJECT_STORAGE_LOCAL_MODE` 决定走哪个：

- **filesystem**：直接读写本地路径（`OBJECT_STORAGE_LOCAL_PATH`）；不需要起容器
- **minio**：自托管 MinIO（S3 兼容）；本目录的 compose 服务

## 启动（minio 模式）

```bash
docker-compose up -d
```

- S3 API：`http://localhost:19000`
- Console：`http://localhost:19001`
- root：`forge_app` / `Minio@!QAZxsw2.`

## 初始 buckets

`minio-init` 容器会自动创建：
- `forge-license-files`（已签发 .forge 文件）
- `forge-public-keys`（公钥发布）
- `forge-audit-snapshots`（审计快照）

## 数据卷

`data/` 已 gitignore。重置：

```bash
docker-compose down -v
rm -rf data/*
docker-compose up -d
```
