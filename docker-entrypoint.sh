#!/bin/sh
set -e

# Run database migrations and seeders if enabled (default: true)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    if [ ! -f "app/data/ports_seed.json" ]; then
        echo "[docker-entrypoint] Reference seed data missing; running scripts/build_seed_data.py..."
        uv run python scripts/build_seed_data.py || echo "[docker-entrypoint] Warning: seed build script failed"
    fi

    echo "[docker-entrypoint] Running database migrations..."
    uv run alembic upgrade head || echo "[docker-entrypoint] Warning: alembic migrations failed or skipped"

    echo "[docker-entrypoint] Running database seeders..."
    uv run python -m backend.seed || echo "[docker-entrypoint] Warning: seeder failed or skipped"
fi

echo "[docker-entrypoint] Executing command: $@"
exec "$@"
