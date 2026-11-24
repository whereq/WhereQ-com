# =============================================================================
# whereq.com API — Production Dockerfile
# Multi-stage build for smaller, secure images
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — install dependencies
# -----------------------------------------------------------------------------
FROM python:3.14.6-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Runtime — minimal production image
# -----------------------------------------------------------------------------
FROM python:3.14.6-slim-bookworm AS runtime

LABEL maintainer="whereq Team"
LABEL description="whereq.com API Service"

RUN groupadd -r whereq && useradd -r -g whereq whereq

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

RUN chown -R whereq:whereq /app
USER whereq

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
