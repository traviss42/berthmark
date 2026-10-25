#!/bin/sh
set -e

# Run database migrations and seeders if enabled (default: true)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[docker-entrypoint] Running database migrations..."
    uv run alembic upgrade head || echo "[docker-entrypoint] Warning: alembic migrations failed or skipped"

    echo "[docker-entrypoint] Running database seeders..."
    uv run python -m backend.seed || echo "[docker-entrypoint] Warning: seeder failed or skipped"
fi

echo "[docker-entrypoint] Executing command: $@"
exec "$@"
