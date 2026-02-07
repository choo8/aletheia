# Stage 1: Build dependencies with uv
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra web --no-install-project

# Copy source and install project
COPY src/ src/
RUN uv sync --frozen --extra web

# Stage 2: Slim runtime
FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash aletheia

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ALETHEIA_DATA_DIR=/data \
    ALETHEIA_STATE_DIR=/data/.aletheia

# Copy entrypoint
COPY deploy/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Data volume
RUN mkdir -p /data && chown aletheia:aletheia /data
VOLUME /data

USER aletheia
WORKDIR /data

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "aletheia.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
