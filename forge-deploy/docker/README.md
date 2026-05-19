## README for docker Deployment

Welcome to the `docker` directory for deploying Forge using Docker Compose. This README outlines the layout, deployment instructions, and provider-selection details for customers running Forge as a self-hosted enterprise License Authority.

### What's Included

- **Application services** (HARD RULE: image planning):
  - `forge-api` — FastAPI HTTP service (port 13001)
  - `forge-worker` — Celery worker (background tasks)
  - `forge-scheduler` — Celery beat (singleton)
  - `forge-web` — Admin UI (nginx serves the built React assets)
- **Self-hosted dependencies** (optional — point env vars at external instances and remove these services if the customer already runs them):
  - PostgreSQL 16
  - Redis 7
  - MinIO (only when `OBJECT_STORAGE_TYPE=local` with `OBJECT_STORAGE_LOCAL_MODE=minio`; enabled via `--profile local-minio`)
- **Edge reverse proxy**: nginx (publishes `HTTP_PORT` / `HTTPS_PORT`)
- **Persistent environment variables**: minimal defaults live in `.env.example`; optional per-topic overrides under `envs/<topic>/*.env.example`

  > What is `.env`? The `.env` file is the local startup file. Copy it from `.env.example` for a default deployment. Optional advanced settings live in `envs/<topic>/*.env.example` files; copy each beside itself without the `.example` suffix when needed.

### How to Deploy Forge with `docker-compose.yaml`

1. **Prerequisites**: Docker and Docker Compose installed on the host.
1. **Environment Setup**:
   - Navigate to the `docker/` directory.
   - Copy `.env.example` to `.env` and fill in the `#REPLACE_ME#` values (passwords, session secret, key master passphrase).
   - For each provider you actually use, copy the matching `envs/<topic>/<topic>.env.example` to `envs/<topic>/<topic>.env`. Only those files are loaded; missing ones are silently ignored (`required: false`).
1. **Run**:
   ```bash
   cp .env.example .env
   docker compose up -d
   ```

1. **Bundle MinIO for object storage (optional)**:
   ```bash
   # Activate the bundled MinIO sidecar
   COMPOSE_PROFILES=local-minio docker compose up -d
   cp envs/object-storage/local.env.example envs/object-storage/local.env
   ```

### Selecting a Provider

Choose providers by editing **two** places:
1. `.env` — set the top-level `*_TYPE` switch (e.g. `DATABASE_TYPE=mysql`)
2. `envs/<topic>/<provider>.env` — copy the matching example file and fill in driver-specific knobs

| Category       | Switch in `.env`      | Provider files under `envs/`                                                                                |
|----------------|-----------------------|-------------------------------------------------------------------------------------------------------------|
| Database       | `DATABASE_TYPE`       | `databases/postgres.env`, `databases/mysql.env`, `databases/oracle.env`, `databases/tidb.env`               |
| Cache          | `CACHE_TYPE`          | `caches/redis.env`                                                                                          |
| Object Storage | `OBJECT_STORAGE_TYPE` | `object-storage/{local,s3,azure-blob,aliyun-oss,google-storage,tencent-cos,volcengine-tos,huawei-obs}.env` |

### Signing Keys

- The signing private keys are encrypted with `KEY_MASTER_PASSPHRASE` (AES-GCM + scrypt KDF) and stored under `KEY_STORAGE_LOCAL_PATH` inside the `forge-api` / `forge-worker` containers.
- **Losing the master passphrase means losing every signing key**, which means losing the ability to sign new licenses. Back it up out-of-band before production.
- For higher security, set `KEY_STORAGE_BACKEND=object_storage` (encrypted blob in your Object Storage of choice) or `kms` (external KMS / Vault).

### Operations

- View logs: `docker compose logs -f forge-api`
- Restart a service: `docker compose restart forge-api`
- Upgrade to a new image tag: edit `IMAGE_TAG` in `.env`, then `docker compose pull && docker compose up -d`
- Backup: data volumes `db-data`, `redis-data`, `minio-data` — back up with your tool of choice before every upgrade
- Health probe: `curl http://localhost:${HTTP_PORT}/api/v1/health`

### Migration from Older Compose Layouts

For users moving from the pre-2026-05-14 layout:

1. **Rename**: `docker-compose.yml` → `docker-compose.yaml`
2. **Split env**: move provider-specific values out of `.env` into the matching `envs/<topic>/<topic>.env`
3. **Update tag**: bump `IMAGE_TAG` to the new release
4. **Wipe old `nginx/conf.d` overrides** if they hardcoded the old service name (`forge-api` vs the renamed `forge-api` — same here, but double-check upstream blocks)

### Troubleshooting

- **forge-api stuck unhealthy**: check `docker compose logs forge-api` — usually database migration failure or missing `KEY_MASTER_PASSPHRASE`
- **forge-scheduler fires tasks twice**: ensure only one replica is running (`deploy.replicas: 1` is enforced in compose, but double-check `docker compose ps`)
- **403 from /api/v1/licenses/issue**: the request has neither an admin session cookie nor a valid `X-Forge-API-Key` header — see `forge-server/README.md` for auth details

---

### Three Delivery Modes

This is **one** of three required delivery artifacts (HARD RULE):

| Mode            | Path                          | When to use                                    |
|-----------------|-------------------------------|------------------------------------------------|
| docker-compose  | `forge-deploy/docker/`        | Single-host, small scale, no K8s               |
| GitLab CI       | `forge-deploy/gitlab/`        | Customer uses GitLab; full CI/CD pipeline      |
| Helm            | `forge-deploy/helm/`          | Customer uses Kubernetes; HA & scale-out       |

The three modes share the same env-variable contract (`DATABASE_*`, `CACHE_*`, `OBJECT_STORAGE_*`, ...). Switch between modes without re-mapping fields.
