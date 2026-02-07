FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client gosu && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash aletheia

# Install dependencies first (cached layer)
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra web --no-install-project

# Copy source and install project
COPY README.md ./
COPY src/ src/
RUN uv sync --frozen --extra web --no-editable

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

WORKDIR /data

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "aletheia.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
