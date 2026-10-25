# Multi-stage Dockerfile for Berthmark Backend API and Stream Worker

# Stage 1: Astral UV Binary Provider
FROM ghcr.io/astral-sh/uv:0.6.14 AS uv-bin

# Stage 2: Final Runtime Application Image
FROM python:3.12-slim-bookworm

# Copy uv binary into runtime image
COPY --from=uv-bin /uv /uvx /bin/

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8000

# Set working directory
WORKDIR /app

# Install curl for healthcheck probing
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies into virtual environment
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project || uv sync --no-install-project

# Copy application source code and migration scripts
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY backend/ ./backend/
COPY openapi.yaml ./
COPY docker-entrypoint.sh ./

# Finalize dependency installation and ensure executable permissions
RUN uv sync && chmod +x docker-entrypoint.sh

# Expose backend API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Configure entrypoint and default command
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
