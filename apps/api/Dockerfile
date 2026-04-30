# Multi-stage Dockerfile for License Console API.
# 不主动 build；仅在 CI / 离线交付时构建。

FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements ./requirements
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements/prod.txt

# ---

FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY --from=builder /usr/lib/x86_64-linux-gnu/libpq.so.5 /usr/lib/x86_64-linux-gnu/libpq.so.5
COPY . /app

USER nonroot
ENV PYTHONPATH=/app:/app/wheels DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8080

# distroless 不带 shell；需要确保入口与参数完全显式
ENTRYPOINT ["python", "-m", "gunicorn", "config.wsgi:application", \
            "--bind", "0.0.0.0:8080", \
            "--workers", "4", \
            "--worker-class", "uvicorn.workers.UvicornWorker", \
            "--access-logfile", "-", "--error-logfile", "-"]
